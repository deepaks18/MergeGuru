"""Opt-in local packaging self-test; never runs during ordinary startup."""

import platform
import sys
import tempfile
import traceback
import zipfile
from pathlib import Path

import pandas as pd

import mergeguru_engine as engine


def run_self_test(report_path, app_factory, splash=None):
    lines = ["MergeGuru Lite Local Self-Test", f"Version: {engine.APP_VERSION}",
             f"Frozen: {bool(getattr(sys, 'frozen', False))}",
             f"Python: {sys.version.split()[0]}", f"Platform: {platform.system()}"]
    result = 1
    try:
        with tempfile.TemporaryDirectory(prefix="mergeguru_selftest_") as temporary:
            folder = Path(temporary)
            reference = folder / "reference.csv"
            shuffled = folder / "shuffled.csv"
            workbook = folder / "dated.xlsx"
            archive_path = folder / "archive.zip"
            pd.DataFrame({"id": ["001"], "region": ["East"], "amount": [1]}).to_csv(reference, index=False)
            pd.DataFrame({"amount": [2], "id": ["002"], "region": ["West"], "note": ["extra"]}).to_csv(shuffled, index=False)
            pd.DataFrame({"id": ["003"], "region": ["East"], "amount": [3]}).to_excel(workbook, sheet_name="Dump 2026-10-03", index=False)
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("nested/source.csv", "id,region,amount\n004,West,4\n")
            sources, errors = engine.discover_sources([str(path) for path in (reference, shuffled, workbook, archive_path)])
            assert not errors and len(sources) == 4
            lines.append("PASS: CSV/Excel/ZIP discovery")
            approved = engine.validate_sources(sources, 0, allow_extra=True, auto_match_sheet=True)
            assert len(approved["passed_sources"]) == 4
            assert approved["summary"]["warn"] == 1
            lines.append("PASS: Header validation and worksheet mapping")
            frame, _, _ = engine.combine_sources(sources, sources[0], approved["reference_columns"],
                source_sheet_map=approved["source_sheet_map"], allow_extra=True,
                extra_columns=approved["extra_columns"], fast_mode=True, optimize_memory=True)
            assert frame["id"].astype(str).tolist() == ["001", "002", "003", "004"]
            assert frame["amount"].sum() == 10
            lines.append("PASS: Parallel combine, column alignment, and identifiers")
            filtered = engine.apply_filters(frame, [{"mode": "text", "column": "region", "operator": "equals", "value": "East"}])
            assert len(filtered) == 2
            csv_path = folder / "output.csv"
            engine.save_dataframe(filtered, str(csv_path), "CSV-Unique text", unique_columns=["id"])
            assert pd.read_csv(csv_path, dtype=str)["id"].tolist() == ["'001'", "'003'"]
            lines.append("PASS: Filtering and protected CSV export")
            excel_path = folder / "output.xlsx"
            engine.save_dataframe(frame, str(excel_path), "Excel", validation_report_df=pd.DataFrame({"Status": ["PASS"]}))
            with pd.ExcelFile(excel_path) as book:
                assert book.sheet_names == ["Data", "Validation Report"]
                assert pd.read_excel(book, sheet_name="Data", dtype={"id": str})["id"].tolist() == ["001", "002", "003", "004"]
            lines.append("PASS: Excel writer and Validation Report")
            parquet_path = folder / "output.parquet"
            engine.save_dataframe(frame, str(parquet_path), "Parquet")
            assert pd.read_parquet(parquet_path)["id"].astype(str).tolist() == ["001", "002", "003", "004"]
            lines.append("PASS: Bundled Parquet support")
            before = csv_path.read_bytes()
            cancelled = [False]
            try:
                engine.save_dataframe(frame, str(csv_path), "CSV", cancel_callback=lambda: cancelled[0],
                    progress_callback=lambda *args: cancelled.__setitem__(0, True))
            except engine.CancelledOperation:
                pass
            else:
                raise AssertionError("Cancelled export was committed")
            assert csv_path.read_bytes() == before
            assert not list(folder.glob(".mergeguru-*"))
            lines.append("PASS: Cancelled overwrite preserves existing output")

        if splash is not None:
            splash.close()
        with tempfile.TemporaryDirectory(prefix="mergeguru_ui_selftest_") as ui_temporary:
            ui_folder = Path(ui_temporary)
            try:
                app = app_factory(
                    preference_file=str(ui_folder / "preferences.json"),
                    diagnostic_file=str(ui_folder / "diagnostics.jsonl"),
                )
            except TypeError:
                app = app_factory()
            app.withdraw()
            callback_errors = []
            app.report_callback_exception = lambda *args: callback_errors.append(args)
            try:
                if hasattr(app, "start_task"):
                    completed = []
                    timed_out = []

                    def worker(report, cancelled):
                        assert not cancelled()
                        report(60, "Checking progress", "Synthetic packaged task")
                        return "ready"

                    app.start_task(
                        "self-test",
                        "Checking packaged UI",
                        worker,
                        lambda value: (completed.append(value), app.quit()),
                    )
                    assert app.busy
                    assert app.progress.winfo_manager() == "grid"
                    assert app.cancel_button.winfo_manager() == "grid"
                    timeout = app.after(5000, lambda: (timed_out.append(True), app.quit()))
                    app.mainloop()
                    app.after_cancel(timeout)
                    assert not timed_out
                    assert completed == ["ready"]
                    assert not app.busy
                else:
                    app._set_operation_running(True, "combine")
                    app.after(600, app.quit)
                    app.mainloop()
                    assert app._operation_strip.winfo_manager() == "pack"
                    app._set_operation_running(False)
                assert not callback_errors
                lines.append(
                    "PASS: Lite window and animated progress initialization "
                    f"(Tk {app.tk.call('info', 'patchlevel')})"
                )
            finally:
                app.destroy()
        lines.append("RESULT: PASS (8 checks)")
        result = 0
    except Exception:
        lines.append("RESULT: FAIL")
        lines.append(traceback.format_exc())
    Path(report_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result
