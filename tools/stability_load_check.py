"""Generated-data load/re-export checks with measured time and process RSS."""

import argparse
import gc
import hashlib
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mergeguru_engine as engine


class Measurements:
    def __init__(self):
        self.rows = []

    def run(self, name, function):
        stop = threading.Event()
        process = psutil.Process()
        peak = [process.memory_info().rss]
        def sample():
            while not stop.wait(0.05):
                peak[0] = max(peak[0], process.memory_info().rss)
        monitor = threading.Thread(target=sample, daemon=True)
        monitor.start()
        started = time.perf_counter()
        try:
            result = function()
        finally:
            peak[0] = max(peak[0], process.memory_info().rss)
            stop.set()
            monitor.join()
        elapsed = time.perf_counter() - started
        self.rows.append((name, elapsed, peak[0] / 1024 ** 2))
        print(f"PASS {name}: {elapsed:.2f}s; peak process RSS {peak[0] / 1024 ** 2:.1f} MiB", flush=True)
        return result


def create_csv(path, start, count, wide=False, shuffled=False, extra=False):
    with path.open("w", encoding="utf-8", newline="") as stream:
        for offset in range(0, count, 10_000):
            numbers = range(start + offset, start + min(count, offset + 10_000))
            frame = pd.DataFrame({"id": [f"{number:012d}" for number in numbers],
                                  "region": ["East" if number % 2 == 0 else "West" for number in numbers],
                                  "amount": list(numbers)})
            if wide:
                frame["payload"] = ["x" * 256 + str(number % 8) for number in numbers]
            if extra:
                frame["note"] = "additional column"
            if shuffled:
                frame = frame[list(reversed(frame.columns))]
            frame.to_csv(stream, header=(offset == 0), index=False)


def checksum(frame):
    return hashlib.sha256(pd.util.hash_pandas_object(frame, index=False).values.tobytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="work/stability_load_results.md")
    args = parser.parse_args()
    available = psutil.virtual_memory().available / 1024 ** 3
    if available < 0.65:
        raise RuntimeError(f"Only {available:.2f} GiB available; generated load test requires at least 0.65 GiB.")
    metrics = Measurements()
    with tempfile.TemporaryDirectory(prefix="mergeguru_load_") as temporary:
        work = Path(temporary)
        wide_paths = [work / f"wide_{index}.csv" for index in range(4)]
        for index, path in enumerate(wide_paths):
            create_csv(path, index * 100_000, 100_000, wide=True, shuffled=bool(index % 2), extra=index == 3)
        wide_bytes = sum(path.stat().st_size for path in wide_paths)
        print(f"Generated wide CSV: 400,000 rows; {wide_bytes / 1024 ** 2:.1f} MiB source bytes", flush=True)
        sources, errors = engine.discover_sources([str(path) for path in wide_paths])
        assert not errors
        validation = metrics.run("Validate 400k-row wide CSV sources", lambda: engine.validate_sources(sources, 0, allow_extra=True))
        assert len(validation["passed_sources"]) == 4 and validation["summary"]["warn"] == 1
        digests = []
        for fast in (False, True):
            mode = "parallel" if fast else "sequential"
            frame, extras, stats = metrics.run(f"Combine 400k rows ({mode})", lambda: engine.combine_sources(
                sources, sources[0], validation["reference_columns"], allow_extra=True,
                extra_columns=validation["extra_columns"], fast_mode=fast, optimize_memory=True))
            assert len(frame) == 400_000 and extras == ["note"]
            assert frame["id"].astype(str).iloc[[0, 99_999, 100_000, 399_999]].tolist() == ["000000000000", "000000099999", "000000100000", "000000399999"]
            assert frame["amount"].astype("int64").sum() == 400_000 * 399_999 // 2
            assert frame["payload"].notna().all()
            assert frame["source_file"].value_counts().to_dict() == {path.name: 100_000 for path in wide_paths}
            assert frame.loc[300_000:, "note"].notna().all() and frame.loc[:299_999, "note"].isna().all()
            digests.append(checksum(frame))
            if not fast:
                def repeated_exports():
                    with patch.object(engine, "read_full", side_effect=AssertionError("Re-export reread a source")):
                        for index in range(4):
                            region = "East" if index % 2 == 0 else "West"
                            filtered = engine.apply_filters(frame, [{"mode": "text", "column": "region", "operator": "equals", "value": region}])
                            assert len(filtered) == 200_000
                            output = work / f"repeat_{index}.csv"
                            engine.save_dataframe(filtered, str(output), "CSV-Unique text", unique_columns=["id"])
                            count = 0
                            for chunk in pd.read_csv(output, dtype={"id": str}, chunksize=25_000):
                                assert chunk["region"].eq(region).all()
                                assert chunk["id"].str.fullmatch(r"'\d{12}'").all()
                                count += len(chunk)
                            assert count == 200_000
                            output.unlink()
                    return None
                metrics.run("Four cached filtered CSV exports (200k rows each)", repeated_exports)
                def parquet_roundtrip():
                    output = work / "wide.parquet"
                    engine.save_dataframe(frame, str(output), "Parquet")
                    restored = pd.read_parquet(output)
                    assert checksum(restored) == checksum(frame)
                metrics.run("400k-row Parquet round-trip", parquet_roundtrip)
            del frame
            gc.collect()
        assert digests[0] == digests[1], "Sequential and parallel outputs differ"

        compact_paths = [work / f"compact_{index}.csv" for index in range(2)]
        for index, path in enumerate(compact_paths):
            create_csv(path, index * 500_000, 500_000)
        compact_bytes = sum(path.stat().st_size for path in compact_paths)
        print(f"Generated compact CSV: 1,000,000 rows; {compact_bytes / 1024 ** 2:.1f} MiB source bytes", flush=True)
        compact = engine.discover_sources([str(path) for path in compact_paths])[0]
        approved = engine.validate_sources(compact, 0)
        frame, _, _ = metrics.run("Combine 1 million compact CSV rows", lambda: engine.combine_sources(
            compact, compact[0], approved["reference_columns"], optimize_memory=True))
        assert len(frame) == 1_000_000
        assert frame["amount"].astype("int64").sum() == 1_000_000 * 999_999 // 2
        assert frame["id"].astype(str).iloc[-1] == "000000999999"
        del frame
        gc.collect()

        excel_paths = [work / f"excel_{index}.xlsx" for index in range(2)]
        for index, path in enumerate(excel_paths):
            numbers = range(index * 25_000, (index + 1) * 25_000)
            frame = pd.DataFrame({"id": [f"{number:012d}" for number in numbers], "amount": list(numbers)})
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                pd.DataFrame({"ignore": [1]}).to_excel(writer, sheet_name="Summary", index=False)
                frame.to_excel(writer, sheet_name=f"Dump 2026-10-{index + 1:02d}", index=False)
        del frame
        gc.collect()
        excel_bytes = sum(path.stat().st_size for path in excel_paths)
        excel_sources = engine.discover_sources([str(path) for path in excel_paths])[0]
        approved = metrics.run("Validate differently named Excel worksheets", lambda: engine.validate_sources(
            excel_sources, 0, selected_sheet="Dump 2026-10-01", auto_match_sheet=True))
        assert len(approved["passed_sources"]) == 2
        frame, _, _ = metrics.run("Combine 50k Excel rows", lambda: engine.combine_sources(
            excel_sources, excel_sources[0], approved["reference_columns"], selected_sheet="Dump 2026-10-01",
            source_sheet_map=approved["source_sheet_map"], fast_mode=True, optimize_memory=True))
        assert len(frame) == 50_000 and frame["id"].astype(str).iloc[-1] == "000000049999"
        def excel_export():
            output = work / "excel_export.xlsx"
            engine.save_dataframe(frame, str(output), "Excel", validation_report_df=pd.DataFrame(approved["summary"], index=[0]))
            with pd.ExcelFile(output) as book:
                assert book.sheet_names == ["Data", "Validation Report"]
                restored = pd.read_excel(book, sheet_name="Data", dtype={"id": str})
            assert checksum(restored) == checksum(frame)
        metrics.run("50k-row Excel export and value round-trip", excel_export)

    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Generated-Data Stability Results", "", f"Initial available RAM: {available:.2f} GiB.",
             f"Wide CSV: 400,000 rows in 4 sources, {wide_bytes / 1024 ** 2:.1f} MiB on disk.",
             f"Compact CSV: 1,000,000 rows in 2 sources, {compact_bytes / 1024 ** 2:.1f} MiB on disk.",
             f"Excel: 50,000 rows in 2 workbooks, {excel_bytes / 1024 ** 2:.2f} MiB on disk.", "",
             "| Check | Seconds | Peak Process RSS (MiB) | Result |", "|---|---:|---:|---|"]
    lines.extend(f"| {name} | {elapsed:.2f} | {peak:.1f} | PASS |" for name, elapsed, peak in metrics.rows)
    lines.extend(["", "Peak RSS includes imported libraries and the retained Python allocator; it is sampled at 50 ms intervals.",
                  "Measurements use synthetic local data and do not predict timings on production storage or machines.",
                  "This pass does not load 2 GB of raw source data or certify worst-case memory requirements.",
                  "Generated source and export files were removed when the test completed.", ""])
    report.write_text("\n".join(lines), encoding="utf-8")
    print(f"Load checks passed; report: {report.resolve()}", flush=True)


if __name__ == "__main__":
    main()
