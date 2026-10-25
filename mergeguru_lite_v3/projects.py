"""Explicit, portable project presets for MergeGuru Lite."""

from __future__ import annotations

import json
import os
import tempfile
import time


PROJECT_EXTENSION = ".mergeguru.json"
PROJECT_SCHEMA_VERSION = 1
MAX_PROJECT_BYTES = 2 * 1024 * 1024
MAX_PROJECT_INPUTS = 10_000
MAX_PROJECT_FILTERS = 1_000
SUPPORTED_SUFFIXES = {".xlsx", ".csv", ".zip"}


def source_descriptor(source):
    """Return a JSON-safe identity without reading source data."""
    if source.get("mode") == "zip":
        return {
            "mode": "zip",
            "path": os.path.abspath(source.get("zip_path", "")),
            "inner_name": str(source.get("inner_name", "")),
        }
    return {
        "mode": "direct",
        "path": os.path.abspath(source.get("full_path", "")),
    }


def source_matches_descriptor(source, descriptor):
    if not descriptor:
        return False
    actual = source_descriptor(source)
    return _descriptor_key(actual) == _descriptor_key(descriptor)


def derive_project_inputs(sources):
    entries = []
    seen = set()
    for source in sources:
        path = source.get("zip_path") if source.get("mode") == "zip" else source.get("full_path")
        if not path:
            continue
        normalized = os.path.normcase(os.path.abspath(path))
        if normalized in seen:
            continue
        seen.add(normalized)
        entries.append({"kind": "file", "path": os.path.abspath(path)})
    return entries


def build_project_payload(state, app_version):
    filters = state.filters or state.pending_filters
    return {
        "schema_version": PROJECT_SCHEMA_VERSION,
        "product": "MergeGuru Lite",
        "saved_with": app_version,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source_inputs": list(state.project_inputs or derive_project_inputs(state.sources)),
        "template": source_descriptor(state.template_source) if state.template_source else None,
        "excluded_sources": [source_descriptor(source) for source in state.excluded_sources],
        "ignored_outputs": [
            os.path.abspath(item["path"])
            for item in state.history
            if isinstance(item, dict) and item.get("path")
        ],
        "settings": {
            "selected_sheet": state.selected_sheet,
            "allow_extra": state.allow_extra,
            "different_sheets": state.different_sheets,
            "fix_layout": state.fix_layout,
            "header_row": state.header_row,
            "footer_rows": state.footer_rows,
            "optimize_memory": state.optimize_memory,
            "fast_mode": state.fast_mode,
        },
        "filters": [_normalize_filter(config) for config in filters],
        "export": {
            "format": state.output_format,
            "protected_columns": sorted(str(column) for column in state.protected_columns),
            "output_directory": os.path.dirname(os.path.abspath(state.output_path)) if state.output_path else "",
        },
    }


def save_project(path, payload):
    target = os.path.abspath(path)
    if not target.lower().endswith(PROJECT_EXTENSION):
        target += PROJECT_EXTENSION
    folder = os.path.dirname(target)
    os.makedirs(folder, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".mergeguru-project-", suffix=".tmp", dir=folder)
    os.close(descriptor)
    try:
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    return target


def load_project(path):
    target = os.path.abspath(path)
    try:
        size = os.path.getsize(target)
    except OSError as exc:
        raise ValueError("The project file could not be opened.") from exc
    if size > MAX_PROJECT_BYTES:
        raise ValueError("The project file is unexpectedly large and was not opened.")
    try:
        with open(target, "r", encoding="utf-8") as stream:
            payload = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("This is not a readable MergeGuru project file.") from exc
    return _validate_payload(payload, os.path.dirname(target))


def resolve_project_inputs(payload):
    """Resolve saved files/folders to the current supported files."""
    paths = []
    warnings = []
    ignored = {
        os.path.normcase(os.path.abspath(path))
        for path in payload.get("ignored_outputs", [])
    }
    for entry in payload["source_inputs"]:
        path = entry["path"]
        if entry["kind"] == "file":
            if os.path.normcase(os.path.abspath(path)) in ignored:
                continue
            if os.path.isfile(path):
                paths.append(path)
            else:
                warnings.append(f"Missing file: {path}")
            continue
        if not os.path.isdir(path):
            warnings.append(f"Missing folder: {path}")
            continue
        try:
            paths.extend(
                item.path
                for item in os.scandir(path)
                if item.is_file()
                and not item.name.startswith("~$")
                and os.path.splitext(item.name)[1].lower() in SUPPORTED_SUFFIXES
                and os.path.normcase(os.path.abspath(item.path)) not in ignored
            )
        except OSError:
            warnings.append(f"Folder could not be read: {path}")
    return list(dict.fromkeys(os.path.abspath(path) for path in paths)), warnings


def _validate_payload(payload, project_folder):
    if not isinstance(payload, dict):
        raise ValueError("The project file must contain a JSON object.")
    if payload.get("schema_version") != PROJECT_SCHEMA_VERSION:
        raise ValueError("This project version is not supported by this MergeGuru release.")
    if payload.get("product") != "MergeGuru Lite":
        raise ValueError("This project was not created by MergeGuru Lite.")

    raw_inputs = payload.get("source_inputs")
    if not isinstance(raw_inputs, list) or not raw_inputs:
        raise ValueError("The project does not contain any source locations.")
    if len(raw_inputs) > MAX_PROJECT_INPUTS:
        raise ValueError("The project contains too many source locations.")
    source_inputs = [_normalize_input(item, project_folder) for item in raw_inputs]

    settings = payload.get("settings", {})
    if not isinstance(settings, dict):
        raise ValueError("The project settings are invalid.")
    normalized_settings = {
        "selected_sheet": _short_text(settings.get("selected_sheet", ""), "worksheet", 255),
        "allow_extra": _boolean(settings.get("allow_extra", True), "allow-extra setting"),
        "different_sheets": _boolean(settings.get("different_sheets", True), "worksheet matching setting"),
        "fix_layout": _boolean(settings.get("fix_layout", False), "layout setting"),
        "header_row": _bounded_integer(settings.get("header_row", 1), "header row", 1, 10_000),
        "footer_rows": _bounded_integer(settings.get("footer_rows", 0), "footer rows", 0, 10_000),
        "optimize_memory": _boolean(settings.get("optimize_memory", True), "memory setting"),
        "fast_mode": _boolean(settings.get("fast_mode", False), "parallel setting"),
    }

    raw_filters = payload.get("filters", [])
    if not isinstance(raw_filters, list) or len(raw_filters) > MAX_PROJECT_FILTERS:
        raise ValueError("The project filters are invalid or exceed the safe limit.")
    filters = [_normalize_filter(config) for config in raw_filters]

    export = payload.get("export", {})
    if not isinstance(export, dict):
        raise ValueError("The project export settings are invalid.")
    export_format = export.get("format", "Excel")
    if export_format not in {"Excel", "CSV", "CSV-Unique text", "Parquet"}:
        raise ValueError("The project uses an unsupported export format.")
    protected = export.get("protected_columns", [])
    if not isinstance(protected, list) or len(protected) > 10_000:
        raise ValueError("The protected-column selection is invalid.")
    output_directory = export.get("output_directory", "")
    if output_directory:
        output_directory = _resolve_path(output_directory, project_folder)
    ignored_outputs = [
        _resolve_path(item, project_folder)
        for item in _list(payload.get("ignored_outputs", []), "ignored outputs", MAX_PROJECT_INPUTS)
    ]

    return {
        "schema_version": PROJECT_SCHEMA_VERSION,
        "product": "MergeGuru Lite",
        "saved_with": _short_text(payload.get("saved_with", ""), "saved version", 100),
        "saved_at": _short_text(payload.get("saved_at", ""), "saved time", 100),
        "source_inputs": source_inputs,
        "template": _normalize_descriptor(payload.get("template"), project_folder),
        "excluded_sources": [
            _normalize_descriptor(item, project_folder)
            for item in _list(payload.get("excluded_sources", []), "excluded sources", MAX_PROJECT_INPUTS)
        ],
        "ignored_outputs": ignored_outputs,
        "settings": normalized_settings,
        "filters": filters,
        "export": {
            "format": export_format,
            "protected_columns": [_short_text(item, "column", 10_000) for item in protected],
            "output_directory": output_directory,
        },
    }


def _normalize_input(item, project_folder):
    if not isinstance(item, dict) or item.get("kind") not in {"file", "folder"}:
        raise ValueError("A project source location is invalid.")
    return {
        "kind": item["kind"],
        "path": _resolve_path(item.get("path", ""), project_folder),
    }


def _normalize_descriptor(item, project_folder):
    if item is None:
        return None
    if not isinstance(item, dict) or item.get("mode") not in {"direct", "zip"}:
        raise ValueError("A saved source identity is invalid.")
    descriptor = {
        "mode": item["mode"],
        "path": _resolve_path(item.get("path", ""), project_folder),
    }
    if item["mode"] == "zip":
        descriptor["inner_name"] = _short_text(item.get("inner_name", ""), "archive item", 32_767)
    return descriptor


def _normalize_filter(config):
    if not isinstance(config, dict):
        raise ValueError("A saved filter is invalid.")
    column = _short_text(config.get("column", ""), "filter column", 10_000)
    mode = config.get("mode")
    if mode == "category":
        action = config.get("action")
        values = config.get("values")
        if action not in {"include", "exclude"} or not isinstance(values, (list, tuple)) or not values:
            raise ValueError("A category filter is invalid.")
        if len(values) > 20_000:
            raise ValueError("A category filter exceeds the safe selection limit.")
        return {
            "column": column,
            "mode": "category",
            "action": action,
            "values": [_short_text(value, "filter value", 32_767) for value in values],
        }
    if mode == "text":
        operator = config.get("operator")
        if operator not in {"starts_with", "contains", "equals", "not_equals"}:
            raise ValueError("A text filter uses an unsupported operation.")
        return {
            "column": column,
            "mode": "text",
            "operator": operator,
            "value": _short_text(config.get("value", ""), "filter text", 32_767),
        }
    raise ValueError("A saved filter uses an unsupported mode.")


def _resolve_path(value, folder):
    text = _short_text(value, "path", 32_767)
    return os.path.abspath(text if os.path.isabs(text) else os.path.join(folder, text))


def _descriptor_key(descriptor):
    return (
        descriptor.get("mode"),
        os.path.normcase(os.path.abspath(descriptor.get("path", ""))),
        descriptor.get("inner_name", ""),
    )


def _short_text(value, label, maximum):
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError(f"The project {label} is invalid.")
    return value


def _boolean(value, label):
    if not isinstance(value, bool):
        raise ValueError(f"The project {label} is invalid.")
    return value


def _bounded_integer(value, label, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"The project {label} is invalid.")
    return value


def _list(value, label, maximum):
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError(f"The project {label} are invalid.")
    return value
