"""Validation and human-readable audit reports for Lite v3."""

from __future__ import annotations

import os
import tempfile
import time

import pandas as pd

from mergeguru_engine import filter_summary, get_dataframe_memory_mb, source_cache_key

from .state import LITE_VERSION


def validation_report_frame(validation):
    rows = []
    for number, result in enumerate(validation.get("results", []), start=1):
        source = result.get("source") or {}
        rows.append(
            {
                "No.": number,
                "File Name": result.get("name", ""),
                "File Type": str(source.get("type", "")).upper(),
                "Source Mode": "ZIP" if source.get("mode") == "zip" else "Direct",
                "Validation Status": str(result.get("status", "")).upper(),
                "Matched Sheet": result.get("sheet") or "",
                "Details": result.get("detail", ""),
                "Missing Columns": ", ".join(result.get("missing") or []),
                "Extra Columns": ", ".join(result.get("extra") or []),
                "Duplicate Columns": ", ".join(result.get("duplicates") or []),
            }
        )
    return pd.DataFrame(rows)


def format_size(size):
    value = float(size or 0)
    for suffix in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or suffix == "TB":
            return f"{value:.0f} B" if suffix == "B" else f"{value:.1f} {suffix}"
        value /= 1024


def write_audit_report(state, output_path, row_count, file_size, elapsed):
    base, _ = os.path.splitext(output_path)
    audit_path = base + ".audit.txt"
    validation = state.validation or {}
    summary = validation.get("summary", {})
    passed = {source_cache_key(source) for source in validation.get("passed_sources", [])}
    memory_mb = get_dataframe_memory_mb(state.final_df)
    folder = os.path.dirname(os.path.abspath(audit_path))
    descriptor, temporary = tempfile.mkstemp(prefix=".mergeguru-audit-", suffix=".txt", dir=folder)
    os.close(descriptor)
    try:
        with open(temporary, "w", encoding="utf-8") as stream:
            stream.write(f"MergeGuru Audit Report ({LITE_VERSION})\n")
            stream.write("=" * 48 + "\n")
            stream.write(f"Created: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            stream.write(f"Reference: {state.template_source.get('display_name', '') if state.template_source else ''}\n")
            if state.selected_sheet:
                stream.write(f"Reference sheet: {state.selected_sheet}\n")
            stream.write("\nOutput\n")
            stream.write(f"Path: {output_path}\n")
            stream.write(f"Format: {state.output_format}\n")
            stream.write(f"Rows: {row_count:,}\n")
            stream.write(f"Columns: {len(state.filtered_df.columns):,}\n")
            stream.write(f"Size: {format_size(file_size)}\n")
            stream.write(f"Save time: {elapsed:.2f}s\n")
            stream.write("\nValidation Summary\n")
            stream.write(f"Passed: {summary.get('pass', 0):,}\n")
            stream.write(f"Warnings: {summary.get('warn', 0):,}\n")
            stream.write(f"Failed/excluded: {summary.get('fail', 0):,}\n")
            stream.write("\nValidation Detail\n")
            for result in validation.get("results", []):
                stream.write(
                    f"- {result.get('name', '')}: {str(result.get('status', '')).upper()}"
                    f" | {result.get('detail', '')}\n"
                )
            stream.write("\nData Summary\n")
            stream.write(f"Combined rows: {state.total_rows:,}\n")
            stream.write(f"Exported rows: {row_count:,}\n")
            stream.write(f"Columns: {len(state.columns):,}\n")
            stream.write(f"In-memory size: {memory_mb:.1f} MB\n" if memory_mb is not None else "In-memory size: unavailable\n")
            stream.write(f"Extra columns appended: {', '.join(state.extra_columns) if state.extra_columns else 'None'}\n")
            stream.write("Deep blank/duplicate-row scans: Not run (performance-safe default)\n")
            stream.write("\nFilters\n")
            if state.filters:
                for config in state.filters:
                    stream.write(f"- {filter_summary(config)}\n")
            else:
                stream.write("- None\n")
            stream.write("\nPossible Duplicate Sources\n")
            if state.duplicate_groups:
                for group in state.duplicate_groups:
                    stream.write(f"- {' / '.join(group)}\n")
            else:
                stream.write("- None detected\n")
            stream.write("\nSources\n")
            for source in state.sources:
                included = source_cache_key(source) in passed
                stream.write(f"- {source.get('display_name', '')} [{'included' if included else 'excluded'}]\n")
            for source in state.excluded_sources:
                stream.write(f"- {source.get('display_name', '')} [excluded by user]\n")
        os.replace(temporary, audit_path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    return audit_path
