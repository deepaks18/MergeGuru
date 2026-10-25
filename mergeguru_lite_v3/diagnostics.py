"""Local, privacy-safe operational diagnostics for MergeGuru Lite."""

from __future__ import annotations

import os
import platform
import sys
import tempfile
import threading
import time
from collections import Counter, deque

import psutil


MAX_LOG_BYTES = 512 * 1024
MAX_EVENTS = 200


def default_log_path():
    root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(root, "MergeGuru", "logs", "lite-diagnostics.log")


class DiagnosticRecorder:
    """Keep bounded metadata logs without recording paths, names, or data values."""

    def __init__(self, app_version, log_path=None):
        self.app_version = app_version
        self.log_path = log_path or default_log_path()
        self.started = time.time()
        self.events = deque(maxlen=MAX_EVENTS)
        self._lock = threading.Lock()
        self.record("application_started", frozen=bool(getattr(sys, "frozen", False)))

    def record(self, event, **fields):
        safe_fields = {
            str(key): _safe_scalar(value)
            for key, value in fields.items()
            if _safe_scalar(value) is not None
        }
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        details = " ".join(f"{key}={value}" for key, value in sorted(safe_fields.items()))
        line = f"{stamp} | {event}" + (f" | {details}" if details else "")
        with self._lock:
            self.events.append(line)
            self._append(line)

    def write_report(self, path, state, *, current_step, task_kind="", last_error_type=""):
        target = os.path.abspath(path)
        folder = os.path.dirname(target)
        os.makedirs(folder, exist_ok=True)
        report = self.build_report(
            state,
            current_step=current_step,
            task_kind=task_kind,
            last_error_type=last_error_type,
        )
        descriptor, temporary = tempfile.mkstemp(prefix=".mergeguru-diagnostic-", suffix=".tmp", dir=folder)
        os.close(descriptor)
        try:
            with open(temporary, "w", encoding="utf-8") as stream:
                stream.write(report)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)
        self.record("diagnostic_report_saved")
        return target

    def build_report(self, state, *, current_step, task_kind="", last_error_type=""):
        source_types = Counter(str(source.get("type", "unknown")) for source in state.sources)
        validation = state.validation.get("summary", {}) if state.validation else {}
        memory = psutil.virtual_memory()
        process_mb = psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
        filters = state.filters or state.pending_filters
        lines = [
            "MergeGuru Lite Diagnostic Report",
            "=" * 40,
            f"Created: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Application version: {self.app_version}",
            f"Packaged executable: {bool(getattr(sys, 'frozen', False))}",
            f"Python runtime: {platform.python_version()}",
            f"Operating system: {platform.platform()}",
            f"Session age: {max(0, int(time.time() - self.started))} seconds",
            f"Available memory: {memory.available / (1024 ** 3):.2f} GB",
            f"Process memory: {process_mb:.1f} MB",
            "",
            "Workflow state",
            "-" * 40,
            f"Current step: {current_step}",
            f"Active task: {task_kind or 'None'}",
            f"Last error type: {last_error_type or 'None'}",
            f"Included sources: {len(state.sources)}",
            f"Excluded sources: {len(state.excluded_sources)}",
            f"Source types: {_format_counts(source_types)}",
            f"Prepared: {state.prepared}",
            f"Combined rows: {state.total_rows}",
            f"Combined columns: {len(state.columns)}",
            f"Active filter count: {len(filters)}",
            f"Filtered rows: {state.result_rows}",
            f"Export format: {state.output_format}",
            f"Export completed for current settings: {state.saved}",
            "",
            "Processing settings",
            "-" * 40,
            f"Different worksheet names: {state.different_sheets}",
            f"Allow extra columns: {state.allow_extra}",
            f"Custom header/footer layout: {state.fix_layout}",
            f"Header row: {state.header_row if state.fix_layout else 1}",
            f"Footer rows ignored: {state.footer_rows if state.fix_layout else 0}",
            f"Memory optimization: {state.optimize_memory}",
            f"Controlled parallel reads: {state.fast_mode}",
            "",
            "Validation summary",
            "-" * 40,
            f"Passed: {validation.get('pass', 0)}",
            f"Warnings: {validation.get('warn', 0)}",
            f"Failed/excluded: {validation.get('fail', 0)}",
            "",
            "Recent operational events",
            "-" * 40,
        ]
        lines.extend(self.events or ["No events recorded."])
        lines.extend(
            [
                "",
                "Privacy note",
                "-" * 40,
                "This report intentionally excludes source filenames, filesystem paths,",
                "worksheet names, column names, filter values, and all source/output data.",
                "No diagnostic information is transmitted automatically.",
                "",
            ]
        )
        return "\n".join(lines)

    def _append(self, line):
        try:
            folder = os.path.dirname(self.log_path)
            os.makedirs(folder, exist_ok=True)
            if os.path.exists(self.log_path) and os.path.getsize(self.log_path) >= MAX_LOG_BYTES:
                previous = self.log_path + ".1"
                if os.path.exists(previous):
                    os.remove(previous)
                os.replace(self.log_path, previous)
            with open(self.log_path, "a", encoding="utf-8") as stream:
                stream.write(line + "\n")
        except OSError:
            pass


def _safe_scalar(value):
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.3f}"
    if isinstance(value, str) and value.replace("_", "").replace("-", "").isalnum() and len(value) <= 80:
        return value
    return None


def _format_counts(counts):
    if not counts:
        return "None"
    return ", ".join(f"{name.upper()}={count}" for name, count in sorted(counts.items()))
