#!/usr/bin/env python3
"""Lightweight MergeGuru release health check."""

import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import mergeguru_engine as engine  # noqa: E402


def make_source(path, rows, columns=None, top_junk=False, footer_rows=0):
    df = pd.DataFrame(rows)
    if columns:
        df = df[columns]
    if top_junk or footer_rows:
        with open(path, "w", encoding="utf-8", newline="") as f:
            if top_junk:
                f.write("Generated report,,\n")
            df.to_csv(f, index=False)
            for i in range(footer_rows):
                f.write(f"Footer {i + 1},,\n")
    else:
        df.to_csv(path, index=False)


def source(path):
    return {
        "type": "csv",
        "mode": "direct",
        "display_name": path.name,
        "full_path": str(path),
    }


def main():
    work = Path(tempfile.mkdtemp(prefix="mergeguru_health_"))
    try:
        base_rows = [
            {"id": 1, "region": "South", "amount": 100},
            {"id": 2, "region": "North", "amount": 200},
        ]
        extra_rows = [
            {"amount": 300, "region": "South", "id": 3, "note": "extra"},
            {"amount": 400, "region": "West", "id": 4, "note": "extra"},
        ]

        ref = work / "reference.csv"
        shuffled_extra = work / "shuffled_extra.csv"
        junk = work / "junk_rows.csv"

        make_source(ref, base_rows)
        make_source(shuffled_extra, extra_rows, columns=["amount", "region", "id", "note"])
        make_source(junk, base_rows, top_junk=True, footer_rows=1)

        ref_cols = engine.clean_cols(engine.read_header(source(ref)))
        extra_cols = engine.clean_cols(engine.read_header(source(shuffled_extra)))
        assert all(col in extra_cols for col in ref_cols), "extra-column file is missing reference columns"
        assert "note" in extra_cols, "extra column was not detected"

        junk_cols = engine.clean_cols(engine.read_header(source(junk), header_row=2, footer_rows=1))
        assert junk_cols == ref_cols, "header/footer layout handling failed"

        combined = []
        for src_path in (ref, shuffled_extra):
            df = engine.read_full(source(src_path))
            df.columns = engine.clean_cols(df.columns)
            combined.append(df.reindex(columns=ref_cols + ["note"]))
        final = pd.concat(combined, ignore_index=True)
        assert len(final) == 4, "combine row count mismatch"
        assert list(final.columns) == ["id", "region", "amount", "note"], "column order mismatch"

        out = work / "health_output.csv"
        engine.save_dataframe(final, str(out), "CSV")
        assert out.exists(), "export file was not created"

        audit = work / "health_output.audit.txt"
        audit.write_text(f"MergeGuru Audit Report ({engine.APP_VERSION})\n", encoding="utf-8")
        assert audit.exists(), "audit file was not created"

        print(f"health check ok: {work}")
    finally:
        if "--keep" not in sys.argv:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()

