"""Session state for the current MergeGuru Lite workflow."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field

import pandas as pd

from mergeguru_engine import (
    EXCEL_HARD_COLUMN_LIMIT,
    EXCEL_HARD_ROW_LIMIT,
    EXPORT_FORMATS,
    apply_filters,
    source_cache_key,
)


LITE_VERSION = "v3.1 Preview"


def source_identity(source):
    """Return the stable identity used while a source remains in this session."""
    return source_cache_key(source)


def source_directory(source):
    path = source.get("full_path") or source.get("zip_path") or ""
    return os.path.dirname(path) if path else os.getcwd()


def default_output_path(source, export_format="Excel"):
    extension = EXPORT_FORMATS[export_format]["extension"]
    stamp = time.strftime("%Y%m%d_%H%M")
    folder = source_directory(source) if source else os.getcwd()
    return next_available_path(os.path.join(folder, f"MergeGuru_Output_{stamp}{extension}"))


def next_available_path(path):
    """Return path or a numbered sibling without overwriting an existing file."""
    base, extension = os.path.splitext(path)
    candidate = path
    number = 2
    while os.path.exists(candidate):
        candidate = f"{base}_{number:02d}{extension}"
        number += 1
    return candidate


def validate_windows_filename(path):
    name = os.path.basename(path.strip())
    if not name:
        raise ValueError("Choose an output file path.")
    stem = os.path.splitext(name)[0]
    if name != name.strip() or name.endswith("."):
        raise ValueError("Remove spaces or dots from the end of the file name.")
    if re.search(r'[<>:"|?*]', name):
        raise ValueError("The file name contains a character Windows cannot use.")
    reserved = {"CON", "PRN", "AUX", "NUL"}
    reserved.update(f"COM{number}" for number in range(1, 10))
    reserved.update(f"LPT{number}" for number in range(1, 10))
    if stem.upper() in reserved:
        raise ValueError("Choose another file name; this name is reserved by Windows.")


@dataclass
class LiteV3State:
    sources: list = field(default_factory=list)
    excluded_sources: list = field(default_factory=list)
    source_errors: list = field(default_factory=list)
    project_inputs: list = field(default_factory=list)
    project_path: str = ""
    template_key: object = None
    sheet_names: list = field(default_factory=list)
    selected_sheet: str = ""
    allow_extra: bool = True
    different_sheets: bool = True
    fix_layout: bool = False
    header_row: int = 1
    footer_rows: int = 0
    optimize_memory: bool = True
    fast_mode: bool = False
    prepared: bool = False
    validation: dict = field(default_factory=dict)
    final_df: pd.DataFrame | None = None
    extra_columns: list = field(default_factory=list)
    memory_stats: dict | None = None
    duplicate_groups: list = field(default_factory=list)
    filters: list = field(default_factory=list)
    pending_filters: list = field(default_factory=list)
    filtered_df: pd.DataFrame | None = None
    output_format: str = "Excel"
    protected_columns: set = field(default_factory=set)
    output_path: str = ""
    history: list = field(default_factory=list)
    saved_signature: object = None

    @property
    def template_index(self):
        for index, source in enumerate(self.sources):
            if source_identity(source) == self.template_key:
                return index
        return 0 if self.sources else None

    @property
    def template_source(self):
        index = self.template_index
        return self.sources[index] if index is not None else None

    @property
    def columns(self):
        return list(self.final_df.columns) if self.final_df is not None else []

    @property
    def total_rows(self):
        return len(self.final_df) if self.final_df is not None else 0

    @property
    def result_rows(self):
        return len(self.filtered_df) if self.filtered_df is not None else 0

    def set_sources(self, sources, errors=(), project_inputs=()):
        self.sources = list(sources)
        self.excluded_sources = []
        self.source_errors = list(errors)
        self.project_inputs = list(project_inputs)
        self.project_path = ""
        self.template_key = source_identity(self.sources[0]) if self.sources else None
        self.sheet_names = []
        self.selected_sheet = ""
        self.invalidate(clear_filters=True)
        if self.sources:
            self.output_path = default_output_path(self.sources[0], self.output_format)

    def set_template(self, source):
        key = source_identity(source)
        if key != self.template_key:
            self.template_key = key
            self.sheet_names = []
            self.selected_sheet = ""
            self.invalidate(clear_filters=True)

    def exclude(self, sources):
        keys = {source_identity(source) for source in sources}
        removed = [source for source in self.sources if source_identity(source) in keys]
        self.sources = [source for source in self.sources if source_identity(source) not in keys]
        self.excluded_sources.extend(removed)
        if self.template_key in keys:
            self.template_key = source_identity(self.sources[0]) if self.sources else None
            self.sheet_names = []
            self.selected_sheet = ""
        self.invalidate(clear_filters=True)

    def restore_excluded(self):
        if not self.excluded_sources:
            return
        self.sources.extend(self.excluded_sources)
        self.excluded_sources = []
        if self.template_key is None and self.sources:
            self.template_key = source_identity(self.sources[0])
        self.invalidate(clear_filters=True)

    def invalidate(self, clear_filters=True):
        self.prepared = False
        self.validation = {}
        self.final_df = None
        self.filtered_df = None
        self.extra_columns = []
        self.memory_stats = None
        self.saved_signature = None
        if clear_filters:
            self.filters = []
            self.pending_filters = []

    def set_prepared(self, validation, final_df, extra_columns, memory_stats):
        self.validation = validation
        self.final_df = final_df
        self.filtered_df = final_df
        self.extra_columns = list(extra_columns)
        self.memory_stats = memory_stats
        self.filters = []
        self.prepared = True
        self.saved_signature = None
        self.protected_columns.intersection_update(self.columns)
        if not self.protected_columns:
            likely_ids = [column for column in self.columns if "id" in str(column).casefold()]
            if likely_ids:
                self.protected_columns.add(likely_ids[0])

    def filter_problem(self):
        available = set(self.columns)
        for config in self.filters:
            if config.get("column") not in available:
                return f"Column '{config.get('column')}' is unavailable. Edit or remove its filter."
        return ""

    def apply_filters(self):
        problem = self.filter_problem()
        if problem:
            raise ValueError(problem)
        self.filtered_df = apply_filters(self.final_df, self.filters)
        self.saved_signature = None
        return self.filtered_df

    def result_signature(self):
        return (
            tuple(source_identity(source) for source in self.sources),
            self.template_key,
            self.selected_sheet,
            self.allow_extra,
            self.different_sheets,
            self.fix_layout,
            self.header_row,
            self.footer_rows,
            tuple(_freeze_filter(config) for config in self.filters),
            self.output_format,
            tuple(sorted(self.protected_columns)),
            os.path.abspath(self.output_path) if self.output_path else "",
        )

    @property
    def saved(self):
        return self.saved_signature == self.result_signature()

    def validate_export(self):
        if not self.prepared or self.final_df is None:
            raise ValueError("Check & Prepare must finish before exporting.")
        if self.filter_problem():
            raise ValueError(self.filter_problem())
        if self.filtered_df is None:
            raise ValueError("Wait for the filtered result to finish updating.")
        if self.filtered_df.empty:
            raise ValueError("No rows match. Adjust the filters before exporting.")
        raw_path = self.output_path.strip()
        validate_windows_filename(raw_path)
        expected = EXPORT_FORMATS[self.output_format]["extension"]
        if os.path.splitext(raw_path)[1].lower() != expected:
            raise ValueError(f"This format needs a {expected} file name.")
        if self.output_format == "CSV-Unique text":
            selected = self.protected_columns.intersection(self.columns)
            if not selected:
                raise ValueError("Choose at least one text column to preserve.")
        if self.output_format == "Excel":
            if len(self.filtered_df) + 1 > EXCEL_HARD_ROW_LIMIT:
                raise ValueError(
                    "Excel supports at most 1,048,575 data rows plus the header. "
                    "Choose CSV or Parquet for this export."
                )
            if len(self.filtered_df.columns) > EXCEL_HARD_COLUMN_LIMIT:
                raise ValueError(
                    "Excel supports at most 16,384 columns. "
                    "Choose CSV or Parquet for this export."
                )

    def mark_exported(self, path, row_count, file_size, audit_path):
        self.output_path = path
        self.saved_signature = self.result_signature()
        self.history.insert(
            0,
            {
                "path": path,
                "format": self.output_format,
                "rows": row_count,
                "size": file_size,
                "audit_path": audit_path,
                "created": time.strftime("%H:%M:%S"),
            },
        )

    def suggest_next_output(self):
        path = self.output_path or default_output_path(self.template_source, self.output_format)
        base, extension = os.path.splitext(path)
        match = re.search(r"_(\d+)$", base)
        if match:
            base = base[: match.start()] + f"_{int(match.group(1)) + 1:02d}"
        else:
            base += "_02"
        self.output_path = next_available_path(base + extension)
        self.saved_signature = None


def _freeze_filter(config):
    frozen = []
    for key in sorted(config):
        value = config[key]
        frozen.append((key, tuple(value) if isinstance(value, list) else value))
    return tuple(frozen)
