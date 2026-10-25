#!/usr/bin/env python3
"""
MergeGuru GUI  -  Wizard-style tool for combining and filtering Excel/CSV files.
Requires:  pandas  openpyxl  (pip install pandas openpyxl)
"""

import sys as _entry_sys


# Every executable invocation uses the canonical Lite launcher. The definitions
# below remain import-only compatibility code for historical checks and Pro.
if __name__ == "__main__":
    from main_gui_lite_v3 import main as _lite_main

    raise SystemExit(_lite_main(_entry_sys.argv))

import sys, os, platform, threading, time, json, subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, filedialog, messagebox
import pandas as pd
from openpyxl import load_workbook
import zipfile
from io import BytesIO
import psutil
import math
from datetime import date

try:
    import pyi_splash
except Exception:
    pyi_splash = None


_SHEET_NAME_CACHE = {}

# =======================================================================
# THEME
# =======================================================================
BG    = "#0d1117"   # main background
SURF  = "#161b22"   # card / sidebar surface
SURF2 = "#21262d"   # hover / subtle surface
BORD  = "#30363d"   # borders
ACC   = "#2f81f7"   # primary accent (blue)
ACCH  = "#58a6ff"   # accent hover
OK    = "#3fb950"   # success green
WARN  = "#d29922"   # warning amber
ERR   = "#f85149"   # error red
FG    = "#e6edf3"   # primary text
MUTE  = "#8b949e"   # muted text

# Font family - pick best available on this OS
_OS = platform.system()
_FAM = "Segoe UI" if _OS == "Windows" else ("SF Pro Display" if _OS == "Darwin" else "Ubuntu")

TF   = (_FAM, 10)
TFS  = (_FAM,  9)
TFB  = (_FAM, 10, "bold")
TFH  = (_FAM, 14, "bold")
TFT  = (_FAM, 22, "bold")
TMO  = ("Consolas" if _OS == "Windows" else "Menlo" if _OS == "Darwin" else "DejaVu Sans Mono", 9)

PAD  = 16
MAX_CATEGORY_UNIQUE_VALUES = 20000
EXCEL_WARNING_ROW_THRESHOLD = 300000
EXCEL_HARD_ROW_LIMIT = 1048576
APP_VERSION = "v2.4"
UNSET = object()
STEP_NAMES = ["Select Data", "Choose Template", "Choose Sheet",
              "Check Files", "Combine & Filter", "Export"]


# =======================================================================
# BACKEND  (same logic as fixed CLI version - no I/O here)
# =======================================================================

def clean_cols(cols):
    return (pd.Index(cols).astype(str).str.strip()
            .str.replace("\n", " ", regex=False).str.replace("\r", " ", regex=False)
            .str.replace(r"\s+", " ", regex=True).str.lower().tolist())


def source_cache_key(source):
    if source["mode"] == "direct":
        return ("direct", source["type"], source["full_path"])
    return ("zip", source["type"], source["zip_path"], source["inner_name"])


def read_csv_flex(src, nrows=None, header=0, skipfooter=0):
    try:
        kwargs = {"nrows": nrows, "encoding": "utf-8", "header": header}
        if skipfooter:
            kwargs["skipfooter"] = skipfooter
            kwargs["engine"] = "python"
        return pd.read_csv(src, **kwargs)
    except UnicodeDecodeError:
        if hasattr(src, "seek"):
            src.seek(0)
        kwargs = {"nrows": nrows, "encoding": "latin-1", "header": header}
        if skipfooter:
            kwargs["skipfooter"] = skipfooter
            kwargs["engine"] = "python"
        return pd.read_csv(src, **kwargs)


def dup_cols(cols):
    d, s = [], set()
    for c in cols:
        if c in s and c not in d:
            d.append(c)
        s.add(c)
    return d


def get_sheet_names(source):
    key = source_cache_key(source)
    cached = _SHEET_NAME_CACHE.get(key)
    if cached is not None:
        return list(cached)

    if source["mode"] == "direct":
        wb = load_workbook(source["full_path"], read_only=True)
        try:
            names = tuple(wb.sheetnames)
        finally:
            wb.close()
    else:
        with zipfile.ZipFile(source["zip_path"], "r") as z:
            with z.open(source["inner_name"]) as f:
                # Zipped XLSX sources must still be fully decompressed for openpyxl.
                wb = load_workbook(BytesIO(f.read()), read_only=True)
                try:
                    names = tuple(wb.sheetnames)
                finally:
                    wb.close()

    _SHEET_NAME_CACHE[key] = names
    return list(names)


def read_zipped_csv(zip_path, inner_name, nrows=None, header=0, skipfooter=0):
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            with z.open(inner_name) as f:
                kwargs = {"nrows": nrows, "encoding": "utf-8", "header": header}
                if skipfooter:
                    kwargs["skipfooter"] = skipfooter
                    kwargs["engine"] = "python"
                return pd.read_csv(f, **kwargs)
    except UnicodeDecodeError:
        with zipfile.ZipFile(zip_path, "r") as z:
            with z.open(inner_name) as f:
                kwargs = {"nrows": nrows, "encoding": "latin-1", "header": header}
                if skipfooter:
                    kwargs["skipfooter"] = skipfooter
                    kwargs["engine"] = "python"
                return pd.read_csv(f, **kwargs)

def read_header(src, sheet=None, header_row=1, footer_rows=0):
    header_idx = max(0, int(header_row) - 1)
    if src["type"] == "xlsx":
        if not sheet:
            raise ValueError(f"Sheet required for: {src['display_name']}")
        if src["mode"] == "direct":
            return pd.read_excel(
                src["full_path"],
                sheet_name=sheet,
                header=header_idx,
                nrows=0,
                skipfooter=footer_rows,
            ).columns
        with zipfile.ZipFile(src["zip_path"], "r") as z:
            with z.open(src["inner_name"]) as f:
                return pd.read_excel(
                    BytesIO(f.read()),
                    sheet_name=sheet,
                    header=header_idx,
                    nrows=0,
                    skipfooter=footer_rows,
                ).columns
    if src["mode"] == "direct":
        return read_csv_flex(src["full_path"], nrows=0, header=header_idx, skipfooter=footer_rows).columns
    return read_zipped_csv(src["zip_path"], src["inner_name"], nrows=0, header=header_idx, skipfooter=footer_rows).columns


def read_full(src, sheet=None, header_row=1, footer_rows=0):
    header_idx = max(0, int(header_row) - 1)
    if src["type"] == "xlsx":
        if not sheet:
            raise ValueError(f"Sheet required for: {src['display_name']}")
        if src["mode"] == "direct":
            return pd.read_excel(
                src["full_path"],
                sheet_name=sheet,
                header=header_idx,
                skipfooter=footer_rows,
            )
        with zipfile.ZipFile(src["zip_path"], "r") as z:
            with z.open(src["inner_name"]) as f:
                return pd.read_excel(
                    BytesIO(f.read()),
                    sheet_name=sheet,
                    header=header_idx,
                    skipfooter=footer_rows,
                )
    if src["mode"] == "direct":
        return read_csv_flex(src["full_path"], header=header_idx, skipfooter=footer_rows)
    return read_zipped_csv(src["zip_path"], src["inner_name"], header=header_idx, skipfooter=footer_rows)


def resolve_sheet(source, ref_sheet):
    if ref_sheet is None:
        raise ValueError("Reference is CSV - cannot validate xlsx source without a sheet.")
    names = get_sheet_names(source)
    if ref_sheet not in names:
        raise ValueError(f"Sheet '{ref_sheet}' not found. Available: {names}")
    return ref_sheet


def apply_filter(df, fc):
    col = fc["column"]
    if fc["mode"] == "category":
        s = df[col].fillna("").astype(str)
        return df[s.isin(fc["values"])] if fc["action"] == "include" else df[~s.isin(fc["values"])]
    if fc["mode"] == "text":
        s, op, v = df[col].fillna("").astype(str), fc["operator"], fc.get("value", "")
        if op == "equals":        return df[s == v]
        if op == "not_equals":    return df[s != v]
        if op == "contains":      return df[s.str.contains(v, case=False, na=False)]
        if op == "starts_with":   return df[s.str.startswith(v, na=False)]
        if op == "paste_include": return df[s.isin(fc["values"])]
        if op == "paste_exclude": return df[~s.isin(fc["values"])]
    if fc["mode"] == "date":
        ds, op = pd.to_datetime(df[col], errors="coerce"), fc["operator"]
        def _d(k):
            d = pd.to_datetime(fc[k], errors="coerce")
            if pd.isna(d): raise ValueError(f"Invalid date '{fc[k]}'")
            return d
        if op == "equals":  return df[ds.dt.date == _d("date1").date()]
        if op == "before":  return df[ds < _d("date1")]
        if op == "after":   return df[ds > _d("date1")]
        if op == "between": return df[(ds >= _d("date1")) & (ds <= _d("date2"))]
    return df


def build_filter_mask(df, fc, string_series=None, date_series=None):
    col = fc["column"]
    if fc["mode"] == "category":
        s = string_series if string_series is not None else df[col].fillna("").astype(str)
        return s.isin(fc["values"]) if fc["action"] == "include" else ~s.isin(fc["values"])
    if fc["mode"] == "text":
        s = string_series if string_series is not None else df[col].fillna("").astype(str)
        op, v = fc["operator"], fc.get("value", "")
        if op == "equals":
            return s == v
        if op == "not_equals":
            return s != v
        if op == "contains":
            return s.str.contains(v, case=False, na=False)
        if op == "starts_with":
            return s.str.startswith(v, na=False)
        if op == "paste_include":
            return s.isin(fc["values"])
        if op == "paste_exclude":
            return ~s.isin(fc["values"])
    if fc["mode"] == "date":
        ds = date_series if date_series is not None else pd.to_datetime(df[col], errors="coerce")
        op = fc["operator"]

        def _d(k):
            d = pd.to_datetime(fc[k], errors="coerce")
            if pd.isna(d):
                raise ValueError(f"Invalid date '{fc[k]}'")
            return d

        if op == "equals":
            return ds.dt.date == _d("date1").date()
        if op == "before":
            return ds < _d("date1")
        if op == "after":
            return ds > _d("date1")
        if op == "between":
            return (ds >= _d("date1")) & (ds <= _d("date2"))
    return pd.Series(True, index=df.index)


def filter_summary(fc):
    """Return a human-readable one-line description of a filter config."""
    col, m = fc["column"], fc["mode"]
    if m == "category":
        vals = ", ".join(fc["values"][:3]) + ("..." if len(fc["values"]) > 3 else "")
        return f"{col}  >  {fc['action'].upper()} [{vals}]"
    if m == "text":
        op  = fc["operator"].replace("_", " ")
        val = fc.get("value") or ", ".join((fc.get("values") or [])[:3])
        return f"{col}  >  {op}: {val}"
    if m == "date":
        op = fc["operator"]
        if op == "between": return f"{col}  >  between {fc['date1']} - {fc['date2']}"
        return f"{col}  >  {op} {fc['date1']}"
    return str(fc)


EXPORT_FORMATS = {
    "Excel": {
        "extension": ".xlsx",
        "filetypes": [("Excel files", "*.xlsx"), ("All files", "*.*")],
    },
    "CSV": {
        "extension": ".csv",
        "filetypes": [("CSV files", "*.csv"), ("All files", "*.*")],
    },
    "CSV-Unique text": {
        "extension": ".csv",
        "filetypes": [("CSV files", "*.csv"), ("All files", "*.*")],
    },
    "Parquet": {
        "extension": ".parquet",
        "filetypes": [("Parquet files", "*.parquet"), ("All files", "*.*")],
    },
}


def detect_export_format(path, fallback="Excel"):
    ext = os.path.splitext(path)[1].lower()
    if ext == EXPORT_FORMATS["CSV-Unique text"]["extension"] and fallback == "CSV-Unique text":
        return fallback
    for fmt, meta in EXPORT_FORMATS.items():
        if fmt != "CSV-Unique text" and ext == meta["extension"]:
            return fmt
    return fallback


def ensure_export_extension(path, fmt):
    base, ext = os.path.splitext(path)
    wanted = EXPORT_FORMATS[fmt]["extension"]
    if ext.lower() == wanted:
        return path
    if ext:
        return base + wanted
    return path + wanted


class CancelledOperation(Exception):
    """Raised when the user cancels a long-running operation."""


def save_dataframe(df, path, fmt, unique_column=None, unique_columns=None,
                   validation_report_df=None, progress_callback=None, cancel_callback=None):
    """
    Save DataFrame to file with optional progress tracking.
    progress_callback: function(percentage, message) - called with 0-100% and status message
    """
    if fmt == "CSV":
        # OK Write CSV in chunks to show progress
        total_rows = len(df)
        chunk_size = max(10000, total_rows // 20)  # ~20 chunks for good granularity
        
        with open(path, 'w', newline='', encoding='utf-8') as f:
            # Write header
            df.head(0).to_csv(f, index=False)
            
            for i in range(0, total_rows, chunk_size):
                if cancel_callback and cancel_callback():
                    raise CancelledOperation("Export cancelled by user.")
                chunk = df.iloc[i:i+chunk_size]
                chunk.to_csv(f, index=False, header=False)
                
                if progress_callback:
                    pct = min(100, int((i + chunk_size) / total_rows * 100))
                    progress_callback(pct, f"Writing... {i + chunk_size:,} of {total_rows:,} rows")
        
        if progress_callback:
            progress_callback(100, f"Completed: {total_rows:,} rows")
        return
        
    if fmt == "CSV-Unique text":
        # OK Add quotes to preserve text columns during conversion
        df_copy = df.copy()
        protected_columns = list(unique_columns or ([unique_column] if unique_column else []))
        for column in protected_columns:
            if column in df_copy.columns:
                df_copy[column] = "'" + df_copy[column].astype(str) + "'"
        
        # Write in chunks with progress
        total_rows = len(df_copy)
        chunk_size = max(10000, total_rows // 20)
        
        with open(path, 'w', newline='', encoding='utf-8') as f:
            # Write header
            df_copy.head(0).to_csv(f, index=False)
            
            for i in range(0, total_rows, chunk_size):
                if cancel_callback and cancel_callback():
                    raise CancelledOperation("Export cancelled by user.")
                chunk = df_copy.iloc[i:i+chunk_size]
                chunk.to_csv(f, index=False, header=False)
                
                if progress_callback:
                    pct = min(100, int((i + chunk_size) / total_rows * 100))
                    progress_callback(pct, f"Writing... {i + chunk_size:,} of {total_rows:,} rows")
        
        if progress_callback:
            progress_callback(100, f"Completed: {total_rows:,} rows")
        return
        
    if fmt == "Excel":
        # The legacy compatibility path delegates to the same atomic,
        # row-streaming writer used by the production Lite application.
        from mergeguru_engine import save_dataframe as save_with_shared_engine

        return save_with_shared_engine(
            df,
            path,
            "Excel",
            unique_column=unique_column,
            unique_columns=unique_columns,
            validation_report_df=validation_report_df,
            progress_callback=progress_callback,
            cancel_callback=cancel_callback,
        )
        
    if fmt == "Parquet":
        try:
            if progress_callback:
                progress_callback(25, "Initializing Parquet writer...")
            if cancel_callback and cancel_callback():
                raise CancelledOperation("Export cancelled by user.")
            
            df.to_parquet(path, index=False)
            
            if progress_callback:
                progress_callback(100, f"Completed: {len(df):,} rows")
        except ImportError as e:
            raise RuntimeError(
                "Parquet export requires an optional dependency like 'pyarrow' or 'fastparquet'."
            ) from e
        return
    raise ValueError(f"Unsupported export format: {fmt}")


# =======================================================================
# PERFORMANCE TIMING HELPERS  (measure bottlenecks)
# =======================================================================

class TimerContext:
    """Simple context manager for measuring operation timing"""
    def __init__(self, operation_name, log_fn=None):
        self.name = operation_name
        self.log_fn = log_fn or print
        self.start = None
        self.elapsed = 0
    
    def __enter__(self):
        self.start = time.time()
        return self
    
    def __exit__(self, *args):
        self.elapsed = time.time() - self.start
        self.log_fn(f"Timer  {self.name}: {self.elapsed:.2f}s")


# =======================================================================
# MEMORY MANAGEMENT HELPERS  (safeguards for large file processing)
# =======================================================================

def get_available_ram_gb():
    """Get available system RAM in GB"""
    try:
        return psutil.virtual_memory().available / (1024 ** 3)
    except Exception:
        return None


def get_process_ram_usage_mb():
    """Get current process RAM usage in MB"""
    try:
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / (1024 ** 2)
    except Exception:
        return None


def estimate_dataframe_size_mb(num_rows, num_cols):
    """Rough estimate of DataFrame memory usage in MB"""
    # Average: ~100 bytes per cell for mixed data types
    # Add 20% overhead for pandas indexing
    return (num_rows * num_cols * 100 / (1024 ** 2)) * 1.2


def get_dataframe_memory_mb(df):
    """Measure a DataFrame's actual memory usage in MB."""
    try:
        return df.memory_usage(deep=True).sum() / (1024 ** 2)
    except Exception:
        return None


def optimize_dataframe_memory(df):
    """
    Reduce DataFrame memory usage without changing visible values.
    Downcasts numeric columns and converts low-cardinality text columns to category.
    """
    optimized = df
    before_mb = get_dataframe_memory_mb(optimized)
    stats = {"int_cols": 0, "float_cols": 0, "category_cols": 0}

    for col in optimized.columns:
        series = optimized[col]
        try:
            if pd.api.types.is_integer_dtype(series):
                optimized[col] = pd.to_numeric(series, downcast="integer")
                stats["int_cols"] += 1
            elif pd.api.types.is_float_dtype(series):
                optimized[col] = pd.to_numeric(series, downcast="float")
                stats["float_cols"] += 1
            elif pd.api.types.is_object_dtype(series):
                non_null = series.dropna()
                if non_null.empty:
                    continue
                unique_count = non_null.nunique(dropna=True)
                if unique_count <= min(1000, max(1, len(series) // 2)):
                    optimized[col] = series.astype("category")
                    stats["category_cols"] += 1
        except Exception:
            continue

    after_mb = get_dataframe_memory_mb(optimized)
    saved_mb = None
    if before_mb is not None and after_mb is not None:
        saved_mb = max(0.0, before_mb - after_mb)

    stats.update({"before_mb": before_mb, "after_mb": after_mb, "saved_mb": saved_mb})
    return optimized, stats


def check_memory_before_combine(total_file_size_bytes, num_files):
    """
    Pre-flight check: Calculate if enough RAM exists to combine files safely.
    Returns: (is_safe: bool, warning_msg: str, available_gb: float, needed_gb: float)
    """
    available_gb = get_available_ram_gb()
    if available_gb is None:
        return True, "", None, None  # Can't check, assume safe
    
    # Estimate: files are typically 30-50% compressible
    # Excel adds overhead, so use 1.3x file size as rough estimate
    estimated_needed_gb = (total_file_size_bytes * 1.3) / (1024 ** 3)
    
    # Safety margin: need at least 2x the data size for temp operations
    safe_threshold_gb = estimated_needed_gb * 2
    
    # If only 1.5GB available, that's cutting it close
    safety_buffer_gb = 1.5
    
    is_safe = available_gb > (safe_threshold_gb + safety_buffer_gb)
    
    warning = ""
    if not is_safe:
        warning = (
            f"Memory Warning:\n\n"
            f"Available RAM: {available_gb:.1f}GB\n"
            f"Estimated needed: {estimated_needed_gb:.1f}GB\n"
            f"Safe threshold: {safe_threshold_gb:.1f}GB (with buffer)\n\n"
            f"Combining may be slow or cause a crash.\n"
            f"Consider:\n"
            f"  - Process fewer files at once\n"
            f"  - Use Parquet format instead of Excel\n"
            f"  - Close other applications to free RAM"
        )
    
    return is_safe, warning, available_gb, estimated_needed_gb


# Both interfaces resolve core processing through this shared engine. The
# definitions above remain temporarily for source compatibility while the UI
# classes are progressively separated from this legacy single-file module.
from mergeguru_engine import (  # noqa: E402
    CancelledOperation,
    SourceChangedError,
    EXPORT_FORMATS,
    build_filter_mask,
    check_memory_before_combine,
    clean_cols,
    detect_export_format,
    dup_cols,
    ensure_export_extension,
    filter_summary,
    get_available_ram_gb,
    get_dataframe_memory_mb,
    get_process_ram_usage_mb,
    get_sheet_names,
    match_sheet_by_headers,
    optimize_dataframe_memory,
    prepare_source_frame,
    provenance_column,
    read_full,
    read_header,
    resolve_sheet,
    save_dataframe,
    source_cache_key,
    source_signature,
)


# =======================================================================
# SHARED WIDGET HELPERS
# =======================================================================

def _btn(parent, text, cmd, kind="primary", **kw):
    colours = {
        "primary": (ACC,   FG,   ACCH,         FG),
        "success": (OK,    BG,   "#4fc160",     BG),
        "danger":  (ERR,   FG,   "#ff6b61",     FG),
        "ghost":   (SURF2, MUTE, BORD,          FG),
        "outline": (BG,    ACC,  SURF2,         ACCH),
    }
    bg, fg, abg, afg = colours.get(kind, colours["primary"])
    # Set defaults that can be overridden by **kw
    defaults = {"padx": 14, "pady": 6, "cursor": "hand2"}
    defaults.update(kw)  # Allow kw to override defaults
    b = tk.Button(parent, text=text, command=cmd,
                  bg=bg, fg=fg, font=TFB, bd=0,
                  activebackground=abg, activeforeground=afg,
                  relief="flat", **defaults)
    return b


def _label(parent, text, font=TF, fg=FG, bg=BG, **kw):
    return tk.Label(parent, text=text, font=font, fg=fg, bg=bg, **kw)


def _sep(parent, horizontal=True, **kw):
    if horizontal:
        return tk.Frame(parent, bg=BORD, height=1, **kw)
    return tk.Frame(parent, bg=BORD, width=1, **kw)


def _entry(parent, textvariable=None, width=None, **kw):
    e = tk.Entry(parent, bg=SURF, fg=FG, font=TMO,
                 insertbackground=FG, relief="flat",
                 highlightthickness=1, highlightbackground=BORD,
                 highlightcolor=ACC, bd=0,
                 textvariable=textvariable, **kw)
    if width:
        e.config(width=width)
    return e


class Tooltip:
    def __init__(self, widget, text):
        self.widget, self.text = widget, text
        self.pending = self.window = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")
        widget.bind("<Destroy>", self._hide, add="+")

    def _schedule(self, _event=None):
        self._hide()
        self.pending = self.widget.after(500, self._show)

    def _show(self):
        self.pending = None
        if not self.widget.winfo_exists():
            return
        self.window = tk.Toplevel(self.widget)
        self.window.overrideredirect(True)
        x = min(self.widget.winfo_rootx(), max(0, self.widget.winfo_screenwidth() - 330))
        y = min(self.widget.winfo_rooty() + self.widget.winfo_height() + 6,
                max(0, self.widget.winfo_screenheight() - 100))
        self.window.geometry(f"+{x}+{y}")
        tk.Label(self.window, text=self.text, font=TFS, bg=SURF2, fg=FG,
                 wraplength=300, justify="left", padx=10, pady=8,
                 relief="solid", borderwidth=1).pack()

    def _hide(self, _event=None):
        if self.pending:
            self.widget.after_cancel(self.pending)
            self.pending = None
        if self.window:
            self.window.destroy()
            self.window = None


def _bind_scroll_routing(window):
    def scroll(event):
        target = event.widget
        if target.winfo_toplevel() != window:
            return
        delta = getattr(event, "delta", 0)
        if delta:
            units = max(1, abs(int(delta / 120))) * (-1 if delta > 0 else 1)
        elif getattr(event, "num", None) in (4, 5):
            units = -3 if event.num == 4 else 3
        else:
            return
        while target is not None and target != window:
            if isinstance(target, (ttk.Treeview, tk.Listbox, tk.Text, ttk.Combobox)):
                return
            if isinstance(target, tk.Canvas):
                if target.yview() != (0.0, 1.0):
                    target.yview_scroll(units, "units")
                    return "break"
            target = target.master
    for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        window.bind(sequence, scroll, add="+")


def _open_path(path):
    try:
        if _OS == "Windows" and hasattr(os, "startfile"):
            os.startfile(path)
        elif _OS == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False


# =======================================================================
# FILTER DIALOG  (modal Toplevel)
# =======================================================================

class FilterDialog(tk.Toplevel):
    def __init__(self, parent, columns, dataframe, on_add, current_filters=None, existing_filter=None):
        super().__init__(parent)
        self.existing_filter = existing_filter
        self.title("Edit Filter" if existing_filter else "Add Filter")
        self.configure(bg=BG)
        self.geometry(f"520x{min(650, self.winfo_screenheight() - 120)}")
        self.minsize(440, 400)
        self.resizable(True, True)
        self.grab_set()
        self.transient(parent)

        self.columns  = columns
        self.df       = dataframe  # already filtered by dependent filters from caller
        self.on_add   = on_add
        self.cat_vals = []
        self.current_filters = current_filters or []  # For reference only
        self._cat_search_after_id = None

        self._build()
        _bind_scroll_routing(self)
        self.bind("<Escape>", lambda _e: self._cleanup())
        # OK Fix mouse wheel leak: unbind on close
        self.protocol("WM_DELETE_WINDOW", self._cleanup)
        self.wait_window()

    def _cleanup(self):
        if self._cat_search_after_id:
            try:
                self.after_cancel(self._cat_search_after_id)
            except Exception:
                pass
            self._cat_search_after_id = None
        self.destroy()

    # -- layout ------------------------------------------------
    def _build(self):
        # Create a main scrollable content area
        main_frame = tk.Frame(self, bg=BG)
        main_frame.pack(fill="both", expand=True)

        # Inner scrollable canvas for top content
        inner_canvas = tk.Canvas(main_frame, bg=BG, highlightthickness=0)
        inner_scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=inner_canvas.yview)
        inner_scrollable = tk.Frame(inner_canvas, bg=BG)
        
        inner_scrollable.bind(
            "<Configure>",
            lambda e: inner_canvas.configure(scrollregion=inner_canvas.bbox("all"))
        )
        
        content_window = inner_canvas.create_window((0, 0), window=inner_scrollable, anchor="nw")
        inner_canvas.bind("<Configure>", lambda e: inner_canvas.itemconfigure(content_window, width=e.width))
        inner_canvas.configure(yscrollcommand=inner_scrollbar.set)
        
        # Column selector
        top = tk.Frame(inner_scrollable, bg=BG, padx=PAD, pady=PAD)
        top.pack(fill="x")
        _label(top, "Column", TFB).pack(anchor="w")
        initial_col = self.existing_filter["column"] if self.existing_filter else self.columns[0]
        self.col_var = tk.StringVar(value=initial_col)
        cb = ttk.Combobox(top, textvariable=self.col_var,
                          values=self.columns, state="readonly")
        cb.pack(fill="x", pady=(4, 0))
        cb.bind("<<ComboboxSelected>>", self._refresh)

        _sep(inner_scrollable).pack(fill="x")

        # Filter type  
        mid = tk.Frame(inner_scrollable, bg=BG, padx=PAD, pady=PAD)
        mid.pack(fill="x")
        _label(mid, "Filter type", TFB).pack(anchor="w")
        initial_mode = self.existing_filter["mode"] if self.existing_filter else "category"
        self.mode_var = tk.StringVar(value=initial_mode)
        for lbl, val in [("Category  (pick values)", "category"),
                         ("Text / ID",               "text"),
                         ("Date",                    "date")]:
            tk.Radiobutton(mid, text=lbl, variable=self.mode_var, value=val,
                           bg=BG, fg=FG, selectcolor=SURF2,
                           activebackground=BG, font=TF,
                           command=self._refresh).pack(anchor="w", pady=1)

        _sep(inner_scrollable).pack(fill="x")

        # Dynamic config area
        self.cfg = tk.Frame(inner_scrollable, bg=BG, padx=PAD, pady=PAD)
        self.cfg.pack(fill="x")

        inner_canvas.pack(side="left", fill="both", expand=True)
        inner_scrollbar.pack(side="right", fill="y")

        # Fixed footer at bottom (ALWAYS visible)
        _sep(self).pack(fill="x")
        foot = tk.Frame(self, bg=BG, padx=PAD, pady=10)
        foot.pack(fill="x")
        _btn(foot, "Cancel",     self._cleanup, "ghost"  ).pack(side="right", padx=(6, 0))
        _btn(foot, "Save Filter" if self.existing_filter else "Add Filter", self._confirm, "primary").pack(side="right")

        self._refresh()

    def _refresh(self, *_):
        if self._cat_search_after_id:
            self.after_cancel(self._cat_search_after_id)
            self._cat_search_after_id = None
        for w in self.cfg.winfo_children():
            w.destroy()
        mode = self.mode_var.get()
        col  = self.col_var.get()
        if mode == "category":
            self._build_category(col)
        elif mode == "text":
            self._build_text()
        elif mode == "date":
            self._build_date()

    def _get_existing_values(self):
        if not self.existing_filter:
            return None
        if self.existing_filter.get("mode") != self.mode_var.get():
            return None
        if self.existing_filter.get("column") != self.col_var.get():
            return None
        return self.existing_filter

    def _looks_like_date_column(self, col):
        try:
            series = self.df[col].dropna()
            if series.empty:
                return False
            sample = series.astype(str).head(100)
            parsed = pd.to_datetime(sample, errors="coerce")
            return (parsed.notna().sum() / max(len(sample), 1)) >= 0.6
        except Exception:
            return False

    def _render_mode_hint(self, mode, col):
        if mode == "category":
            if not self.cat_vals:
                suggestion = "Date" if self._looks_like_date_column(col) else "Text / ID"
                _label(
                    self.cfg,
                    f"This column has no non-empty values after the current filters. Try {suggestion} only if new rows are expected, or choose another column.",
                    TFS,
                    fg=MUTE,
                    wraplength=440,
                    justify="left",
                ).pack(anchor="w", pady=(0, 6))
            elif len(self.cat_vals) > MAX_CATEGORY_UNIQUE_VALUES:
                suggestion = "Date" if self._looks_like_date_column(col) else "Text / ID"
                _label(
                    self.cfg,
                    f"Category pick-list is hidden because this column has {len(self.cat_vals):,} unique values. {suggestion} is the better fit here.",
                    TFS,
                    fg=MUTE,
                    wraplength=440,
                    justify="left",
                ).pack(anchor="w", pady=(0, 6))
        elif mode == "date" and not self._looks_like_date_column(col):
            _label(
                self.cfg,
                "This column does not strongly look like a date column. If matching feels off, try Text / ID instead.",
                TFS,
                fg=MUTE,
                wraplength=440,
                justify="left",
            ).pack(anchor="w", pady=(0, 8))

    # -- category ----------------------------------------------
    def _build_category(self, col):
        f = self.cfg
        try:
            self.cat_vals = sorted(self.df[col].dropna().astype(str).unique().tolist())
        except Exception:
            self.cat_vals = []
        
        # Initialize persistent selection if first time, otherwise keep it
        # (it gets preserved across search operations)
        if not hasattr(self, '_persistent_selection'):
            self._persistent_selection = set()
        
        # Clear selection if user switched to a different column
        if hasattr(self, '_current_category_col') and self._current_category_col != col:
            self._persistent_selection.clear()
        self._current_category_col = col

        if not self.cat_vals:
            _label(f, "No values found in this column.", fg=WARN).pack(anchor="w")
            self._render_mode_hint("category", col)
            return
        if len(self.cat_vals) > MAX_CATEGORY_UNIQUE_VALUES:
            _label(f, f"Too many unique values ({len(self.cat_vals)}) - use Text/ID filter.",
                   fg=WARN).pack(anchor="w")
            self._render_mode_hint("category", col)
            return

        existing = self._get_existing_values()
        _label(f, "Action", TFB).pack(anchor="w")
        self.cat_action = tk.StringVar(value=(existing or {}).get("action", "include"))
        for lbl, v in [("Include selected", "include"), ("Exclude selected", "exclude")]:
            tk.Radiobutton(f, text=lbl, variable=self.cat_action, value=v,
                           bg=BG, fg=FG, selectcolor=SURF2,
                           activebackground=BG, font=TF).pack(anchor="w")

        # Search box for filtering values
        _label(f, "Search values (type to filter)", TFB).pack(anchor="w", pady=(10, 2))
        search_frame = tk.Frame(f, bg=BG)
        search_frame.pack(fill="x", pady=(0, 6))
        self.cat_search = _entry(search_frame)
        self.cat_search.pack(fill="x", ipady=4)
        self.cat_search.bind("<KeyRelease>", self._filter_category_list)

        # Action buttons row
        btn_frame = tk.Frame(f, bg=BG)
        btn_frame.pack(fill="x", pady=(0, 8))
        _btn(btn_frame, "Select visible", lambda: self._cat_select_all(True), "primary", padx=8, pady=4).pack(side="left", padx=(0, 4))
        _btn(btn_frame, "Clear visible", lambda: self._cat_select_all(False), "ghost", padx=8, pady=4).pack(side="left", padx=2)
        _btn(btn_frame, "Invert visible", self._cat_invert_selection, "ghost", padx=8, pady=4).pack(side="left", padx=2)
        self._cat_count_label = tk.Label(btn_frame, text="0 selected", font=TFS, bg=BG, fg=MUTE)
        self._cat_count_label.pack(side="right")

        self._cat_selected_preview = _label(f, "", TFS, fg=MUTE, wraplength=420, justify="left")
        self._cat_selected_preview.pack(anchor="w", pady=(2, 6))
        _label(f, "Click a value to tick or untick it. Space toggles the focused row.", TFS, fg=MUTE, wraplength=420).pack(anchor="w", pady=(0, 4))

        list_frame = tk.Frame(f, bg=BG, height=220)
        list_frame.pack(fill="both", expand=False, pady=(0, 4))
        list_frame.pack_propagate(False)

        self.cat_listbox = ttk.Treeview(list_frame, columns=("checked", "value"),
                                       show="headings", selectmode="browse", height=7)
        self.cat_listbox.heading("checked", text="Pick")
        self.cat_listbox.heading("value", text="Value")
        self.cat_listbox.column("checked", width=46, stretch=False, anchor="center")
        self.cat_listbox.column("value", width=300, stretch=True)
        self.cat_listbox.tag_configure("checked", foreground=OK)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.cat_listbox.yview)
        self.cat_listbox.configure(yscrollcommand=scrollbar.set)
        self.cat_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.cat_visible_values = list(self.cat_vals)
        self._cat_visible_set = set(self.cat_visible_values)
        self._persistent_selection = set((existing or {}).get("values", []))
        self.cat_listbox.bind("<Button-1>", self._toggle_category_row)
        self.cat_listbox.bind("<space>", self._toggle_category_row)

        # Update count and focus on search
        self._refresh_category_listbox()
        self._update_cat_count()
        self.cat_search.focus()

    def _filter_category_list(self, *_):
        """Debounce search redraws for large category lists."""
        if self._cat_search_after_id:
            self.after_cancel(self._cat_search_after_id)
        self._cat_search_after_id = self.after(150, self._apply_category_filter)

    def _apply_category_filter(self):
        """Filter the listbox based on search input."""
        self._cat_search_after_id = None
        search_text = self.cat_search.get().lower().strip()

        if not search_text:
            self.cat_visible_values = list(self.cat_vals)
        else:
            self.cat_visible_values = [v for v in self.cat_vals if search_text in v.lower()]
        self._cat_visible_set = set(self.cat_visible_values)
        self._refresh_category_listbox()

    def _update_cat_count(self):
        """Update the selection count display."""
        count = len(self._persistent_selection)
        self._cat_count_label.config(text=f"{count} selected")
        if hasattr(self, "_cat_selected_preview"):
            sample = ", ".join(sorted(self._persistent_selection)[:3])[:110]
            self._cat_selected_preview.config(text=f"Selected: {sample}" if count else "No values selected yet.")

    def _refresh_category_listbox(self):
        self.cat_listbox.delete(*self.cat_listbox.get_children())
        for idx, val in enumerate(self.cat_visible_values):
            checked = val in self._persistent_selection
            self.cat_listbox.insert("", "end", iid=str(idx),
                values=("[x]" if checked else "[ ]", val), tags=("checked",) if checked else ())
        self._update_cat_count()

    def _toggle_category_row(self, event):
        row = self.cat_listbox.focus() if event.keysym == "space" else self.cat_listbox.identify_row(event.y)
        if not row:
            return
        val = self.cat_visible_values[int(row)]
        if val in self._persistent_selection:
            self._persistent_selection.remove(val)
        else:
            self._persistent_selection.add(val)
        checked = val in self._persistent_selection
        self.cat_listbox.item(row, values=("[x]" if checked else "[ ]", val), tags=("checked",) if checked else ())
        self.cat_listbox.focus(row)
        self.cat_listbox.selection_set(row)
        self._update_cat_count()
        return "break"

    def _cat_select_all(self, state):
        """Select or deselect all visible values."""
        if state:
            self._persistent_selection.update(self._cat_visible_set)
        else:
            self._persistent_selection.difference_update(self._cat_visible_set)
        self._refresh_category_listbox()

    def _cat_invert_selection(self):
        """Invert selection of visible values."""
        new_selection = set(self._persistent_selection)
        for val in self._cat_visible_set:
            if val in new_selection:
                new_selection.remove(val)
            else:
                new_selection.add(val)
        self._persistent_selection = new_selection
        self._refresh_category_listbox()

    # -- text --------------------------------------------------
    def _build_text(self):
        f = self.cfg
        existing = self._get_existing_values()
        self._render_mode_hint("text", self.col_var.get())
        _label(f, "Operator", TFB).pack(anchor="w")
        self.txt_op = tk.StringVar(value=(existing or {}).get("operator", "equals"))
        for lbl, v in [("Equals",                       "equals"),
                       ("Not equals",                   "not_equals"),
                       ("Contains",                     "contains"),
                       ("Starts with",                  "starts_with"),
                       ("Include list  (comma-sep)",    "paste_include"),
                       ("Exclude list  (comma-sep)",    "paste_exclude")]:
            tk.Radiobutton(f, text=lbl, variable=self.txt_op, value=v,
                           bg=BG, fg=FG, selectcolor=SURF2,
                           activebackground=BG, font=TF).pack(anchor="w", pady=1)
        _label(f, "Value", TFB).pack(anchor="w", pady=(10, 2))
        self.txt_val = _entry(f)
        if existing:
            if "value" in existing:
                self.txt_val.insert(0, existing.get("value", ""))
            elif "values" in existing:
                self.txt_val.insert(0, ",".join(existing.get("values", [])))
        self.txt_val.pack(fill="x", ipady=4)
    # -- date --------------------------------------------------
    def _build_date(self):
        f = self.cfg
        existing = self._get_existing_values()
        self._render_mode_hint("date", self.col_var.get())
        _label(f, "Operator", TFB).pack(anchor="w")
        self.date_op = tk.StringVar(value=(existing or {}).get("operator", "equals"))
        for lbl, v in [("Equals",             "equals"),
                       ("Before (exclusive)", "before"),
                       ("After  (exclusive)", "after"),
                       ("Between (inclusive)","between")]:
            tk.Radiobutton(f, text=lbl, variable=self.date_op, value=v,
                           bg=BG, fg=FG, selectcolor=SURF2,
                           activebackground=BG, font=TF,
                           command=self._toggle_date2).pack(anchor="w", pady=1)

        _label(f, "Date 1  (YYYY-MM-DD)", TFB).pack(anchor="w", pady=(10, 2))
        self.date1 = _entry(f)
        self.date1.insert(0, (existing or {}).get("date1", date.today().replace(month=1, day=1).isoformat()))
        self.date1.pack(fill="x", ipady=4)

        self._date2_lbl = _label(f, "Date 2  (YYYY-MM-DD)", TFB)
        self._date2_lbl.pack(anchor="w", pady=(8, 2))
        self.date2 = _entry(f)
        self.date2.insert(0, (existing or {}).get("date2", date.today().isoformat()))
        self.date2.pack(fill="x", ipady=4)
        self._toggle_date2()

    def _toggle_date2(self, *_):
        if hasattr(self, "date_op") and hasattr(self, "date2"):
            show = self.date_op.get() == "between"
            st = "normal" if show else "disabled"
            self.date2.config(state=st)
            fg = FG if show else MUTE
            self._date2_lbl.config(fg=fg)

    # -- confirm -----------------------------------------------
    def _confirm(self):
        mode, col = self.mode_var.get(), self.col_var.get()

        if mode == "category":
            if not self.cat_vals or len(self.cat_vals) > MAX_CATEGORY_UNIQUE_VALUES:
                suggestion = "Date" if self._looks_like_date_column(col) else "Text / ID"
                messagebox.showwarning(
                    "Category filter unavailable",
                    f"Category pick-list is not available for '{col}'.\n\nTry {suggestion} for this column instead.",
                    parent=self,
                )
                return
            vals = sorted(self._persistent_selection)
            if not vals:
                messagebox.showwarning("No selection", "Select at least one value.", parent=self)
                return
            fc = {"mode": "category", "column": col,
                  "action": self.cat_action.get(), "values": vals}

        elif mode == "text":
            v  = self.txt_val.get().strip()
            op = self.txt_op.get()
            if op in ("paste_include", "paste_exclude"):
                vals = [x.strip() for x in v.split(",") if x.strip()]
                if not vals:
                    messagebox.showwarning("Empty list", "Enter at least one value.", parent=self)
                    return
                fc = {"mode": "text", "column": col, "operator": op, "values": vals}
            else:
                fc = {"mode": "text", "column": col, "operator": op, "value": v}

        elif mode == "date":
            op = self.date_op.get()
            d1 = self.date1.get().strip()
            if not d1:
                messagebox.showwarning("Missing date", "Enter Date 1.", parent=self)
                return
            if op == "between":
                d2 = self.date2.get().strip()
                if not d2:
                    messagebox.showwarning("Missing date", "Enter Date 2.", parent=self)
                    return
                fc = {"mode": "date", "column": col, "operator": op, "date1": d1, "date2": d2}
            else:
                fc = {"mode": "date", "column": col, "operator": op, "date1": d1}
            try:
                first = date.fromisoformat(d1)
                if first.isoformat() != d1:
                    raise ValueError("Use YYYY-MM-DD, including the hyphens.")
                if op == "between" and date.fromisoformat(d2) < first:
                    raise ValueError("The end date must be on or after the start date.")
                if op == "between" and date.fromisoformat(d2).isoformat() != d2:
                    raise ValueError("Use YYYY-MM-DD, including the hyphens.")
            except ValueError as exc:
                messagebox.showwarning("Invalid date", f"Use valid dates in YYYY-MM-DD format.\n\n{exc}", parent=self)
                return
        else:
            return

        try:
            build_filter_mask(self.df.head(1), fc)
        except Exception as exc:
            messagebox.showwarning("Invalid filter", f"Correct the filter before saving.\n\n{exc}", parent=self)
            return
        self.on_add(fc)
        self._cleanup()


class ExportSuccessDialog(tk.Toplevel):
    def __init__(self, parent, out_path, out_fmt, row_count, file_size_text, filter_text="", on_change_filters=None):
        super().__init__(parent)
        self.parent = parent
        self.out_path = out_path
        self.out_dir = os.path.dirname(out_path) or "."
        self.on_change_filters = on_change_filters
        self.title("Export Complete")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        body = tk.Frame(self, bg=BG, padx=PAD, pady=PAD)
        body.pack(fill="both", expand=True)
        _label(body, "Export complete", TFH).pack(anchor="w")
        _label(
            body,
            f"{row_count:,} rows saved as {out_fmt}",
            TFS,
            fg=MUTE,
        ).pack(anchor="w", pady=(4, 12))

        summary = tk.Frame(body, bg=SURF, padx=12, pady=10, highlightthickness=1, highlightbackground=BORD)
        summary.pack(fill="x")
        _label(summary, "File", TFS, fg=MUTE, bg=SURF).pack(anchor="w")
        _label(summary, os.path.basename(out_path), TFB, bg=SURF).pack(anchor="w")
        _label(summary, out_path, TFS, fg=MUTE, bg=SURF, wraplength=460, justify="left").pack(anchor="w", pady=(2, 8))
        _label(summary, f"Size: {file_size_text}", TFS, fg=MUTE, bg=SURF).pack(anchor="w")
        if filter_text:
            _label(summary, filter_text, TFS, fg=MUTE, bg=SURF, wraplength=460, justify="left").pack(anchor="w", pady=(4, 0))

        actions = tk.Frame(body, bg=BG)
        actions.pack(fill="x", pady=(12, 0))
        _btn(actions, "Open File", self._open_file, "primary").pack(side="left")
        _btn(actions, "Open Folder", self._open_folder, "ghost").pack(side="left", padx=(8, 0))
        if self.on_change_filters is not None:
            _btn(actions, "Change Filters", self._change_filters, "outline").pack(side="left", padx=(8, 0))
        _btn(actions, "Export Again", self.destroy, "outline").pack(side="left", padx=(8, 0))
        _btn(actions, "Close", self.destroy, "ghost").pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.wait_window()

    def _open_file(self):
        if not _open_path(self.out_path):
            messagebox.showwarning("Open failed", "Could not open the exported file.", parent=self)

    def _open_folder(self):
        if not _open_path(self.out_dir):
            messagebox.showwarning("Open failed", "Could not open the export folder.", parent=self)

    def _change_filters(self):
        self.destroy()
        if self.on_change_filters is not None:
            self.parent.after(50, self.on_change_filters)


# =======================================================================
# MAIN APPLICATION WINDOW
# =======================================================================

class MergeGuruApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title(f"MergeGuru {APP_VERSION}")
        self.geometry("980x640")
        self.minsize(760, 520)
        self.configure(bg=BG)

        # -- shared state -----------------------------------------
        self.folder        = ""
        self.selected_file_paths = []
        self.all_sources   = []
        self.ref_idx       = 0           # index into all_sources
        self.selected_sheet = None
        self.ref_columns   = []
        self.passed_srcs   = []
        self.filters       = []
        self.optimize_memory_enabled = True
        self.deep_quality_checks_enabled = False
        self.fast_combine_enabled = False
        self._advanced_options_expanded = False
        self.layout_fix_enabled = False
        self.auto_match_sheet_enabled = False
        self.header_row_num = 1
        self.footer_rows_to_ignore = 0
        self.auto_advance_after_validation = False
        self.allow_extra_columns = False
        self.extra_columns_found = []
        self.final_df      = None        # combined df (populated in filter step)
        self._last_memory_optimization = None
        self._validation_started_at = None
        self._validation_timer_id = None
        self._validation_total = 0
        self._validation_done = 0
        self._validation_summary = {}
        self._validation_results = []
        self._source_sheet_map = {}
        self._data_quality_summary = {}
        self._duplicate_source_warnings = []
        self._export_history = []
        self._cancel_combine_requested = False
        self._cancel_export_requested = False
        self._operation_running = False
        self._operation_label = ""
        self._operation_timer_id = None
        self._operation_controls = []
        self._disabled_operation_controls = []
        self._operation_percent = 0
        self._operation_eta = None
        self._operation_detail = ""
        self._operation_files = {}
        self._operation_cancel_pending = False
        self._operation_last_progress = time.monotonic()
        self._cancel_validation_requested = False
        self._last_export_signature = None
        self._data_revision = 0
        self._auto_open_output = False
        self._filtered_cache_key = None
        self._filtered_df_cache = None
        self._filter_stats_cache = []
        self._string_series_cache = {}
        self._date_series_cache = {}
        self._perf_log = []
        
        # -- timing tracking --------------------------------------
        self.stage_start_time = time.time()  # Start time of current stage
        self.stage_times = {}  # Dictionary to store time per stage

        self._apply_style()
        self._build_layout()
        self.nav_to(0)
        self.protocol("WM_DELETE_WINDOW", self._request_close)
        self.bind("<Alt-n>", lambda _e: self._keyboard_next())
        self.bind("<Alt-b>", lambda _e: self._on_back())
        self.bind("<Control-o>", lambda _e: self._keyboard_browse())

    # -- ttk style ---------------------------------------------
    def _apply_style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".",
                    background=BG, foreground=FG, font=TF,
                    troughcolor=SURF2, bordercolor=BORD,
                    lightcolor=BORD, darkcolor=BORD,
                    focuscolor=ACC, selectbackground=ACC, selectforeground=FG)
        s.configure("TCombobox",
                    fieldbackground=SURF, background=SURF,
                    foreground=FG, arrowcolor=MUTE, padding=4)
        s.map("TCombobox", fieldbackground=[("readonly", SURF)])
        s.configure("Step.Horizontal.TProgressbar",
                    troughcolor=SURF2, background=ACC,
                    thickness=3, borderwidth=0)
        s.configure("File.Horizontal.TProgressbar",
                    troughcolor=SURF2, background=OK,
                    thickness=8, borderwidth=0)
        s.configure("Treeview",
                    background=SURF, fieldbackground=SURF,
                    foreground=FG, rowheight=28)
        s.configure("Treeview.Heading",
                    background=SURF2, foreground=MUTE,
                    font=TFS, relief="flat")
        s.map("Treeview",
              background=[("selected", ACC)],
              foreground=[("selected", FG)])

    # -- layout skeleton ----------------------------------------
    def _build_layout(self):
        # -- top header ---------------------------------------
        hdr = tk.Frame(self, bg=SURF, height=52)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text=f"MergeGuru {APP_VERSION}", font=TFH, bg=SURF, fg=FG).pack(side="left", padx=PAD)
        self._hdr_step = tk.Label(hdr, text="", font=TFS, bg=SURF, fg=MUTE)
        self._hdr_step.pack(side="right", padx=PAD)
        _sep(self).pack(fill="x")

        # -- overall step progress bar -------------------------
        self._step_prog = ttk.Progressbar(self, style="Step.Horizontal.TProgressbar",
                                          mode="determinate", maximum=len(STEP_NAMES))
        self._step_prog.pack(fill="x")

        # -- body  (sidebar + content) -------------------------
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)

        # sidebar
        self._sidebar = tk.Frame(body, bg=SURF, width=200)
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)

        tk.Frame(body, bg=BORD, width=1).pack(side="left", fill="y")  # vertical divider

        # content
        content_shell = tk.Frame(body, bg=BG)
        content_shell.pack(side="left", fill="both", expand=True)
        self._content_canvas = tk.Canvas(content_shell, bg=BG, highlightthickness=0)
        self._content_vsb = ttk.Scrollbar(content_shell, orient="vertical", command=self._content_canvas.yview)
        self._content_canvas.configure(yscrollcommand=self._content_vsb.set)
        self._content_canvas.pack(side="left", fill="both", expand=True)
        self._content_vsb.pack(side="right", fill="y")
        self._content = tk.Frame(self._content_canvas, bg=BG)
        self._content_window = self._content_canvas.create_window((0, 0), window=self._content, anchor="nw")
        self._content.bind("<Configure>", self._on_content_configure)
        self._content_canvas.bind("<Configure>", self._on_content_canvas_configure)
        self._bind_content_mousewheel()

        # -- footer (status + nav) -----------------------------
        self._footer_divider = _sep(self)
        self._footer_divider.pack(fill="x")
        foot = tk.Frame(self, bg=SURF, pady=10)
        foot.pack(fill="x")

        nav = tk.Frame(foot, bg=SURF)
        self._footer_nav = nav
        nav.pack(side="right", padx=(8, PAD))
        self._btn_next = _btn(nav, "Next ->", self._on_next, "primary")
        self._btn_next.pack(side="right")
        self._close_without_export_btn = _btn(
            nav,
            "Close Without Export",
            self._close_without_export,
            "ghost",
        )
        self._close_without_export_btn.pack(side="right", padx=(0, 6))
        self._close_without_export_btn.pack_forget()
        self._btn_back = _btn(nav, "<- Back", self._on_back, "ghost")
        self._btn_back.pack(side="right", padx=(0, 6))
        Tooltip(self._btn_next, "Complete this step before continuing. Keyboard shortcut: Alt+N.")
        Tooltip(self._btn_back, "Go to the previous step. Keyboard shortcut: Alt+B.")

        self._status_lbl = tk.Label(
            foot,
            text="Welcome - select a folder or files to begin.",
            font=TFS,
            bg=SURF,
            fg=MUTE,
            anchor="w",
            justify="left",
        )
        self._status_lbl.pack(side="left", fill="x", expand=True, padx=PAD)
        self._status_lbl.bind(
            "<Configure>",
            lambda e: self._status_lbl.config(wraplength=max(260, e.width - 12)),
        )
        self._operation_strip = tk.Frame(self, bg=SURF2, padx=PAD, pady=8)
        self._operation_strip.columnconfigure(0, weight=1)
        self._operation_title = tk.Label(self._operation_strip, text="", font=TFB, fg=FG, bg=SURF2, anchor="w")
        self._operation_title.grid(row=0, column=0, sticky="ew")
        self._operation_cancel_btn = _btn(self._operation_strip, "Cancel", self._cancel_active_operation,
                                          "danger", padx=10, pady=4)
        self._operation_cancel_btn.grid(row=0, column=2, rowspan=2, padx=(12, 0))
        self._operation_activity = ttk.Progressbar(self._operation_strip, mode="indeterminate", length=85)
        self._operation_activity.grid(row=0, column=1, padx=(10, 0))
        self._operation_bar = ttk.Progressbar(self._operation_strip, maximum=100, mode="determinate")
        self._operation_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self._operation_caption = tk.Label(self._operation_strip, text="", font=TFS, fg=FG, bg=SURF2, anchor="w")
        self._operation_caption.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        self._operation_caption.bind("<Configure>", lambda e: self._operation_caption.config(wraplength=max(200, e.width - 8)))

        # build sidebar step indicators
        self._step_widgets = []
        for i, name in enumerate(STEP_NAMES):
            row = tk.Frame(self._sidebar, bg=SURF)
            row.pack(fill="x")
            accent_bar = tk.Frame(row, bg=SURF, width=3)
            accent_bar.pack(side="left", fill="y")
            inner = tk.Frame(row, bg=SURF, padx=10, pady=12)
            inner.pack(side="left", fill="x", expand=True)
            num  = tk.Label(inner, text=f"{i+1:02d}", font=("Consolas", 9), bg=SURF, fg=MUTE)
            num.pack(anchor="w")
            name_lbl = tk.Label(inner, text=name, font=TFS, bg=SURF, fg=MUTE, anchor="w")
            name_lbl.pack(anchor="w")
            self._step_widgets.append((row, inner, accent_bar, num, name_lbl))

    def _on_content_configure(self, _event=None):
        canvas_height = max(1, self._content_canvas.winfo_height())
        content_height = max(canvas_height, self._content.winfo_reqheight())
        self._content_canvas.itemconfigure(self._content_window, height=content_height)
        self._content_canvas.configure(scrollregion=self._content_canvas.bbox("all"))

    def _on_content_canvas_configure(self, event):
        self._content_canvas.itemconfigure(self._content_window, width=event.width)
        content_height = max(event.height, self._content.winfo_reqheight())
        self._content_canvas.itemconfigure(self._content_window, height=content_height)
        self._content_canvas.configure(scrollregion=self._content_canvas.bbox("all"))

    def _bind_content_mousewheel(self):
        _bind_scroll_routing(self)

    # -- navigation --------------------------------------------
    def nav_to(self, step):
        if self._operation_running:
            return
        self._operation_controls = []
        # Cancel previous timer if it's running
        if hasattr(self, '_timer_id'):
            self.after_cancel(self._timer_id)
        
        # Record time spent on previous stage (but don't show it - we're tracking overall time now)
        if hasattr(self, '_current') and self._current is not None:
            pass  # Overall timer continues running
        
        self._current = step
        self._step_prog["value"] = step
        
        # Start live timer update
        self._update_timer()
        
        self._btn_back.config(state="normal" if step > 0 and not self._operation_running else "disabled")
        self._btn_next.config(text="Next ->", state="normal" if not self._operation_running else "disabled")
        if hasattr(self, "_close_without_export_btn"):
            self._close_without_export_btn.pack_forget()

        for i, (row, inner, bar, num, lbl) in enumerate(self._step_widgets):
            if i < step:      # completed
                row.config(bg=SURF); inner.config(bg=SURF)
                bar.config(bg=OK);   num.config(bg=SURF, fg=OK, text="OK")
                lbl.config(bg=SURF, fg=MUTE, font=TFS)
            elif i == step:   # active
                row.config(bg=SURF2); inner.config(bg=SURF2)
                bar.config(bg=ACC);   num.config(bg=SURF2, fg=ACC, text=f"{i+1:02d}")
                lbl.config(bg=SURF2, fg=FG, font=TFB)
            else:             # upcoming
                row.config(bg=SURF); inner.config(bg=SURF)
                bar.config(bg=SURF); num.config(bg=SURF, fg=MUTE, text=f"{i+1:02d}")
                lbl.config(bg=SURF, fg=MUTE, font=TFS)

        for w in self._content.winfo_children():
            w.destroy()

        [self._page_folder, self._page_sources, self._page_sheet,
         self._page_validate, self._page_filters, self._page_export][step]()
        self.after_idle(lambda: self._content_canvas.yview_moveto(0))

    def _on_next(self):
        if self._operation_running:
            self._set_status(f"Please wait until {self._operation_label or 'the current operation'} finishes.", WARN)
            return
        if self._current < len(STEP_NAMES) - 1:
            self.nav_to(self._current + 1)
        else:
            if not self._has_current_export():
                self._set_status("The current result has not been exported. Run Export or choose Close Without Export.", WARN)
                messagebox.showwarning(
                    "Export required",
                    "The current result has not been exported.\n\nRun Export to save it, or use Close Without Export to leave.",
                    parent=self,
                )
                return
            self.destroy()

    def _keyboard_next(self):
        if str(self._btn_next.cget("state")) == "normal":
            self._on_next()
        return "break"

    def _keyboard_browse(self):
        if self._current == 0 and not self._operation_running:
            self._browse_folder()
        return "break"

    def _result_signature(self):
        return (self._data_revision, self._filter_cache_key())

    def _has_current_export(self):
        return self.final_df is not None and self._last_export_signature == self._result_signature()

    def _request_close(self):
        if self._operation_running:
            if messagebox.askyesno("Operation in progress", "Cancel the current operation?\n\nThe window will stay open until processing stops safely.", parent=self):
                self._cancel_active_operation()
            return
        self._close_without_export()

    def _on_back(self):
        if self._operation_running:
            self._set_status(f"Please wait until {self._operation_label or 'the current operation'} finishes.", WARN)
            return
        if self._current > 0:
            self.nav_to(self._current - 1)

    def _set_status(self, msg, color=MUTE):
        self._status_lbl.config(text=msg, fg=color)

    def _set_operation_running(self, running, label=""):
        self._operation_running = bool(running)
        self._operation_label = label if running else ""
        if hasattr(self, "_btn_back"):
            self._btn_back.config(state="disabled" if running else ("normal" if self._current > 0 else "disabled"))
        if hasattr(self, "_btn_next"):
            self._btn_next.config(state="disabled" if running else "normal")
        if running:
            self._operation_started = time.monotonic()
            self._operation_percent, self._operation_eta, self._operation_detail = 0, None, "Starting"
            self._operation_files = {}
            self._operation_cancel_pending = False
            self._operation_last_progress = self._operation_started
            self._disabled_operation_controls = []
            for widget in self._operation_controls:
                if widget.winfo_exists():
                    state = widget.cget("state")
                    self._disabled_operation_controls.append((widget, state))
                    widget.config(state="disabled")
            self._operation_strip.pack(fill="x", before=self._footer_divider)
            self._operation_cancel_btn.config(state="normal", text="Cancel")
            self._operation_activity.start(80)
            self._tick_operation_display()
        else:
            self._operation_activity.stop()
            self._operation_files = {}
            if self._operation_timer_id:
                self.after_cancel(self._operation_timer_id)
                self._operation_timer_id = None
            self._operation_strip.pack_forget()
            for widget, state in self._disabled_operation_controls:
                if widget.winfo_exists():
                    widget.config(state=state)
            self._disabled_operation_controls = []

    def _register_operation_controls(self, parent):
        for widget in parent.winfo_children():
            if isinstance(widget, (tk.Entry, tk.Checkbutton, tk.Button, ttk.Combobox)):
                self._operation_controls.append(widget)
            self._register_operation_controls(widget)

    def _tick_operation_display(self):
        if not self._operation_running:
            return
        elapsed = self._format_time(time.monotonic() - self._operation_started)
        eta = self._format_time(self._operation_eta) if self._operation_eta is not None else "Estimating..."
        state = "Stopping safely" if self._operation_cancel_pending else "Working"
        progress = f"{self._operation_percent:.0f}% completed" if self._operation_percent > 0 else "Waiting for progress"
        self._operation_title.config(text=f"{self._operation_label.capitalize()}: {state}  |  {progress}")
        self._operation_bar.config(value=self._operation_percent)
        files = list(self._operation_files.values())
        file_text = f"\nFile: {files[0]}" if len(files) == 1 else f"\n{len(files)} files active: {', '.join(files[:2])}" if files else ""
        gap = time.monotonic() - self._operation_last_progress
        hint = "\nLarge files can take several minutes between progress updates." if gap >= 15 and not self._operation_cancel_pending else ""
        self._operation_caption.config(text=f"Elapsed: {elapsed}  |  ETA: {eta}  |  {self._operation_detail}{file_text}{hint}")
        self._operation_timer_id = self.after(500, self._tick_operation_display)

    def _note_operation_progress(self, percent):
        if percent > self._operation_percent:
            self._operation_last_progress = time.monotonic()
        self._operation_percent = max(0, min(100, percent))

    def _operation_file_activity(self, key, name, active):
        if not self._operation_running:
            return
        if active:
            self._operation_files[key] = name
        else:
            self._operation_files.pop(key, None)

    def _cancel_active_operation(self):
        if not self._operation_running:
            return
        self._operation_cancel_btn.config(state="disabled", text="Stopping...")
        self._operation_cancel_pending = True
        self._operation_detail = "Cancel requested; waiting for the current read/write to finish"
        if self._operation_label == "file check":
            self._cancel_validation_requested = True
        elif self._operation_label == "combine":
            self._cancel_combine()
        else:
            self._cancel_export()

    def _record_perf(self, msg):
        timestamp = time.strftime("%H:%M:%S")
        self._perf_log.append(f"[{timestamp}] {msg}")

    def _classify_file_error(self, exc):
        msg = str(exc)
        low = msg.lower()
        if "password" in low or "encrypted" in low:
            return "password-protected", "Password-protected or encrypted file is not supported."
        if isinstance(exc, PermissionError) or "permission denied" in low or "being used by another process" in low:
            return "locked/permission", "File appears locked or you do not have permission to read it."
        if isinstance(exc, zipfile.BadZipFile) or "badzipfile" in low or "not a zip file" in low:
            return "corrupt", "File appears corrupt, incomplete, or not a valid Excel/ZIP file."
        if "file is not a zip file" in low or "cannot open" in low or "invalid file" in low:
            return "corrupt", "File appears corrupt or partially downloaded."
        return "read error", msg or exc.__class__.__name__

    def _show_error_with_details(self, title, user_message, technical_detail="", action=""):
        dlg = tk.Toplevel(self)
        dlg.title(title)
        dlg.configure(bg=BG)
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)

        body = tk.Frame(dlg, bg=BG, padx=PAD, pady=PAD)
        body.pack(fill="both", expand=True)
        tk.Label(body, text=title, font=TFB, bg=BG, fg=ERR).pack(anchor="w")
        tk.Label(
            body,
            text=user_message,
            font=TF,
            bg=BG,
            fg=FG,
            wraplength=520,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))
        if action:
            tk.Label(
                body,
                text=f"Next step: {action}",
                font=TFS,
                bg=BG,
                fg=ACCH,
                wraplength=520,
                justify="left",
            ).pack(anchor="w", pady=(8, 0))

        detail_box = tk.Text(
            body,
            bg=SURF,
            fg=FG,
            font=TMO,
            height=5,
            width=72,
            bd=0,
            highlightthickness=1,
            highlightbackground=BORD,
        )
        detail_box.insert("1.0", technical_detail or "No technical detail available.")
        detail_box.config(state="disabled")

        actions = tk.Frame(body, bg=BG)
        actions.pack(fill="x", pady=(12, 0))

        def toggle_details():
            if detail_box.winfo_ismapped():
                detail_box.pack_forget()
                details_btn.config(text="Show technical detail")
            else:
                detail_box.pack(fill="x", pady=(10, 0))
                details_btn.config(text="Hide technical detail")

        details_btn = _btn(actions, "Show technical detail", toggle_details, "outline", padx=10, pady=4)
        details_btn.pack(side="left")
        _btn(actions, "OK", dlg.destroy, "primary", padx=14, pady=4).pack(side="right")
        dlg.wait_window()

    def _find_duplicate_source_warnings(self):
        groups = {}
        for src in self.all_sources:
            try:
                name = os.path.basename(src.get("inner_name") or src.get("full_path") or src.get("display_name", "")).lower()
                if src.get("mode") == "direct":
                    size = os.path.getsize(src["full_path"])
                else:
                    with zipfile.ZipFile(src["zip_path"], "r") as z:
                        size = z.getinfo(src["inner_name"]).file_size
                key = (name, size)
                groups.setdefault(key, []).append(src.get("display_name"))
            except Exception:
                continue
        return [names for names in groups.values() if len(names) > 1]

    def _write_audit_report(self, out_path, out_fmt, row_count, file_size, save_elapsed):
        base, _ = os.path.splitext(out_path)
        audit_txt_path = base + ".audit.txt"
        passed_ids = {id(src) for src in self.passed_srcs}
        sources = []
        for src in self.all_sources:
            item = {
                "name": src.get("display_name"),
                "type": src.get("type"),
                "mode": src.get("mode"),
                "included": id(src) in passed_ids,
            }
            if src.get("mode") == "direct":
                item["path"] = src.get("full_path")
            else:
                item["zip_path"] = src.get("zip_path")
                item["inner_name"] = src.get("inner_name")
            sources.append(item)

        payload = {
            "app": "MergeGuru",
            "version": APP_VERSION,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source_folder": self.folder,
            "reference_source": self.all_sources[self.ref_idx].get("display_name") if self.all_sources else None,
            "selected_sheet": self.selected_sheet,
            "layout_options": {
                "enabled": self.layout_fix_enabled,
                "header_row": self.header_row_num,
                "footer_rows_to_ignore": self.footer_rows_to_ignore,
            },
            "validation_summary": self._validation_summary,
            "validation_results": [
                {
                    "source": r.get("name"),
                    "status": r.get("status"),
                    "detail": r.get("detail"),
                }
                for r in self._validation_results
            ],
            "possible_duplicate_sources": self._duplicate_source_warnings,
            "data_quality_summary": self._data_quality_summary,
            "filters": [filter_summary(fc) for fc in self.filters],
            "filter_count": len(self.filters),
            "extra_columns_appended": list(self.extra_columns_found),
            "sources": sources,
            "output": {
                "path": out_path,
                "format": out_fmt,
                "rows": row_count,
                "file_size_bytes": file_size,
                "save_elapsed_seconds": round(save_elapsed, 3),
            },
        }
        with open(audit_txt_path, "w", encoding="utf-8") as f:
            f.write(f"MergeGuru Audit Report ({APP_VERSION})\n")
            f.write("=" * 42 + "\n")
            f.write(f"Created: {payload['created_at']}\n")
            f.write(f"Source folder: {self.folder}\n")
            f.write(f"Reference: {payload['reference_source']}\n")
            if self.selected_sheet:
                f.write(f"Sheet: {self.selected_sheet}\n")
            f.write("\nOutput\n")
            f.write(f"Path: {out_path}\n")
            f.write(f"Format: {out_fmt}\n")
            f.write(f"Rows: {row_count:,}\n")
            f.write(f"Size: {self._format_size(file_size)}\n")
            f.write(f"Save time: {save_elapsed:.2f}s\n")
            f.write("\nValidation Summary\n")
            f.write(self._format_validation_summary() or "No validation summary available.")
            f.write("\n\nData Quality\n")
            f.write(self._format_quality_summary())
            f.write("\n\nFilters\n")
            if self.filters:
                for fc in self.filters:
                    f.write(f"- {filter_summary(fc)}\n")
            else:
                f.write("- None\n")
            f.write("\nPossible Duplicate Sources\n")
            if self._duplicate_source_warnings:
                for group in self._duplicate_source_warnings:
                    f.write(f"- {' / '.join(group)}\n")
            else:
                f.write("- None detected\n")
            f.write("\nSources\n")
            for src in sources:
                state = "included" if src["included"] else "excluded"
                f.write(f"- {src['name']} [{state}]\n")
        return audit_txt_path

    def _invalidate_filtered_cache(self, clear_series=False):
        self._filtered_cache_key = None
        self._filtered_df_cache = None
        self._filter_stats_cache = []
        if clear_series:
            self._string_series_cache = {}
            self._date_series_cache = {}

    def _reset_combined_state(self, clear_filters=False):
        self._data_revision += 1
        self.final_df = None
        self._last_memory_optimization = None
        self._data_quality_summary = {}
        self._cancel_combine_requested = False
        self.extra_columns_found = []
        if clear_filters:
            self.filters = []
        self._invalidate_filtered_cache(clear_series=True)

    def _filter_cache_key(self):
        return tuple(json.dumps(fc, sort_keys=True) for fc in self.filters)

    def _get_string_series(self, col):
        if self.final_df is None:
            return None
        if col not in self._string_series_cache:
            self._string_series_cache[col] = self.final_df[col].fillna("").astype(str)
        return self._string_series_cache[col]

    def _get_date_series(self, col):
        if self.final_df is None:
            return None
        if col not in self._date_series_cache:
            self._date_series_cache[col] = pd.to_datetime(self.final_df[col], errors="coerce")
        return self._date_series_cache[col]

    def _compute_filtered_result(self):
        if self.final_df is None:
            self._filtered_df_cache = None
            self._filter_stats_cache = []
            return None

        cache_key = self._filter_cache_key()
        if self._filtered_cache_key == cache_key and self._filtered_df_cache is not None:
            return self._filtered_df_cache

        if not self.filters:
            self._filtered_cache_key = cache_key
            self._filtered_df_cache = self.final_df
            self._filter_stats_cache = []
            return self._filtered_df_cache

        mask = pd.Series(True, index=self.final_df.index)
        stats = []
        for fc in self.filters:
            before = int(mask.sum())
            string_series = self._get_string_series(fc["column"]) if fc["mode"] in ("category", "text") else None
            date_series = self._get_date_series(fc["column"]) if fc["mode"] == "date" else None
            current_mask = build_filter_mask(
                self.final_df,
                fc,
                string_series=string_series,
                date_series=date_series,
            ).fillna(False)
            mask &= current_mask
            stats.append((fc, before, int(mask.sum())))

        self._filtered_cache_key = cache_key
        self._filtered_df_cache = self.final_df.loc[mask]
        self._filter_stats_cache = stats
        return self._filtered_df_cache

    def _compute_filtered_view_for_filters(self, filters):
        if self.final_df is None:
            return None
        if not filters:
            return self.final_df

        mask = pd.Series(True, index=self.final_df.index)
        for fc in filters:
            string_series = self._get_string_series(fc["column"]) if fc["mode"] in ("category", "text") else None
            date_series = self._get_date_series(fc["column"]) if fc["mode"] == "date" else None
            current_mask = build_filter_mask(
                self.final_df,
                fc,
                string_series=string_series,
                date_series=date_series,
            ).fillna(False)
            mask &= current_mask
        return self.final_df.loc[mask]
    
    def _format_time(self, seconds):
        """Format seconds into a readable time string (e.g., '1m 23s', '45s')"""
        if seconds < 60:
            return f"{int(seconds)}s"
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"

    def _make_auto_export_path(self, fmt="Excel"):
        stamp = time.strftime("%Y%m%d_%H%M%S")
        base = f"combined_output_{stamp}"
        if self.filters:
            base += f"_{len(self.filters)}filters"
        return self._make_unique_path(os.path.join(self.folder or ".", base + EXPORT_FORMATS[fmt]["extension"]))

    def _make_unique_path(self, path):
        base, ext = os.path.splitext(path)
        candidate = path
        n = 2
        while os.path.exists(candidate):
            candidate = f"{base}_{n}{ext}"
            n += 1
        return candidate

    def _build_data_quality_summary(self, df):
        if df is None:
            return {}
        summary = {
            "rows": len(df),
            "columns": len(df.columns),
            "files": len(self.passed_srcs),
            "blank_columns": [],
            "blank_rows": None,
            "blank_rows_skipped": not self.deep_quality_checks_enabled,
            "duplicate_rows": None,
            "duplicate_skipped": not self.deep_quality_checks_enabled,
            "deep_checks_enabled": self.deep_quality_checks_enabled,
        }
        if not self.deep_quality_checks_enabled:
            return summary
        try:
            null_mask = df.isna()
            blank_cols = df.columns[null_mask.all(axis=0)].tolist()
            summary["blank_columns"] = blank_cols
            if len(df) <= 500000:
                summary["blank_rows"] = int(null_mask.all(axis=1).sum())
            else:
                summary["blank_rows_skipped"] = True
        except Exception:
            summary["blank_columns"] = []
            summary["blank_rows"] = None
        if len(df) <= 250000:
            try:
                summary["duplicate_rows"] = int(df.duplicated().sum())
            except Exception:
                summary["duplicate_rows"] = None
        else:
            summary["duplicate_skipped"] = True
        return summary

    def _format_quality_summary(self):
        q = self._data_quality_summary or {}
        if not q:
            return "Data quality summary is not available yet."
        blank_cols = q.get("blank_columns") or []
        blank_rows = q.get("blank_rows")
        duplicate_rows = q.get("duplicate_rows")
        if not q.get("deep_checks_enabled"):
            blank_row_text = "not checked"
            dup_text = "not checked"
        else:
            blank_row_text = "skipped for large data" if q.get("blank_rows_skipped") else (
                "--" if blank_rows is None else f"{blank_rows:,}"
            )
            dup_text = "skipped for large data" if q.get("duplicate_skipped") else (
                "--" if duplicate_rows is None else f"{duplicate_rows:,}"
            )
        return (
            f"Quality: {q.get('rows', 0):,} rows | {q.get('columns', 0)} columns | "
            f"{q.get('files', 0)} files | blank rows: {blank_row_text} | "
            f"blank columns: {len(blank_cols)} | duplicate rows: {dup_text}"
        )

    def _stop_overall_timer(self):
        """Stop the overall timer and show final result"""
        if hasattr(self, '_timer_id'):
            self.after_cancel(self._timer_id)
        
        if hasattr(self, 'overall_start_time'):
            elapsed = time.time() - self.overall_start_time
            elapsed_text = f"  |  {self._format_time(elapsed)}"
            self._hdr_step.config(text=f"{STEP_NAMES[self._current]}  |  {self._current+1} / {len(STEP_NAMES)}{elapsed_text}")
            return elapsed

    def _update_timer(self):
        """Update the live timer in the header (runs every second)"""
        if hasattr(self, '_current') and hasattr(self, 'overall_start_time'):
            # Calculate overall elapsed time from Browse click
            elapsed = time.time() - self.overall_start_time
            elapsed_text = f"  |  {self._format_time(elapsed)}"
            
            # Update header with live timer
            self._hdr_step.config(text=f"{STEP_NAMES[self._current]}  |  {self._current+1} / {len(STEP_NAMES)}{elapsed_text}")
            
            # Schedule next update in 1 second
            self._timer_id = self.after(1000, self._update_timer)

    def _next_ok(self, yes=True):
        self._btn_next.config(state="normal" if yes and not self._operation_running else "disabled")

    # -- content area padding helper ---------------------------
    def _pad(self):
        f = tk.Frame(self._content, bg=BG)
        f.pack(fill="both", expand=True, padx=PAD, pady=PAD)
        return f

    def _page_header(self, parent, title, subtitle=""):
        tk.Label(parent, text=title,    font=TFH, bg=BG, fg=FG).pack(anchor="w")
        if subtitle:
            tk.Label(parent, text=subtitle, font=TFS, bg=BG, fg=MUTE).pack(anchor="w", pady=(2, 0))
        tk.Frame(parent, bg=BORD, height=1).pack(fill="x", pady=(10, 14))

    # ---------------------------------------------------------
    # STEP 0  -  Select Data
    # ---------------------------------------------------------
    def _page_folder(self):
        self._next_ok(False)

        # centred card
        card = tk.Frame(self._content, bg=BG)
        card.place(relx=0.5, rely=0.44, anchor="center")

        tk.Label(card, text="📁", font=(_FAM, 52), bg=BG, fg=MUTE).pack()
        tk.Label(card, text="Select Data Sources", font=TFH, bg=BG, fg=FG).pack(pady=(6, 3))
        tk.Label(card, text="Pick a folder, or Ctrl-select specific .xlsx, .csv, or .zip files.",
                 font=TFS, bg=BG, fg=MUTE).pack()

        tk.Frame(card, bg=BG, height=18).pack()

        # path display box
        path_box = tk.Frame(card, bg=SURF2, highlightthickness=1,
                            highlightbackground=BORD)
        path_box.pack(fill="x", pady=(0, 10), ipadx=2, ipady=2)
        self._path_lbl = tk.Label(path_box,
                                   text="No folder or files selected",
                                   font=TMO, bg=SURF2, fg=MUTE,
                                   width=48, anchor="w", padx=10, pady=6)
        self._path_lbl.pack(side="left", fill="x", expand=True)

        _btn(card, "  Browse Folder...  ", self._browse_folder, "primary").pack(fill="x")
        tk.Label(card, text="or", font=TFS, bg=BG, fg=MUTE).pack(pady=(6, 0))
        _btn(card, "  Select Files...  ", self._browse_files, "ghost").pack(fill="x", pady=(6, 0))
        self._folder_badge = tk.Label(card, text="", font=TFS, bg=BG, fg=MUTE)
        self._folder_badge.pack(pady=(10, 0))

        # restore previous selection if navigating back
        if self.folder:
            if self.selected_file_paths:
                label = f"{len(self.selected_file_paths)} selected file(s) from {self.folder}"
            else:
                label = self.folder
            self._path_lbl.config(text=label, fg=FG)
            n = len(self.all_sources)
            self._folder_badge.config(text=f"OK  {n} source(s) found.", fg=OK)
            self._next_ok(True)

    def _browse_folder(self):
        p = filedialog.askdirectory(title="Select folder with data files")
        if not p:
            return
        self.folder = p
        self.selected_file_paths = []
        self._path_lbl.config(text=p, fg=FG)
        self._folder_badge.config(text="Scanning...", fg=MUTE)
        self._reset_source_selection()
        self._discover_sources()

    def _browse_files(self):
        paths = filedialog.askopenfilenames(
            title="Select data files",
            filetypes=[
                ("Supported data files", "*.xlsx *.csv *.zip"),
                ("Excel files", "*.xlsx"),
                ("CSV files", "*.csv"),
                ("ZIP files", "*.zip"),
                ("All files", "*.*"),
            ],
        )
        if not paths:
            return
        self.selected_file_paths = list(paths)
        try:
            self.folder = os.path.commonpath([os.path.dirname(p) for p in self.selected_file_paths])
        except Exception:
            self.folder = os.path.dirname(self.selected_file_paths[0])
        self._path_lbl.config(text=f"{len(self.selected_file_paths)} selected file(s) from {self.folder}", fg=FG)
        self._folder_badge.config(text="Scanning selected files...", fg=MUTE)
        self._reset_source_selection()
        self._discover_sources_from_paths(self.selected_file_paths)

    def _reset_source_selection(self):
        # START OVERALL TIMER
        self.overall_start_time = time.time()

        # reset downstream state
        self.all_sources  = []
        self.ref_idx      = 0
        self.selected_sheet = None
        self._source_sheet_map = {}
        self.ref_columns  = []
        self.passed_srcs  = []
        self.filters      = []
        self._reset_combined_state(clear_filters=False)

    def _discover_sources(self):
        paths = [os.path.join(self.folder, f) for f in os.listdir(self.folder)]
        self._discover_sources_from_paths(paths)

    def _discover_sources_from_paths(self, paths):
        self.all_sources = []
        self._duplicate_source_warnings = []
        for path in paths:
            f = os.path.basename(path)
            lf = path.lower()
            if lf.endswith(".xlsx"):
                self.all_sources.append({"type": "xlsx", "mode": "direct",
                    "display_name": f, "full_path": path})
            elif lf.endswith(".csv"):
                self.all_sources.append({"type": "csv", "mode": "direct",
                    "display_name": f, "full_path": path})
        for path in paths:
            f = os.path.basename(path)
            if not path.lower().endswith(".zip"):
                continue
            try:
                with zipfile.ZipFile(path, "r") as z:
                    for item in z.namelist():
                        li = item.lower()
                        t  = "xlsx" if li.endswith(".xlsx") else ("csv" if li.endswith(".csv") else None)
                        if t:
                            self.all_sources.append({"type": t, "mode": "zip",
                                "display_name": f"{f} :: {item}",
                                "zip_path": path, "inner_name": item})
            except Exception:
                pass
        n = len(self.all_sources)
        self._duplicate_source_warnings = self._find_duplicate_source_warnings()
        if n == 0:
            self._folder_badge.config(text="Warning  No supported files found.", fg=WARN)
            self._next_ok(False)
        else:
            dup_note = f" | {len(self._duplicate_source_warnings)} possible duplicate group(s)" if self._duplicate_source_warnings else ""
            self._folder_badge.config(text=f"OK  {n} source(s) discovered{dup_note}.", fg=WARN if self._duplicate_source_warnings else OK)
            self._set_status(f"{n} file(s) ready{dup_note} - click Next.", WARN if self._duplicate_source_warnings else OK)
            self._next_ok(True)

    # ---------------------------------------------------------
    # STEP 1  -  Choose Template  (choose reference)
    # ---------------------------------------------------------
    def _page_sources(self):
        self._next_ok(bool(self.all_sources))
        pad = self._pad()
        self._page_header(pad, "Choose Template File",
                          "Pick the file whose columns and layout should be used as the template.")

        if not self.all_sources:
            tk.Label(pad, text="No sources found - go back and choose a different folder.",
                     font=TF, bg=BG, fg=WARN).pack(anchor="w")
            return

        if self._duplicate_source_warnings:
            sample = "; ".join(" / ".join(group[:2]) for group in self._duplicate_source_warnings[:3])
            tk.Label(
                pad,
                text=f"Possible duplicate sources detected: {sample}",
                font=TFS,
                bg=BG,
                fg=WARN,
                wraplength=720,
                justify="left",
            ).pack(anchor="w", pady=(0, 10))

        # treeview
        tf = tk.Frame(pad, bg=BG)
        tf.pack(fill="both", expand=True)
        vsb = ttk.Scrollbar(tf, orient="vertical")
        self._src_tree = ttk.Treeview(tf, columns=("template", "type", "name"),
                                       show="headings", yscrollcommand=vsb.set)
        vsb.config(command=self._src_tree.yview)
        self._src_tree.heading("template",  text="TEMPLATE")
        self._src_tree.heading("type", text="TYPE")
        self._src_tree.heading("name", text="SOURCE")
        self._src_tree.column("template",  width=90,  stretch=False)
        self._src_tree.column("type", width=56,  stretch=False)
        self._src_tree.column("name", width=500)
        self._src_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self._src_tree.tag_configure("ref_row", foreground=WARN)

        for i, src in enumerate(self.all_sources):
            mark = "Selected" if i == self.ref_idx else "Click row"
            source_name = self._template_source_label(src["display_name"], i == self.ref_idx)
            self._src_tree.insert("", "end", iid=str(i),
                                   values=(mark, src["type"].upper(), source_name),
                                   tags=("ref_row",) if i == self.ref_idx else ())

        self._src_tree.bind("<ButtonRelease-1>", self._pick_reference)
        self._src_tree.selection_set(str(self.ref_idx))

        info = tk.Label(pad, text=f"{len(self.all_sources)} source(s) found.",
                        font=TFS, bg=BG, fg=OK)
        info.pack(anchor="w", pady=(10, 0))
        self._set_status("Choose the template file, then click Next.", MUTE)

    def _template_source_label(self, display_name, selected):
        return f"★ {display_name}" if selected else display_name

    def _pick_reference(self, *_):
        sel = self._src_tree.selection()
        if not sel:
            return
        new_idx = int(sel[0])
        old_idx = self.ref_idx
        self.ref_idx = new_idx
        # update star markers
        self._src_tree.set(str(old_idx), "template", "Click row")
        self._src_tree.set(str(old_idx), "name", self._template_source_label(
            self.all_sources[old_idx]["display_name"], False
        ))
        self._src_tree.item(str(old_idx), tags=())
        self._src_tree.set(str(new_idx), "template", "Selected")
        self._src_tree.set(str(new_idx), "name", self._template_source_label(
            self.all_sources[new_idx]["display_name"], True
        ))
        self._src_tree.item(str(new_idx), tags=("ref_row",))
        # reset downstream
        self.selected_sheet = None
        self._source_sheet_map = {}
        self.ref_columns    = []
        self.passed_srcs    = []
        self._reset_combined_state(clear_filters=True)

    # ---------------------------------------------------------
    # STEP 2  -  Choose Sheet
    # ---------------------------------------------------------
    def _page_sheet(self):
        self._next_ok(False)
        pad = self._pad()
        ref = self.all_sources[self.ref_idx]

        if ref["type"] != "xlsx":
            self.selected_sheet = None
            self._next_ok(True)
            self._page_header(pad, "Choose Template Sheet")
            tk.Label(pad, text="Template file is CSV, so no worksheet selection is needed.",
                     font=TF, bg=BG, fg=MUTE).pack(anchor="w")
            tk.Label(pad, text="Click Next to continue.", font=TFS, bg=BG, fg=MUTE).pack(anchor="w", pady=4)
            self._render_layout_options(pad)
            return

        self._page_header(pad, "Choose Template Sheet",
                          f"Template file: {ref['display_name']}")

        loading = tk.Label(pad, text="Loading  Loading sheets...", font=TF, bg=BG, fg=MUTE)
        loading.pack(anchor="w")

        def load():
            try:
                names = get_sheet_names(ref)
                self.after(0, lambda: self._show_sheets(pad, loading, names))
            except Exception as e:
                self.after(0, lambda: loading.config(text=f"Error: {e}", fg=ERR))

        threading.Thread(target=load, daemon=True).start()

    def _show_sheets(self, pad, loading, names):
        loading.destroy()
        if not self.selected_sheet or self.selected_sheet not in names:
            self.selected_sheet = names[0]

        self._sheet_var = tk.StringVar(value=self.selected_sheet)

        for name in names:
            rb = tk.Radiobutton(pad, text=name, variable=self._sheet_var, value=name,
                                bg=BG, fg=FG, selectcolor=SURF2,
                                activebackground=BG, activeforeground=ACCH, font=TF,
                                command=lambda n=name: self._set_sheet(n))
            rb.pack(anchor="w", pady=3)

        self._auto_match_sheet_var = tk.BooleanVar(value=self.auto_match_sheet_enabled)
        advanced = tk.Frame(pad, bg=SURF, padx=12, pady=10, highlightthickness=1, highlightbackground=BORD)
        advanced.pack(fill="x", pady=(14, 0))
        _label(advanced, "Advanced file handling", TFB, bg=SURF).pack(anchor="w")
        tk.Checkbutton(
            advanced,
            text="Different sheet names, same data layout",
            variable=self._auto_match_sheet_var,
            bg=SURF,
            fg=FG,
            selectcolor=SURF2,
            activebackground=SURF,
            activeforeground=FG,
            font=TF,
            command=self._toggle_auto_match_sheet,
        ).pack(anchor="w", pady=(12, 2))
        _label(
            advanced,
            "Use this when sheet names include dates or changing text. MergeGuru will find the worksheet by matching the reference headers.",
            TFS,
            fg=MUTE,
            bg=SURF,
            wraplength=620,
            justify="left",
        ).pack(anchor="w")

        self._render_layout_options(advanced, nested=True)
        self._next_ok(True)
        self._set_status("Choose the template sheet, then click Next.", MUTE)

    def _set_sheet(self, name):
        self.selected_sheet = name
        self.ref_columns  = []
        self.passed_srcs  = []
        self._reset_combined_state(clear_filters=True)

    def _toggle_auto_match_sheet(self):
        self.auto_match_sheet_enabled = bool(self._auto_match_sheet_var.get())
        self.ref_columns = []
        self.passed_srcs = []
        self._source_sheet_map = {}
        self._reset_combined_state(clear_filters=True)

    def _get_layout_read_options(self):
        if not self.layout_fix_enabled:
            return {"header_row": 1, "footer_rows": 0}
        return {
            "header_row": max(1, int(self.header_row_num)),
            "footer_rows": max(0, int(self.footer_rows_to_ignore)),
        }

    def _render_layout_options(self, parent, nested=False):
        box = (
            tk.Frame(parent, bg=SURF)
            if nested
            else tk.Frame(parent, bg=SURF, padx=12, pady=10, highlightthickness=1, highlightbackground=BORD)
        )
        box.pack(fill="x", pady=(12 if nested else 14, 0))
        if nested:
            tk.Frame(box, bg=BORD, height=1).pack(fill="x", pady=(4, 10))

        self._layout_fix_var = tk.BooleanVar(value=self.layout_fix_enabled)
        tk.Checkbutton(
            box,
            text="Some files have extra rows above or below the real table",
            variable=self._layout_fix_var,
            bg=SURF,
            fg=FG,
            selectcolor=SURF2,
            activebackground=SURF,
            activeforeground=FG,
            font=TF,
            command=self._toggle_layout_options,
        ).pack(anchor="w")

        _label(
            box,
            "Enable this only when a dump contains title rows, notes, totals, or other junk around the real data.",
            TFS,
            fg=MUTE,
            bg=SURF,
            wraplength=520,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        self._layout_opts_frame = tk.Frame(box, bg=SURF)
        self._layout_opts_frame.pack(fill="x", pady=(10, 0))

        row1 = tk.Frame(self._layout_opts_frame, bg=SURF)
        row1.pack(fill="x")
        _label(row1, "Header row number:", TFB, bg=SURF).pack(side="left")
        self._header_row_var = tk.StringVar(value=str(self.header_row_num))
        self._header_row_entry = _entry(row1, textvariable=self._header_row_var, width=8)
        self._header_row_entry.pack(side="left", padx=(8, 0), ipady=4)

        row2 = tk.Frame(self._layout_opts_frame, bg=SURF)
        row2.pack(fill="x", pady=(8, 0))
        _label(row2, "Footer rows to ignore:", TFB, bg=SURF).pack(side="left")
        self._footer_rows_var = tk.StringVar(value=str(self.footer_rows_to_ignore))
        self._footer_rows_entry = _entry(row2, textvariable=self._footer_rows_var, width=8)
        self._footer_rows_entry.pack(side="left", padx=(8, 0), ipady=4)

        _label(
            self._layout_opts_frame,
            "Example: if the real headers start on line 5, set header row to 5. If the last 2 rows are notes/totals, set footer rows to 2.",
            TFS,
            fg=MUTE,
            bg=SURF,
            wraplength=520,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))

        self._toggle_layout_options()

    def _toggle_layout_options(self):
        enabled = bool(self._layout_fix_var.get())
        self.layout_fix_enabled = enabled
        if enabled:
            self._layout_opts_frame.pack(fill="x", pady=(10, 0))
        else:
            self._layout_opts_frame.pack_forget()

    def _sync_layout_options_from_ui(self):
        enabled = bool(getattr(self, "_layout_fix_var", tk.BooleanVar(value=self.layout_fix_enabled)).get())
        self.layout_fix_enabled = enabled
        if not enabled:
            self.header_row_num = 1
            self.footer_rows_to_ignore = 0
            return
        try:
            header_row = int(self._header_row_var.get().strip())
            footer_rows = int(self._footer_rows_var.get().strip())
        except ValueError:
            raise ValueError("Header row and footer rows must be whole numbers.")
        if header_row < 1:
            raise ValueError("Header row must be 1 or greater.")
        if footer_rows < 0:
            raise ValueError("Footer rows cannot be negative.")
        self.header_row_num = header_row
        self.footer_rows_to_ignore = footer_rows

    # ---------------------------------------------------------
    # STEP 3  -  Check Files
    # ---------------------------------------------------------
    def _page_validate(self):
        self._next_ok(False)
        pad = self._pad()
        self._page_header(pad, "Check Files",
                          "Confirm every selected file matches the template before combining.")

        action_card = tk.Frame(pad, bg=SURF, padx=12, pady=10, highlightthickness=1, highlightbackground=BORD)
        action_card.pack(fill="x", pady=(0, 10))
        _label(action_card, "Ready to check", TFB, bg=SURF).pack(side="left")
        self._run_validation_btn = _btn(action_card, "Run File Check", self._run_validation, "primary")
        self._run_validation_btn.pack(side="right")
        tk.Label(
            action_card,
            text="Files with missing columns will be stopped here, before export.",
            font=TFS,
            bg=SURF,
            fg=MUTE,
        ).pack(anchor="w", pady=(4, 0))

        options = tk.Frame(pad, bg=SURF, padx=12, pady=10, highlightthickness=1, highlightbackground=BORD)
        options.pack(fill="x", pady=(0, 10))
        _label(options, "Check options", TFB, bg=SURF).pack(anchor="w")
        self._auto_next_var = tk.BooleanVar(value=self.auto_advance_after_validation)
        tk.Checkbutton(
            options,
            text="Auto-next when validation passes",
            variable=self._auto_next_var,
            bg=SURF,
            fg=FG,
            selectcolor=SURF2,
            activebackground=SURF,
            activeforeground=FG,
            font=TFS,
        ).pack(anchor="w", pady=(8, 0))
        self._allow_extra_cols_var = tk.BooleanVar(value=self.allow_extra_columns)
        tk.Checkbutton(
            options,
            text="Allow extra columns and append at end",
            variable=self._allow_extra_cols_var,
            command=self._on_validation_option_changed,
            bg=SURF,
            fg=FG,
            selectcolor=SURF2,
            activebackground=SURF,
            activeforeground=FG,
            font=TFS,
        ).pack(anchor="w", pady=(4, 0))
        _label(
            options,
            "Tip: allow extra columns only when all template columns are present and you want new columns added after the template columns.",
            TFS,
            fg=MUTE,
            bg=SURF,
            wraplength=620,
            justify="left",
        ).pack(anchor="w", pady=(6, 0))

        # results tree
        tf = tk.Frame(pad, bg=BG)
        tf.pack(fill="both", expand=True)
        vsb = ttk.Scrollbar(tf, orient="vertical")
        self._val_tree = ttk.Treeview(tf, columns=("status", "source", "detail"),
                                       show="headings", yscrollcommand=vsb.set, height=6)
        vsb.config(command=self._val_tree.yview)
        self._val_tree.heading("status", text="STATUS")
        self._val_tree.heading("source", text="SOURCE")
        self._val_tree.heading("detail", text="DETAIL")
        self._val_tree.column("status", width=74,  stretch=False)
        self._val_tree.column("source", width=240)
        self._val_tree.column("detail", width=340)
        self._val_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self._val_tree.bind("<Double-1>", self._show_validation_detail)
        self._val_tree.tag_configure("pass", foreground=OK)
        self._val_tree.tag_configure("warn", foreground=WARN)
        self._val_tree.tag_configure("fail", foreground=ERR)

        # per-file progress
        tk.Frame(pad, bg=BG, height=10).pack()
        self._val_prog = ttk.Progressbar(pad, style="File.Horizontal.TProgressbar",
                                          mode="determinate", maximum=len(self.all_sources) or 1)
        self._val_prog.pack(fill="x")
        self._val_detail = tk.Label(pad, text="", font=TFS, bg=BG, fg=MUTE)
        self._val_detail.pack(anchor="w", pady=(4, 0))
        self._val_summary_lbl = tk.Label(pad, text="", font=TFS, bg=BG, fg=MUTE)
        self._val_summary_lbl.pack(fill="x", pady=(2, 0))
        self._val_summary_lbl.config(anchor="w", justify="left")
        self._val_summary_lbl.bind("<Configure>", lambda e: e.widget.config(wraplength=max(200, e.width - 8)))
        _label(pad, "Double-click a file result for details and the next step.", TFS, fg=MUTE).pack(anchor="w", pady=(4, 0))
        self._register_operation_controls(options)

        # if previously validated, restore results
        if self.passed_srcs:
            self._restore_validation()

    def _show_validation_detail(self, event):
        row = self._val_tree.identify_row(event.y)
        if not row:
            return
        status, name, detail = self._val_tree.item(row, "values")
        lower = detail.lower()
        action = "Correct the column layout or header-row settings, then run the file check again."
        if "locked" in lower or "permission" in lower:
            action = "Close Excel if the file is open, or choose a location you have permission to read."
        elif "password" in lower or "encrypted" in lower:
            action = "Use an unencrypted copy approved for this workflow."
        elif "corrupt" in lower:
            action = "Download a fresh copy of the source file and try again."
        elif status == "PASS":
            action = "This file is ready to combine."
        elif status == "WARN":
            action = "This file is accepted with extra columns; those columns will be appended."
        self._show_error_with_details(f"File check: {status}", name, technical_detail=detail, action=action)

    def _on_validation_option_changed(self):
        self.allow_extra_columns = bool(self._allow_extra_cols_var.get())
        if not hasattr(self, "_val_tree"):
            return

        # Existing pass/fail rows were calculated with the previous rule.
        # Clear them so stale validation cannot silently exclude files.
        if self._val_tree.get_children():
            for row in self._val_tree.get_children():
                self._val_tree.delete(row)
            self.passed_srcs = []
            self.extra_columns_found = []
            self._validation_results = []
            self._reset_combined_state(clear_filters=True)
            self._val_prog["value"] = 0
            self._val_detail.config(
                text="Check settings changed. Click Run File Check again.",
                fg=WARN,
            )
            self._set_status("Check settings changed. Run File Check again before continuing.", WARN)
            self._next_ok(False)

    def _restore_validation(self):
        if self._validation_results:
            for result in self._validation_results:
                self._val_tree.insert("", "end",
                                      values=(result["status"], result["name"], result["detail"]),
                                      tags=(result["tag"],))
        else:
            pass_set = {id(s) for s in self.passed_srcs}
            for src in self.all_sources:
                passed = id(src) in pass_set
                tag    = "pass" if passed else "fail"
                status = "PASS" if passed else "FAIL"
                self._val_tree.insert("", "end",
                                      values=(status, src["display_name"], ""),
                                      tags=(tag,))
        n = len(self.passed_srcs)
        t = len(self.all_sources)
        self._val_detail.config(text=f"{n} of {t} files passed.", fg=OK if n else ERR)
        if hasattr(self, "_val_summary_lbl") and self._validation_summary:
            self._val_summary_lbl.config(text=self._format_validation_summary(), fg=MUTE)
        self._val_prog["value"] = t
        if n:
            self._next_ok(True)

    def _start_validation_timer(self, total):
        self._validation_started_at = time.time()
        self._validation_total = total
        self._validation_done = 0
        if self._validation_timer_id:
            self.after_cancel(self._validation_timer_id)
            self._validation_timer_id = None
        self._tick_validation_timer()

    def _stop_validation_timer(self):
        if self._validation_timer_id:
            self.after_cancel(self._validation_timer_id)
            self._validation_timer_id = None

    def _tick_validation_timer(self):
        if self._validation_started_at is None:
            return
        elapsed = time.time() - self._validation_started_at
        total = self._validation_total or len(self.all_sources) or 1
        done = self._validation_done
        eta = None
        if done > 0:
            eta = elapsed * max(0, total - done) / done
        eta_text = "--" if eta is None else self._format_time(eta)
        self._note_operation_progress(done / total * 100)
        self._operation_eta = eta
        self._operation_detail = f"{done}/{total} files checked"
        if hasattr(self, "_val_detail"):
            self._val_detail.config(
                text=(
                    f"Validating {done}/{total} files  |  "
                    f"Elapsed: {self._format_time(elapsed)}  |  ETA: {eta_text}"
                ),
                fg=MUTE,
            )
        self._validation_timer_id = self.after(1000, self._tick_validation_timer)

    def _format_validation_summary(self):
        s = self._validation_summary or {}
        if not s:
            return ""
        return (
            f"Summary: pass {s.get('pass', 0)} | warnings {s.get('warn', 0)} | "
            f"failed {s.get('fail', 0)} | missing-column files {s.get('missing', 0)} | "
            f"extra-column files {s.get('extra', 0)} | duplicate-header files {s.get('duplicate', 0)}"
        )

    def _run_validation(self):
        if self._operation_running:
            self._set_status(f"Please wait until {self._operation_label or 'the current operation'} finishes.", WARN)
            return
        ref = self.all_sources[self.ref_idx]
        validation_started = time.time()
        try:
            self._sync_layout_options_from_ui()
        except ValueError as e:
            self._show_error_with_details(
                "Layout settings",
                "The header/footer row settings are not valid.",
                technical_detail=str(e),
                action="Use whole numbers only. Header row must be 1 or greater; footer rows cannot be negative.",
            )
            return
        read_opts = self._get_layout_read_options()
        self.auto_advance_after_validation = bool(
            getattr(self, "_auto_next_var", tk.BooleanVar(value=False)).get()
        )
        self.allow_extra_columns = bool(
            getattr(self, "_allow_extra_cols_var", tk.BooleanVar(value=False)).get()
        )
        if ref["type"] == "xlsx":
            self.auto_match_sheet_enabled = bool(
                getattr(self, "_auto_match_sheet_var", tk.BooleanVar(value=self.auto_match_sheet_enabled)).get()
            )

        for row in self._val_tree.get_children():
            self._val_tree.delete(row)
        self._val_prog["value"] = 0
        self._val_prog["maximum"] = len(self.all_sources) or 1
        self._val_detail.config(text="Running...", fg=MUTE)
        self._set_operation_running(True, "file check")
        self._cancel_validation_requested = False
        if hasattr(self, "_run_validation_btn"):
            self._run_validation_btn.config(state="disabled")
        self._next_ok(False)
        self.passed_srcs = []
        self._source_sheet_map = {}
        self.extra_columns_found = []
        self._validation_summary = {}
        self._validation_results = []
        if hasattr(self, "_val_summary_lbl"):
            self._val_summary_lbl.config(text="", fg=MUTE)
        self._reset_combined_state(clear_filters=True)
        self._start_validation_timer(len(self.all_sources))

        def run():
            self.after(0, lambda: self._operation_file_activity("template", ref["display_name"], True))
            try:
                ref_columns = clean_cols(read_header(ref, sheet=self.selected_sheet, **read_opts))
                dups = dup_cols(ref_columns)
                if dups:
                    raise ValueError(f"Template has duplicate headers: {', '.join(dups)}")
            except Exception as exc:
                self.after(0, lambda err=str(exc): self._validation_failed_done(err))
                return
            self.after(0, lambda: self._operation_file_activity("template", ref["display_name"], False))
            if self._cancel_validation_requested:
                self.after(0, self._validation_cancelled_done)
                return
            self.after(0, lambda cols=ref_columns: setattr(self, "ref_columns", cols))
            passed = []
            extra_columns_found = []
            validation_results = []
            summary = {"pass": 0, "warn": 0, "fail": 0, "missing": 0, "extra": 0, "duplicate": 0}
            allow_extra = self.allow_extra_columns
            auto_match_sheet = self.auto_match_sheet_enabled and ref["type"] == "xlsx"
            source_order = {id(src): idx for idx, src in enumerate(self.all_sources)}

            def validate_source(src):
                file_started = time.time()
                key = source_cache_key(src)
                self.after(0, lambda k=key, n=src["display_name"]: self._operation_file_activity(k, n, True))
                miss, extra, dups = [], [], []
                matched_sheet = None
                sheet_notes = []
                try:
                    signature = source_signature(src)
                    if src["type"] == "xlsx":
                        if src is ref:
                            sh = self.selected_sheet
                            cols = clean_cols(read_header(src, sheet=sh, **read_opts))
                        elif auto_match_sheet:
                            sh, cols, sheet_notes = match_sheet_by_headers(
                                src,
                                ref_columns,
                                reference_sheet=self.selected_sheet,
                                header_row=read_opts["header_row"],
                                footer_rows=read_opts["footer_rows"],
                                allow_extra=allow_extra,
                            )
                        else:
                            sh = resolve_sheet(src, self.selected_sheet)
                            cols = clean_cols(read_header(src, sheet=sh, **read_opts))
                        matched_sheet = sh
                    else:
                        sh = None
                        sheet_notes = []
                        cols = clean_cols(read_header(src, sheet=sh, **read_opts))
                    dups = dup_cols(cols)
                    miss  = [c for c in ref_columns if c not in cols]
                    extra = [c for c in cols if c not in ref_columns]
                    ok = not miss and not extra and not dups
                    ok_with_extra = allow_extra and not miss and extra and not dups
                    if signature != source_signature(src):
                        raise SourceChangedError("Source changed during validation. Run the file check again.")
                    if ok or ok_with_extra:
                        src["_validated_signature"] = signature

                    if ok:
                        tag, status, detail = "pass", "PASS", f"{len(cols)} columns"
                    elif ok_with_extra:
                        tag, status = "warn", "WARN"
                        detail = f"{len(cols)} columns; extra appended: {', '.join(extra[:3])}{'...' if len(extra)>3 else ''}"
                    else:
                        parts = []
                        if miss:  parts.append(f"missing: {', '.join(miss[:3])}{'...' if len(miss)>3 else ''}")
                        if extra: parts.append(f"extra: {', '.join(extra[:3])}{'...' if len(extra)>3 else ''}")
                        if dups: parts.append(f"dup cols: {', '.join(dups)}")
                        tag, status, detail = "fail", "FAIL", ";  ".join(parts)
                    if sheet_notes:
                        detail = detail + "; " + "; ".join(sheet_notes)
                except Exception as e:
                    category, err_detail = self._classify_file_error(e)
                    tag, status, detail = "fail", "FAIL", f"{category}: {err_detail}"

                outcome = "PASS" if tag in ("pass", "warn") else "FAIL"
                elapsed = time.time() - file_started
                self.after(0, lambda k=key: self._operation_file_activity(k, "", False))
                return {
                    "src": src,
                    "tag": tag,
                    "status": status,
                    "name": src["display_name"],
                    "detail": detail,
                    "miss": miss,
                    "extra": extra,
                    "dups": dups,
                    "sheet": matched_sheet,
                    "outcome": outcome,
                    "elapsed": elapsed,
                }

            workers = min(6, max(1, len(self.all_sources)))
            with ThreadPoolExecutor(max_workers=workers) as ex:
                futures = [ex.submit(validate_source, src) for src in self.all_sources]
                for i, fut in enumerate(as_completed(futures), start=1):
                    if self._cancel_validation_requested:
                        for pending in futures:
                            pending.cancel()
                        break
                    result = fut.result()
                    validation_results.append(result)
                    tag = result["tag"]
                    summary[tag] += 1
                    if result["miss"]:
                        summary["missing"] += 1
                    if result["extra"]:
                        summary["extra"] += 1
                    if result["dups"]:
                        summary["duplicate"] += 1
                    if tag in ("pass", "warn"):
                        passed.append(result["src"])
                        self._source_sheet_map[source_cache_key(result["src"])] = result["sheet"]
                    if tag == "warn":
                        for col in result["extra"]:
                            if col not in extra_columns_found:
                                extra_columns_found.append(col)

                    self._record_perf(
                        f"Validation: {result['name']} -> {result['outcome']} in {result['elapsed']:.2f}s"
                    )
                    self.after(0, lambda r=result: self._val_tree.insert(
                        "", "end", values=(r["status"], r["name"], r["detail"]), tags=(r["tag"],)
                    ))
                    self.after(0, lambda v=i: self._val_prog.configure(value=v))
                    self.after(0, lambda v=i: setattr(self, "_validation_done", v))

            if self._cancel_validation_requested:
                self.after(0, self._validation_cancelled_done)
                return
            validation_results.sort(key=lambda r: source_order.get(id(r["src"]), 0))
            passed = [r["src"] for r in validation_results if r["tag"] in ("pass", "warn")]
            validation_elapsed = time.time() - validation_started
            self._record_perf(
                f"Validation finished in {validation_elapsed:.2f}s "
                f"({len(passed)}/{len(self.all_sources)} files passed)"
            )
            self.after(0, lambda: self._val_finish(passed, validation_elapsed, extra_columns_found, summary, validation_results))

        threading.Thread(target=run, daemon=True).start()

    def _validation_cancelled_done(self):
        self._stop_validation_timer()
        self._validation_started_at = None
        self._set_operation_running(False)
        self.passed_srcs = []
        self._source_sheet_map = {}
        self._validation_results = []
        self._run_validation_btn.config(state="normal")
        self._val_detail.config(text="File check cancelled. Run it again to continue.", fg=WARN)
        self._val_summary_lbl.config(text="Partial results are not approved for combining.", fg=WARN)
        self._next_ok(False)

    def _validation_failed_done(self, detail):
        self._validation_cancelled_done()
        self._val_detail.config(text="Template check failed. Correct the source or settings and retry.", fg=ERR)
        self._show_error_with_details("Template check failed", "The template could not be read or its headers are ambiguous.",
                                      technical_detail=detail,
                                      action="Check the selected worksheet and header row. Close Excel if the file is locked, then retry.")

    def _val_finish(self, passed, validation_elapsed=None, extra_columns_found=None, summary=None, validation_results=None):
        self._set_operation_running(False)
        if hasattr(self, "_run_validation_btn"):
            self._run_validation_btn.config(state="normal")
        self._stop_validation_timer()
        self._validation_started_at = None
        self.passed_srcs = passed
        self.extra_columns_found = list(extra_columns_found or [])
        self._validation_summary = dict(summary or {})
        self._validation_results = list(validation_results or [])
        n, t = len(passed), len(self.all_sources)
        elapsed_note = ""
        if validation_elapsed is not None:
            elapsed_note = f" in {self._format_time(validation_elapsed)}"
        if n:
            extra_note = ""
            if self.extra_columns_found:
                extra_note = f"; {len(self.extra_columns_found)} extra column(s) will be appended"
            self._val_detail.config(text=f"{n} of {t} files passed{elapsed_note}{extra_note} - ready to combine.", fg=OK)
            if hasattr(self, "_val_summary_lbl"):
                self._val_summary_lbl.config(text=self._format_validation_summary(), fg=MUTE)
            if self.auto_advance_after_validation:
                self._set_status(f"{n} file(s) passed validation. Moving to filters...", OK)
            else:
                self._set_status(f"{n} file(s) passed validation. Click Next.", OK)
            self._next_ok(True)
            self._reset_combined_state(clear_filters=True)
            self.extra_columns_found = list(extra_columns_found or [])
            if self.auto_advance_after_validation:
                self.after(700, lambda: self.nav_to(4) if self._current == 3 else None)
        else:
            self._val_detail.config(text=f"0 of {t} files passed{elapsed_note} - cannot continue.", fg=ERR)
            if hasattr(self, "_val_summary_lbl"):
                self._val_summary_lbl.config(text=self._format_validation_summary(), fg=MUTE)
            self._set_status("No files passed validation.", ERR)
            self._next_ok(False)

    # ---------------------------------------------------------
    # STEP 4  -  Combine & Filter
    # ---------------------------------------------------------
    def _page_filters(self):
        self._next_ok(True)
        pad = self._pad()

        header_row = tk.Frame(pad, bg=BG)
        header_row.pack(fill="x")
        tk.Label(header_row, text="Combine & Filter", font=TFH, bg=BG, fg=FG).pack(side="left")
        self._add_filter_btn = _btn(header_row, "+ Add Filter", self._open_filter_dlg, "primary")
        self._add_filter_btn.pack(side="right")
        self._combine_start_btn = _btn(header_row, "Combine Files", self._start_combine, "success", padx=10)
        self._combine_start_btn.pack(side="right", padx=(0, 8))

        tk.Label(pad, text="First combine the checked files. Then optionally add filters before export.",
                 font=TFS, bg=BG, fg=MUTE).pack(anchor="w", pady=(2, 0))

        advanced = tk.Frame(pad, bg=SURF, padx=12, pady=10, highlightthickness=1, highlightbackground=BORD)
        advanced.pack(fill="x", pady=(10, 8))
        adv_header = tk.Frame(advanced, bg=SURF)
        adv_header.pack(fill="x")
        _label(adv_header, "Advanced performance options", TFB, bg=SURF).pack(side="left")
        self._advanced_toggle_lbl = tk.Label(
            adv_header,
            text=("Hide" if self._advanced_options_expanded else "Show"),
            font=TFS,
            bg=SURF,
            fg=ACCH,
            cursor="hand2",
        )
        self._advanced_toggle_lbl.pack(side="right")
        self._advanced_body = tk.Frame(advanced, bg=SURF)

        def _toggle_advanced(*_):
            self._advanced_options_expanded = not self._advanced_options_expanded
            if self._advanced_options_expanded:
                self._advanced_body.pack(fill="x")
                self._advanced_toggle_lbl.config(text="Hide")
            else:
                self._advanced_body.pack_forget()
                self._advanced_toggle_lbl.config(text="Show")

        self._advanced_toggle_lbl.bind("<Button-1>", _toggle_advanced)
        _label(
            self._advanced_body,
            "Most users can leave these on their defaults.",
            TFS,
            fg=MUTE,
            bg=SURF,
        ).pack(anchor="w", pady=(8, 0))
        self._optimize_memory_var = tk.BooleanVar(value=self.optimize_memory_enabled)
        memory_option = tk.Checkbutton(
            self._advanced_body,
            text="Optimize memory after combine (recommended for large files)",
            variable=self._optimize_memory_var,
            bg=SURF,
            fg=FG,
            selectcolor=SURF2,
            activebackground=SURF,
            activeforeground=FG,
            font=TFS,
        )
        memory_option.pack(anchor="w", pady=(6, 0))
        Tooltip(memory_option, "Reduces numeric storage and repeated text. Floats are downcast only when their values round-trip exactly.")
        self._fast_combine_var = tk.BooleanVar(value=self.fast_combine_enabled)
        fast_option = tk.Checkbutton(
            self._advanced_body,
            text="Fast combine mode (parallel reads, uses more memory)",
            variable=self._fast_combine_var,
            bg=SURF,
            fg=FG,
            selectcolor=SURF2,
            activebackground=SURF,
            activeforeground=FG,
            font=TFS,
        )
        fast_option.pack(anchor="w", pady=(3, 0))
        Tooltip(fast_option, "Reads several files at once. May help on fast storage, but uses more RAM. Sequential mode is the safer default.")
        self._deep_quality_var = tk.BooleanVar(value=self.deep_quality_checks_enabled)
        quality_option = tk.Checkbutton(
            self._advanced_body,
            text="Run deeper data quality checks after combine (slower)",
            variable=self._deep_quality_var,
            bg=SURF,
            fg=FG,
            selectcolor=SURF2,
            activebackground=SURF,
            activeforeground=FG,
            font=TFS,
        )
        quality_option.pack(anchor="w", pady=(3, 0))
        Tooltip(quality_option, "Checks blank and duplicate rows without deleting data. Adds processing time; scans are skipped above the configured row limits.")
        _btn(self._advanced_body, "Use recommended settings", self._recommended_performance,
             "ghost", padx=8, pady=4).pack(anchor="w", pady=(8, 0))
        self._performance_note = _label(self._advanced_body, "Choose these settings before clicking Combine Files.",
                                        TFS, fg=MUTE, bg=SURF, wraplength=470)
        self._performance_note.pack(anchor="w", pady=(6, 0))
        self._register_operation_controls(self._advanced_body)
        if self._advanced_options_expanded:
            self._advanced_body.pack(fill="x")

        # info bar
        self._filter_info = tk.Label(pad, text="", font=TFS, bg=BG, fg=MUTE, justify="left", anchor="w")
        self._filter_info.pack(fill="x", pady=(0, 8))
        self._filter_info.bind("<Configure>", lambda e: self._filter_info.config(wraplength=max(200, e.width - 8)))

        self._combine_progress_frame = tk.Frame(
            pad,
            bg=SURF,
            padx=12,
            pady=10,
            highlightthickness=1,
            highlightbackground=BORD,
        )
        self._combine_progress_frame.pack(fill="x", pady=(0, 10))
        tk.Label(self._combine_progress_frame, text="Combine progress", font=TFB, bg=SURF, fg=FG).pack(anchor="w")
        self._combine_prog = ttk.Progressbar(
            self._combine_progress_frame,
            style="File.Horizontal.TProgressbar",
            mode="determinate",
            maximum=100,
        )
        self._combine_prog.pack(fill="x", pady=(8, 4))
        self._combine_progress_text = tk.Label(
            self._combine_progress_frame,
            text="Waiting to combine",
            font=TFS,
            bg=SURF,
            fg=MUTE,
        )
        self._combine_progress_text.pack(anchor="w")
        self._combine_progress_meta = tk.Label(
            self._combine_progress_frame,
            text="Elapsed: 0s  |  ETA: --",
            font=TFS,
            bg=SURF,
            fg=MUTE,
        )
        self._combine_progress_meta.pack(anchor="w", pady=(2, 0))
        self._combine_cancel_btn = _btn(
            self._combine_progress_frame,
            "Cancel Combine",
            self._cancel_combine,
            "danger",
            padx=10,
            pady=4,
        )
        self._combine_cancel_btn.pack(anchor="w", pady=(8, 0))

        self._quality_info = tk.Label(pad, text="", font=TFS, bg=BG, fg=MUTE, justify="left")
        self._quality_info.pack(anchor="w", pady=(0, 8))

        # filter list
        self._filter_frame = tk.Frame(pad, bg=BG)
        self._filter_frame.pack(fill="both", expand=True)

        # combine sources if not yet done
        if self.final_df is None:
            self._add_filter_btn.config(state="disabled", cursor="arrow")
            self._combine_cancel_btn.config(state="disabled")
            self._filter_info.config(text=f"Ready: {len(self.passed_srcs)} checked files. Click Combine Files to load your data.", fg=MUTE)
            self._next_ok(False)
            if self.auto_advance_after_validation:
                self.after_idle(self._start_combine)
        else:
            self._combine_start_btn.config(state="disabled")
            self._freeze_performance_options()
            self._combine_progress_frame.pack_forget()
            self._add_filter_btn.config(state="normal", cursor="hand2")
            self._update_filter_info()
            self._redraw_filters()

        self._set_status("Combine first, then add optional filters or click Next to export.", MUTE)

    def _recommended_performance(self):
        self._optimize_memory_var.set(True)
        self._fast_combine_var.set(False)
        self._deep_quality_var.set(False)

    def _freeze_performance_options(self):
        for widget in self._advanced_body.winfo_children():
            if isinstance(widget, (tk.Checkbutton, tk.Button)):
                widget.config(state="disabled")
        self._performance_note.config(text="These settings were applied to the loaded data. Go back and run the file check again to change them.")

    def _start_combine(self):
        if self._operation_running or self.final_df is not None or not self.passed_srcs:
            return
        self.optimize_memory_enabled = bool(self._optimize_memory_var.get())
        self.fast_combine_enabled = bool(self._fast_combine_var.get())
        self.deep_quality_checks_enabled = bool(self._deep_quality_var.get())
        self._combine_start_btn.config(state="disabled")
        self._combine_cancel_btn.config(state="normal")
        self._set_operation_running(True, "combine")
        self._filter_info.config(text="Combining checked files...", fg=MUTE)
        self._next_ok(False)
        self._cancel_combine_requested = False
        threading.Thread(target=self._combine_bg, daemon=True).start()

    def _cancel_combine(self):
        self._cancel_combine_requested = True
        self._set_status("Cancel requested. Combine will stop after the current file.", WARN)
        if hasattr(self, "_combine_cancel_btn"):
            self._combine_cancel_btn.config(state="disabled")
        self._next_ok(False)
        self._operation_detail = "Cancel requested; waiting for the current file"
        self._operation_cancel_btn.config(state="disabled", text="Stopping...")
        self._operation_cancel_pending = True

    def _combine_cancelled_done(self):
        self.final_df = None
        self._invalidate_filtered_cache(clear_series=True)
        self._set_operation_running(False)
        if hasattr(self, "_combine_start_btn"):
            self._combine_start_btn.config(state="normal")
        self._update_combine_progress(percent=0, status="Combine cancelled", eta=None)
        self._set_status("Combine cancelled.", WARN)
        if hasattr(self, "_add_filter_btn"):
            self._add_filter_btn.config(state="disabled", cursor="arrow")
        if hasattr(self, "_combine_cancel_btn"):
            self._combine_cancel_btn.config(state="disabled")

    def _update_combine_progress(
        self,
        *,
        percent=None,
        files_done=None,
        total_files=None,
        bytes_done=None,
        total_bytes=None,
        elapsed=None,
        eta=None,
        ram_mb=None,
        status=None,
    ):
        if percent is not None:
            self._note_operation_progress(percent)
        self._operation_eta = eta
        self._operation_detail = f"{status or 'Combining'} | {files_done}/{total_files} files" if total_files else status or "Combining"
        if hasattr(self, "_combine_prog") and percent is not None:
            self._combine_prog.configure(value=max(0, min(100, percent)))
        if hasattr(self, "_combine_progress_text"):
            parts = []
            if status:
                parts.append(status)
            if files_done is not None and total_files:
                parts.append(f"{files_done}/{total_files} files")
            if percent is not None:
                parts.append(f"{int(percent)}%")
            if bytes_done is not None and total_bytes:
                parts.append(f"{self._format_size(bytes_done)} / {self._format_size(total_bytes)}")
            self._combine_progress_text.config(text="  |  ".join(parts) if parts else "Combining files", fg=MUTE)
        if hasattr(self, "_combine_progress_meta"):
            meta = []
            if elapsed is not None:
                meta.append(f"Elapsed: {self._format_time(elapsed)}")
            if eta is not None:
                meta.append(f"ETA: {self._format_time(eta)}")
            else:
                meta.append("ETA: --")
            if ram_mb is not None:
                meta.append(f"RAM: {ram_mb:.0f}MB")
            self._combine_progress_meta.config(text="  |  ".join(meta), fg=MUTE)

    def _source_size(self, src):
        try:
            if src["mode"] == "direct":
                return os.path.getsize(src["full_path"])
            with zipfile.ZipFile(src["zip_path"], "r") as z:
                return z.getinfo(src["inner_name"]).file_size
        except Exception:
            return 0

    def _choose_combine_workers(self, total_bytes):
        sources = self.passed_srcs or []
        if len(sources) <= 1:
            return 1
        has_excel = any(src.get("type") == "xlsx" for src in sources)
        cpu_cap = max(1, (os.cpu_count() or 2) // 2)
        base_cap = min(4, cpu_cap, len(sources))
        if has_excel:
            base_cap = min(base_cap, 2)
        if total_bytes >= 1024 ** 3:
            base_cap = min(base_cap, 2)
        return max(1, base_cap)

    def _combine_bg(self):
        try:
            self._combine_bg_impl()
        except CancelledOperation:
            self.after(0, self._combine_cancelled_done)
        except Exception as exc:
            self.after(0, lambda err=str(exc): self._combine_failed_done(err))

    def _combine_failed_done(self, detail):
        self.final_df = None
        self._invalidate_filtered_cache(clear_series=True)
        self._set_operation_running(False)
        self._update_combine_progress(percent=0, status="Combine failed", eta=None)
        self._add_filter_btn.config(state="disabled", cursor="arrow")
        self._combine_cancel_btn.config(state="disabled")
        self._next_ok(False)
        self._combine_start_btn.config(state="normal")
        self._set_status("Combine stopped. Run the file check again before retrying.", ERR)
        self._show_error_with_details(
            "Combine failed", "MergeGuru could not safely combine all approved files.",
            technical_detail=detail,
            action="Check the source files, then go back and run the file check again.",
        )

    def _combine_bg_impl(self):
        ref = self.all_sources[self.ref_idx]
        read_opts = self._get_layout_read_options()

        total_bytes = 0
        for src in self.passed_srcs:
            try:
                if src["mode"] == "direct":
                    total_bytes += os.path.getsize(src["full_path"])
                else:
                    with zipfile.ZipFile(src["zip_path"], "r") as z:
                        info = z.getinfo(src["inner_name"])
                        total_bytes += info.file_size
            except Exception:
                pass

        is_safe, warning_msg, avail_gb, needed_gb = check_memory_before_combine(total_bytes, len(self.passed_srcs))

        if not is_safe:
            self.after(0, lambda: messagebox.showwarning(
                "Memory Warning",
                warning_msg + "\n\nRecommendation: close Excel/other heavy apps, keep memory optimization enabled, and use CSV or Parquet for very large exports.",
                parent=self))

        self.after(0, lambda: self._set_status(f"Combining {len(self.passed_srcs)} files (~{self._format_size(total_bytes)})...", MUTE))
        self.after(0, lambda: self._update_combine_progress(
            percent=0,
            files_done=0,
            total_files=len(self.passed_srcs),
            bytes_done=0,
            total_bytes=total_bytes,
            elapsed=0,
            eta=None,
            status="Starting combine",
        ))

        bytes_processed = 0
        start_time = time.time()
        frames = []
        frame_results = []
        max_ram_seen = 0
        timing_log = []
        source_count = len(self.passed_srcs)
        fast_mode = bool(self.fast_combine_enabled and source_count > 1)
        max_workers = self._choose_combine_workers(total_bytes) if fast_mode else 1
        if fast_mode:
            self._record_perf(f"Fast combine mode enabled with {max_workers} worker(s).")

        def mark_progress(files_completed, file_size):
            nonlocal bytes_processed, max_ram_seen
            bytes_processed += file_size or 0
            current_ram_mb = get_process_ram_usage_mb()
            if current_ram_mb is not None:
                max_ram_seen = max(max_ram_seen, current_ram_mb)
            elapsed = time.time() - start_time
            if bytes_processed > 0:
                bytes_per_sec = bytes_processed / elapsed if elapsed > 0 else 0
                remaining_bytes = total_bytes - bytes_processed
                eta_secs = remaining_bytes / bytes_per_sec if bytes_per_sec > 0 else 0
                files_pct = int((files_completed / source_count * 100)) if source_count else 0
                bytes_pct = int((bytes_processed / total_bytes * 100)) if total_bytes else files_pct
                progress_pct = max(0, min(95, bytes_pct))
                ram_status = f" | RAM: {current_ram_mb:.0f}MB" if current_ram_mb is not None else ""
                mode_note = "Fast combining" if fast_mode else "Combining"
                status_msg = (f"{mode_note}: {files_completed}/{source_count} files ({files_pct}%) "
                              f"| {self._format_size(bytes_processed)} / {self._format_size(total_bytes)}"
                              + ram_status + f" | ETA: {self._format_time(eta_secs)}")
                self.after(0, lambda m=status_msg: self._set_status(m, MUTE))
                self.after(0, lambda pct=progress_pct, done=files_completed, elapsed=elapsed,
                           eta=eta_secs, ram=current_ram_mb, b_done=bytes_processed, status=mode_note:
                           self._update_combine_progress(
                               percent=pct,
                               files_done=done,
                               total_files=source_count,
                               bytes_done=b_done,
                               total_bytes=total_bytes,
                               elapsed=elapsed,
                               eta=eta,
                               ram_mb=ram,
                               status=status,
                           ))

        def load_one(index, src):
            if self._cancel_combine_requested:
                raise CancelledOperation("Combine cancelled.")
            file_start = time.time()
            key = source_cache_key(src)
            self.after(0, lambda k=key, n=src["display_name"]: self._operation_file_activity(k, n, True))
            file_size = self._source_size(src)
            if src["type"] != "xlsx":
                sh = None
            else:
                sh = self._source_sheet_map.get(source_cache_key(src))
                if sh is None:
                    sh = self.selected_sheet if src is ref else resolve_sheet(src, self.selected_sheet)
            df = prepare_source_frame(src, self.ref_columns, sheet=sh,
                                      allow_extra=self.allow_extra_columns, **read_opts)
            file_elapsed = time.time() - file_start
            self.after(0, lambda k=key: self._operation_file_activity(k, "", False))
            return {
                "index": index,
                "source": src,
                "df": df,
                "file_size": file_size,
                "elapsed": file_elapsed,
                "rows": len(df),
            }

        def handle_result(result, files_completed):
            frame_results.append(result)
            timing_log.append((result["source"]["display_name"], result["elapsed"], result["rows"]))
            self._record_perf(
                f"Combine read: {result['source']['display_name']} -> {result['rows']:,} rows in {result['elapsed']:.2f}s"
            )
            mark_progress(files_completed, result["file_size"])

        if fast_mode:
            completed = 0
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                future_map = {
                    ex.submit(load_one, i, src): (i, src)
                    for i, src in enumerate(self.passed_srcs)
                }
                for fut in as_completed(future_map):
                    if self._cancel_combine_requested:
                        self._record_perf("Combine cancelled by user during fast combine.")
                        for pending in future_map:
                            pending.cancel()
                        raise CancelledOperation("Combine cancelled.")
                    i, src = future_map[fut]
                    try:
                        completed += 1
                        handle_result(fut.result(), completed)
                    except Exception as e:
                        mark_progress(completed, self._source_size(src))
                        self._record_perf(
                            f"Combine read failed: {src['display_name']} ({e})"
                        )
                        raise
        else:
            for i, src in enumerate(self.passed_srcs):
                if self._cancel_combine_requested:
                    self._record_perf("Combine cancelled by user before next file.")
                    self.after(0, self._combine_cancelled_done)
                    return
                try:
                    handle_result(load_one(i, src), i + 1)
                except Exception as e:
                    mark_progress(i + 1, self._source_size(src))
                    self._record_perf(
                        f"Combine read failed: {src['display_name']} ({e})"
                    )
                    raise

        concat_start = time.time()
        self.after(0, lambda: self._update_combine_progress(
            percent=96,
            files_done=len(self.passed_srcs),
            total_files=len(self.passed_srcs),
            bytes_done=total_bytes,
            total_bytes=total_bytes,
            elapsed=time.time() - start_time,
            eta=None,
            status="Finalizing dataset",
        ))
        if frame_results:
            final_columns = list(self.ref_columns)
            if self.allow_extra_columns:
                extra_columns = [c for c in self.extra_columns_found if c not in final_columns]
                for result in sorted(frame_results, key=lambda item: item["index"]):
                    for col in result["df"].columns:
                        if col not in final_columns and col not in extra_columns:
                            extra_columns.append(col)
                self.extra_columns_found = extra_columns
                final_columns += extra_columns
            provenance = provenance_column(final_columns)
            for result in frame_results:
                result["df"][provenance] = result["source"]["display_name"]
            final_columns.append(provenance)
            frames = [
                result["df"].reindex(columns=final_columns)
                for result in sorted(frame_results, key=lambda item: item["index"])
            ]
            batch_size = 10
            rolling_frames = []
            for start in range(0, len(frames), batch_size):
                batch = frames[start:start + batch_size]
                rolling_frames.append(pd.concat(batch, ignore_index=True))
            frames.clear()
            self.final_df = pd.concat(rolling_frames, ignore_index=True)
            rolling_frames.clear()
            if self._cancel_combine_requested:
                self.final_df = None
                self.after(0, self._combine_cancelled_done)
                return
            self._data_quality_summary = self._build_data_quality_summary(self.final_df)
            if self.optimize_memory_enabled:
                optimize_start = time.time()
                self.after(0, lambda: self._update_combine_progress(
                    percent=98,
                    files_done=len(self.passed_srcs),
                    total_files=len(self.passed_srcs),
                    bytes_done=total_bytes,
                    total_bytes=total_bytes,
                    elapsed=time.time() - start_time,
                    eta=None,
                    status="Optimizing memory",
                ))
                try:
                    self.final_df, mem_stats = optimize_dataframe_memory(self.final_df)
                    self._last_memory_optimization = mem_stats
                    self._record_perf(
                        "Memory optimization: "
                        f"{(mem_stats.get('before_mb') or 0):.1f}MB -> {(mem_stats.get('after_mb') or 0):.1f}MB "
                        f"(saved {(mem_stats.get('saved_mb') or 0):.1f}MB) "
                        f"| ints: {mem_stats.get('int_cols', 0)}, "
                        f"floats: {mem_stats.get('float_cols', 0)}, "
                        f"categories: {mem_stats.get('category_cols', 0)} "
                        f"in {time.time() - optimize_start:.2f}s"
                    )
                except Exception as e:
                    self._last_memory_optimization = None
                    self._record_perf(f"Memory optimization skipped: {e}")
            self._invalidate_filtered_cache(clear_series=True)
        if self._cancel_combine_requested:
            self.final_df = None
            self.after(0, self._combine_cancelled_done)
            return
        concat_elapsed = time.time() - concat_start

        total_elapsed = time.time() - start_time
        timing_summary = f"Combine timing: {len(timing_log)} files in {total_elapsed:.2f}s (concat: {concat_elapsed:.2f}s)"
        for fname, elapsed, rows in timing_log:
            timing_summary += f"\n  - {fname}: {elapsed:.2f}s ({rows:,} rows)"
        if max_ram_seen:
            timing_summary += f"\n  Peak RAM observed: {max_ram_seen:.0f}MB"

        self._last_combine_timing = timing_summary
        for line in timing_summary.splitlines():
            self._record_perf(line)

        self.after(0, self._combine_done)
    
    def _format_size(self, bytes_val):
        """Format bytes into readable size (MB, GB, etc.)"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_val < 1024.0:
                return f"{bytes_val:.1f}{unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:.1f}PB"

    def _combine_done(self):
        self._set_operation_running(False)
        if self.final_df is not None:
            self._freeze_performance_options()
            self._update_combine_progress(percent=100, status="Combine complete", eta=0)
            if hasattr(self, "_combine_cancel_btn"):
                self._combine_cancel_btn.config(state="disabled")
            if hasattr(self, "_add_filter_btn"):
                self._add_filter_btn.config(state="normal", cursor="hand2")
            if hasattr(self, "_quality_info"):
                self._quality_info.config(text=self._format_quality_summary(), fg=MUTE)
            self._update_filter_info()
            self._next_ok(True)
        else:
            self._update_combine_progress(percent=0, status="Combine failed", eta=None)
            if hasattr(self, "_add_filter_btn"):
                self._add_filter_btn.config(state="disabled", cursor="arrow")
            self._filter_info.config(text="Failed to combine files.", fg=ERR)

    def _update_filter_info(self):
        if self.final_df is not None:
            filtered = self._get_filtered_view()
            r, c = len(self.final_df), len(self.final_df.columns)
            shown = len(filtered) if filtered is not None else r
            memory_note = ""
            if self._last_memory_optimization:
                after_mb = self._last_memory_optimization.get("after_mb")
                saved_mb = self._last_memory_optimization.get("saved_mb")
                if after_mb is not None and saved_mb is not None:
                    memory_note = f"  |  Memory: {after_mb:.1f}MB (saved {saved_mb:.1f}MB)"
            extra_note = ""
            if self.allow_extra_columns and self.extra_columns_found:
                extra_note = f"  |  Extra columns appended: {len(self.extra_columns_found)}"
            self._filter_info.config(
                text=(
                    f"Combined dataset: {r:,} rows  |  {c} columns  |  "
                    f"{len(self.filters)} filter(s){memory_note}{extra_note}"
                ),
                fg=MUTE)
            if hasattr(self, "_quality_info"):
                self._quality_info.config(text=self._format_quality_summary(), fg=MUTE)
        self._redraw_filters()

    def _get_filtered_view(self):
        if self.final_df is None:
            return None
        try:
            return self._compute_filtered_result()
        except Exception:
            return self.final_df

    def _open_filter_dlg(self):
        if self.final_df is None:
            self._set_status("Filters will be available after combine completes.", WARN)
            return
        active_df = self._get_filtered_view()
        if active_df is None or active_df.empty:
            messagebox.showinfo(
                "No rows left",
                "The current filters leave no rows to refine. Remove a filter to continue.",
                parent=self,
            )
            return
        FilterDialog(self, list(self.final_df.columns), active_df, self._add_filter, self.filters)

    def _add_filter(self, fc):
        self.filters.append(fc)
        self._invalidate_filtered_cache(clear_series=False)
        self._update_filter_info()

    def _edit_filter(self, idx):
        if self.final_df is None or idx < 0 or idx >= len(self.filters):
            return
        other_filters = [fc for i, fc in enumerate(self.filters) if i != idx]
        active_df = self._compute_filtered_view_for_filters(other_filters)
        if active_df is None or active_df.empty:
            messagebox.showinfo(
                "No rows left",
                "The other active filters leave no rows to refine. Remove a filter to continue.",
                parent=self,
            )
            return

        def _save_edited_filter(updated_fc):
            self.filters[idx] = updated_fc
            self._invalidate_filtered_cache(clear_series=False)
            self._update_filter_info()

        FilterDialog(
            self,
            list(self.final_df.columns),
            active_df,
            _save_edited_filter,
            other_filters,
            existing_filter=self.filters[idx],
        )

    def _remove_filter(self, idx):
        self.filters.pop(idx)
        self._invalidate_filtered_cache(clear_series=False)
        self._update_filter_info()

    def _clear_filters(self):
        if not self.filters:
            return
        self.filters = []
        self._invalidate_filtered_cache(clear_series=False)
        self._update_filter_info()
        self._set_status("Filters cleared. Combined data is still loaded.", OK)

    def _reuse_combined_for_filter_export(self):
        if self.final_df is None:
            self._set_status("No combined data is loaded.", WARN)
            return
        self.nav_to(4)
        self._set_status("Combined data reused. Adjust filters and export again.", OK)

    def _redraw_filters(self):
        for w in self._filter_frame.winfo_children():
            w.destroy()
        if not self.filters:
            tk.Label(self._filter_frame,
                     text="No filters - all rows will be included in the export.",
                     font=TFS, bg=BG, fg=MUTE).pack(anchor="w")
            return
        tk.Label(self._filter_frame, text="Applied filters",
                 font=TFB, bg=BG, fg=FG).pack(anchor="w", pady=(0, 6))
        _btn(self._filter_frame, "Clear All Filters", self._clear_filters, "ghost",
             padx=10, pady=4).pack(anchor="w", pady=(0, 6))
        for i, fc in enumerate(self.filters):
            row = tk.Frame(self._filter_frame, bg=SURF2, pady=7, padx=12)
            row.pack(fill="x", pady=2)
            tag_f = tk.Frame(row, bg=ACC, width=3)
            tag_f.pack(side="left", fill="y", padx=(0, 10))
            tk.Label(row, text=filter_summary(fc), font=TF, bg=SURF2, fg=FG,
                     anchor="w").pack(side="left", fill="x", expand=True)
            _btn(row, "Edit", lambda i=i: self._edit_filter(i), "ghost",
                 padx=10, pady=3).pack(side="right", padx=(0, 6))
            _btn(row, "X", lambda i=i: self._remove_filter(i), "danger",
                 padx=8, pady=3).pack(side="right")

    # ---------------------------------------------------------
    # STEP 5  -  Export
    # ---------------------------------------------------------
    def _page_export(self):
        self._next_ok(True)
        self._btn_next.config(text="Finish (Close)", state="normal" if not self._operation_running else "disabled")
        pad = self._pad()
        self._page_header(pad, "Export", "Review the result and save the output file.")
        self._save_state_lbl = _label(pad, "", TFB, fg=WARN, wraplength=480)
        self._save_state_lbl.pack(anchor="w", pady=(0, 8))
        self._refresh_save_state()

        # summary row
        if self.final_df is not None:
            r, c = len(self.final_df), len(self.final_df.columns)
            tk.Label(pad,
                     text=f"Input  >  {len(self.passed_srcs)} files  |  {r:,} rows  |  {c} cols  |  {len(self.filters)} filter(s)",
                     font=TFS, bg=BG, fg=MUTE).pack(anchor="w", pady=(0, 10))

        # output path row
        path_row = tk.Frame(pad, bg=BG)
        path_row.pack(fill="x")
        tk.Label(path_row, text="Output file:", font=TFB, bg=BG, fg=FG).pack(side="left")
        export_format = getattr(self, "_preferred_export_format", "Excel")
        default = self._make_auto_export_path(export_format)
        self._out_var = tk.StringVar(value=default)
        self._export_fmt_var = tk.StringVar(value=export_format)
        self._export_fmt_var.trace_add("write", self._on_export_format_changed)
        _btn(path_row, "Browse", self._pick_out_path, "ghost", padx=8, pady=4).pack(side="right")
        _entry(path_row, textvariable=self._out_var, width=24).pack(side="left", fill="x", expand=True, padx=(8, 6), ipady=4)

        fmt_row = tk.Frame(pad, bg=BG)
        fmt_row.pack(fill="x", pady=(10, 0))
        tk.Label(fmt_row, text="Export format:", font=TFB, bg=BG, fg=FG).pack(side="left")
        ttk.Combobox(fmt_row, textvariable=self._export_fmt_var,
                     values=list(EXPORT_FORMATS.keys()), state="readonly",
                     width=20).pack(side="left", padx=(8, 0))
        self._csv_unique_hint = tk.Label(
            pad,
            text="Select CSV-Unique text to choose protected text columns.",
            font=TFS,
            bg=BG,
            fg=MUTE,
        )
        self._csv_unique_hint.pack(anchor="w", pady=(4, 0))

        # Column selection for CSV-Unique text format (conditional)
        self._unique_col_frame = tk.Frame(
            pad,
            bg=SURF,
            padx=12,
            pady=10,
            highlightthickness=1,
            highlightbackground=ACC,
        )
        self._unique_col_frame.pack(fill="x", pady=(8, 0))
        tk.Label(self._unique_col_frame, text="CSV-Unique text: pick columns to preserve", font=TFB, bg=SURF, fg=ACCH).pack(anchor="w")
        tk.Label(
            self._unique_col_frame,
            text="Tick ID/code columns that must keep leading zeros or exact text formatting.",
            font=TFS,
            bg=SURF,
            fg=MUTE,
        ).pack(anchor="w", pady=(2, 4))
        
        cols = list(self.final_df.columns) if self.final_df is not None else []
        quick_row = tk.Frame(self._unique_col_frame, bg=SURF)
        quick_row.pack(fill="x", pady=(2, 6))
        self._unique_selected_lbl = tk.Label(
            quick_row,
            text="0 selected",
            font=TFS,
            bg=SURF,
            fg=MUTE,
        )
        self._unique_selected_lbl.pack(side="left")
        _btn(quick_row, "Select All", self._select_all_unique_columns, "ghost", padx=8, pady=3).pack(side="right", padx=(6, 0))
        _btn(quick_row, "Clear", self._clear_unique_columns, "ghost", padx=8, pady=3).pack(side="right")

        picker_shell = tk.Frame(self._unique_col_frame, bg=SURF, highlightthickness=1, highlightbackground=BORD)
        picker_shell.pack(fill="x")
        picker_canvas = tk.Canvas(picker_shell, bg=SURF, height=150, highlightthickness=0)
        picker_scroll = ttk.Scrollbar(picker_shell, orient="vertical", command=picker_canvas.yview)
        picker_canvas.configure(yscrollcommand=picker_scroll.set)
        picker_canvas.pack(side="left", fill="both", expand=True)
        picker_scroll.pack(side="right", fill="y")
        picker_body = tk.Frame(picker_canvas, bg=SURF)
        picker_window = picker_canvas.create_window((0, 0), window=picker_body, anchor="nw")
        picker_body.bind("<Configure>", lambda _e: picker_canvas.configure(scrollregion=picker_canvas.bbox("all")))
        picker_canvas.bind("<Configure>", lambda e: picker_canvas.itemconfigure(picker_window, width=e.width))
        self._unique_col_vars = {}
        for column in cols:
            var = tk.BooleanVar(value=column in getattr(self, "_preferred_unique_columns", []))
            self._unique_col_vars[column] = var
            tk.Checkbutton(
                picker_body,
                text=column,
                variable=var,
                command=self._update_unique_column_count,
                bg=SURF,
                fg=FG,
                selectcolor=SURF2,
                activebackground=SURF,
                activeforeground=FG,
                font=TFS,
                anchor="w",
            ).pack(fill="x", anchor="w", padx=8, pady=1)
        self._update_unique_column_count()
        self._register_operation_controls(path_row)
        self._register_operation_controls(fmt_row)
        self._register_operation_controls(self._unique_col_frame)
        
        # Initially hide the column selection (show only when CSV-Unique text is selected)
        self._unique_col_frame.pack_forget()

        self._export_btns_frame = tk.Frame(pad, bg=BG)
        self._export_btns_frame.pack(fill="x", pady=(10, 0))
        self._run_export_btn = _btn(self._export_btns_frame, "  Run Export  ", self._run_export, "success")
        self._run_export_btn.pack(side="left")
        self._cancel_export_btn = _btn(self._export_btns_frame, "Cancel Export", self._cancel_export, "danger", padx=10, pady=6)
        self._cancel_export_btn.pack(side="left", padx=(8, 0))
        self._cancel_export_btn.config(state="disabled")
        self._auto_open_var = tk.BooleanVar(value=self._auto_open_output)
        auto_open = tk.Checkbutton(pad, text="Open output file automatically after export", variable=self._auto_open_var,
                                  command=lambda: setattr(self, "_auto_open_output", self._auto_open_var.get()),
                                  font=TFS, bg=BG, fg=FG, selectcolor=SURF2, activebackground=BG, activeforeground=FG)
        auto_open.pack(anchor="w", pady=(6, 0))
        self._operation_controls.append(auto_open)
        if hasattr(self, "_close_without_export_btn"):
            self._close_without_export_btn.pack(side="right", padx=(0, 6))

        preview_bar = tk.Frame(pad, bg=BG)
        preview_bar.pack(fill="x", pady=(10, 0))
        _btn(preview_bar, "Preview Filtered Rows", self._refresh_export_preview, "outline",
             padx=10, pady=4).pack(side="left")
        self._preview_rows_var = tk.StringVar(value="25")
        _label(preview_bar, "Rows:", TFS).pack(side="left", padx=(8, 4))
        row_picker = ttk.Combobox(preview_bar, textvariable=self._preview_rows_var, values=("10", "25", "100"), state="readonly", width=4)
        row_picker.pack(side="left")
        row_picker.bind("<<ComboboxSelected>>", lambda _e: self._refresh_export_preview())
        copy_button = _btn(preview_bar, "Copy selected", self._copy_preview_rows, "ghost", padx=8, pady=4)
        copy_button.pack(side="right")
        Tooltip(copy_button, "Select preview rows, then copy their displayed values with column names. Ctrl+C also works.")
        self._preview_status = tk.Label(pad, text="Preview not loaded. Preview uses the combined data already in memory.", font=TFS, bg=BG, fg=MUTE, wraplength=470, justify="left")
        self._preview_status.pack(anchor="w", pady=(4, 0))
        self._register_operation_controls(preview_bar)

        preview_frame = tk.Frame(pad, bg=SURF, highlightthickness=1, highlightbackground=BORD)
        preview_frame.pack(fill="x", pady=(8, 0))
        self._preview_tree = ttk.Treeview(preview_frame, show="headings", height=5)
        preview_vertical = ttk.Scrollbar(preview_frame, orient="vertical", command=self._preview_tree.yview)
        preview_horizontal = ttk.Scrollbar(preview_frame, orient="horizontal", command=self._preview_tree.xview)
        self._preview_tree.config(yscrollcommand=preview_vertical.set, xscrollcommand=preview_horizontal.set)
        preview_frame.columnconfigure(0, weight=1)
        self._preview_tree.grid(row=0, column=0, sticky="ew")
        preview_vertical.grid(row=0, column=1, sticky="ns")
        preview_horizontal.grid(row=1, column=0, sticky="ew")
        self._preview_tree.bind("<Control-c>", self._copy_preview_rows)

        tk.Frame(pad, bg=BORD, height=1).pack(fill="x", pady=12)
        prog_lbl_row = tk.Frame(pad, bg=BG)
        prog_lbl_row.pack(fill="x")
        tk.Label(prog_lbl_row, text="Progress", font=TFB, bg=BG, fg=FG).pack(side="left")
        self._exp_pct = tk.Label(prog_lbl_row, text="", font=TFS, bg=BG, fg=MUTE)
        self._exp_pct.pack(side="right")
        self._exp_prog = ttk.Progressbar(pad, style="File.Horizontal.TProgressbar",
                                          mode="determinate",
                                          maximum=100)
        self._exp_prog.pack(fill="x", pady=(4, 10))

        stats_card = tk.Frame(pad, bg=SURF, padx=12, pady=10, highlightthickness=1, highlightbackground=BORD)
        stats_card.pack(fill="x", pady=(0, 10))
        stats_top = tk.Frame(stats_card, bg=SURF)
        stats_top.pack(fill="x")
        _label(stats_top, "Export details", TFB, bg=SURF).pack(side="left")
        self._exp_detail_status = tk.Label(stats_top, text="Waiting to start", font=TFS, bg=SURF, fg=MUTE)
        self._exp_detail_status.pack(side="right")

        stats_grid = tk.Frame(stats_card, bg=SURF)
        stats_grid.pack(fill="x", pady=(8, 0))
        self._exp_elapsed = tk.Label(stats_grid, text="Elapsed: 0s", font=TFS, bg=SURF, fg=FG)
        self._exp_elapsed.grid(row=0, column=0, sticky="w", padx=(0, 18))
        self._exp_eta = tk.Label(stats_grid, text="ETA: --", font=TFS, bg=SURF, fg=FG)
        self._exp_eta.grid(row=0, column=1, sticky="w", padx=(0, 18))
        self._exp_size = tk.Label(stats_grid, text="Output size: --", font=TFS, bg=SURF, fg=FG)
        self._exp_size.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

        # live log
        self._exp_log = tk.Text(pad, bg=SURF, fg=FG, font=TMO, height=6, bd=0,
                                 state="disabled",
                                 highlightthickness=1, highlightbackground=BORD)
        self._exp_log.pack(fill="both", expand=True)
        self._exp_log.tag_configure("ok",   foreground=OK)
        self._exp_log.tag_configure("err",  foreground=ERR)
        self._exp_log.tag_configure("info", foreground=MUTE)
        self._exp_log.tag_configure("head", foreground=ACC, font=(_FAM, 9, "bold"))
        for line in self._perf_log[-20:]:
            self._log(line, "info")

        self._history_frame = tk.Frame(pad, bg=BG)
        self._history_frame.pack(fill="x", pady=(8, 0))
        self._redraw_export_history()
        self._on_export_format_changed()

        self._set_status("Set an output path and click Run Export.", MUTE)

    def _refresh_export_preview(self):
        if self.final_df is None or not hasattr(self, "_preview_tree"):
            return
        try:
            filtered = self._compute_filtered_result()
        except Exception as e:
            self._preview_status.config(text=f"Preview failed: {e}", fg=ERR)
            return

        for row in self._preview_tree.get_children():
            self._preview_tree.delete(row)

        cols = list(filtered.columns)
        row_count = int(self._preview_rows_var.get())
        self._preview_tree.configure(columns=cols)
        for col in cols:
            self._preview_tree.heading(col, text=str(col))
            self._preview_tree.column(col, width=140, stretch=False)

        for _, row in filtered.head(row_count).iterrows():
            values = []
            for col in cols:
                val = row.get(col, "")
                values.append("" if pd.isna(val) else str(val))
            self._preview_tree.insert("", "end", values=values)

        self._preview_status.config(
            text=f"Preview: {min(len(filtered), row_count):,} of {len(filtered):,} rows | {len(cols)} columns. Scroll sideways for more columns.",
            fg=OK,
        )

    def _copy_preview_rows(self, _event=None):
        rows = self._preview_tree.selection()
        if not rows:
            self._preview_status.config(text="Select one or more preview rows to copy.", fg=WARN)
            return "break"
        columns = self._preview_tree.cget("columns")
        frame = pd.DataFrame([self._preview_tree.item(row, "values") for row in rows], columns=columns)
        self.clipboard_clear()
        self.clipboard_append(frame.to_csv(sep="\t", index=False))
        self._preview_status.config(text=f"Copied {len(rows)} preview row(s) with column names.", fg=OK)
        return "break"

    def _refresh_save_state(self):
        if hasattr(self, "_save_state_lbl") and self._save_state_lbl.winfo_exists():
            saved = self._has_current_export()
            text = "Current result exported." if saved else "Changes since the last export - export again to save this result." if self._export_history else "Not saved yet - click Run Export to create your output."
            self._save_state_lbl.config(text=text, fg=OK if saved else WARN)

    def _redraw_export_history(self):
        if not hasattr(self, "_history_frame"):
            return
        for w in self._history_frame.winfo_children():
            w.destroy()
        tk.Label(self._history_frame, text="Export history", font=TFB, bg=BG, fg=FG).pack(anchor="w")
        if not self._export_history:
            tk.Label(self._history_frame, text="No exports in this session yet.", font=TFS, bg=BG, fg=MUTE).pack(anchor="w", pady=(2, 0))
            return
        for item in self._export_history[-4:][::-1]:
            row = tk.Frame(self._history_frame, bg=SURF2, padx=10, pady=6)
            row.pack(fill="x", pady=2)
            text = (
                f"{item['time']} | {item['rows']:,} rows | {item['fmt']} | "
                f"{self._format_size(item['size'])} | {os.path.basename(item['path'])}"
            )
            tk.Label(row, text=text, font=TFS, bg=SURF2, fg=FG, anchor="w").pack(side="left", fill="x", expand=True)
            _btn(row, "Open", lambda p=item["path"]: _open_path(p), "ghost", padx=8, pady=3).pack(side="right", padx=(6, 0))
            _btn(row, "Folder", lambda p=os.path.dirname(item["path"]) or ".": _open_path(p), "ghost", padx=8, pady=3).pack(side="right")

    def _cancel_export(self):
        self._cancel_export_requested = True
        self._set_status("Cancel requested. Export will stop at the next safe point.", WARN)
        if hasattr(self, "_cancel_export_btn"):
            self._cancel_export_btn.config(state="disabled")
        self._operation_detail = "Cancel requested; waiting for the current write"
        self._operation_cancel_btn.config(state="disabled", text="Stopping...")
        self._operation_cancel_pending = True

    def _close_without_export(self):
        if self._operation_running:
            self._set_status(f"Please wait until {self._operation_label or 'the current operation'} finishes.", WARN)
            return
        if self._has_current_export() or (self.final_df is None and not self.all_sources):
            self.destroy()
            return
        proceed = messagebox.askyesno(
            "Close without exporting?",
            "The current result has not been exported.\n\nClose anyway? Existing output files will be kept.",
            parent=self,
        )
        if proceed:
            self.destroy()

    def _pick_out_path(self):
        fmt = self._export_fmt_var.get()
        self._preferred_export_format = fmt
        p = filedialog.asksaveasfilename(
            title="Save output as",
            initialdir=self.folder,
            defaultextension=EXPORT_FORMATS[fmt]["extension"],
            filetypes=EXPORT_FORMATS[fmt]["filetypes"])
        if p:
            fmt = detect_export_format(p, fallback=fmt)
            self._export_fmt_var.set(fmt)
            self._out_var.set(ensure_export_extension(p, fmt))

    def _on_export_format_changed(self, *_):
        path = self._out_var.get().strip()
        fmt = self._export_fmt_var.get()
        self._preferred_export_format = fmt
        if path and fmt in EXPORT_FORMATS:
            new_path = ensure_export_extension(path, fmt)
            if new_path != path:
                self._out_var.set(new_path)
        
        # OK Show/hide unique column selector based on format selection
        if fmt == "CSV-Unique text":
            pack_options = {"fill": "x", "pady": (8, 0)}
            if hasattr(self, "_export_btns_frame"):
                pack_options["before"] = self._export_btns_frame
            self._unique_col_frame.pack(**pack_options)
            self._csv_unique_hint.config(text="Select protected columns below before running export.", fg=ACCH)
            self._set_status("CSV-Unique text selected. Pick one or more protected text columns below.", MUTE)
        else:
            self._unique_col_frame.pack_forget()
            self._csv_unique_hint.config(text="Select CSV-Unique text to choose protected text columns.", fg=MUTE)

    def _update_unique_column_count(self):
        if not hasattr(self, "_unique_selected_lbl"):
            return
        selected = self._selected_unique_columns()
        self._preferred_unique_columns = selected
        sample = ", ".join(selected[:3])
        more = f" +{len(selected) - 3} more" if len(selected) > 3 else ""
        detail = f": {sample}{more}" if selected else ""
        self._unique_selected_lbl.config(
            text=f"{len(selected)} selected{detail}",
            fg=OK if selected else MUTE,
        )

    def _select_all_unique_columns(self):
        for var in getattr(self, "_unique_col_vars", {}).values():
            var.set(True)
        self._update_unique_column_count()

    def _clear_unique_columns(self):
        for var in getattr(self, "_unique_col_vars", {}).values():
            var.set(False)
        self._update_unique_column_count()

    def _selected_unique_columns(self):
        if hasattr(self, "_unique_col_vars"):
            return [
                column
                for column, var in self._unique_col_vars.items()
                if bool(var.get())
            ]
        if not hasattr(self, "_unique_col_list"):
            return []
        return [
            self._unique_col_list.get(index)
            for index in self._unique_col_list.curselection()
        ]

    def _update_export_details(self, *, status=UNSET, elapsed=UNSET, eta=UNSET, output_size=UNSET):
        if status is not UNSET:
            self._operation_detail = status
        if eta is not UNSET:
            self._operation_eta = eta
        if hasattr(self, "_exp_detail_status") and status is not UNSET:
            self._exp_detail_status.config(text=status)
        if hasattr(self, "_exp_elapsed") and elapsed is not UNSET:
            self._exp_elapsed.config(text=f"Elapsed: {self._format_time(max(0, elapsed))}")
        if hasattr(self, "_exp_eta") and eta is not UNSET:
            eta_text = "--" if eta is None or math.isinf(eta) else self._format_time(max(0, eta))
            self._exp_eta.config(text=f"ETA: {eta_text}")
        if hasattr(self, "_exp_size") and output_size is not UNSET:
            self._exp_size.config(text=f"Output size: {output_size}")

    def _show_export_success_dialog(self, out_path, out_fmt, row_count, file_size):
        filter_text = "Filters: none"
        if self.filters:
            summaries = [filter_summary(fc) for fc in self.filters[:3]]
            more = f"; +{len(self.filters) - 3} more" if len(self.filters) > 3 else ""
            filter_text = f"Filters: {'; '.join(summaries)}{more}"
        ExportSuccessDialog(
            self,
            out_path,
            out_fmt,
            row_count,
            self._format_size(file_size),
            filter_text=filter_text,
            on_change_filters=self._reuse_combined_for_filter_export,
        )

    def _build_validation_report_df(self):
        rows = []
        results = list(self._validation_results or [])
        if not results and self.all_sources:
            passed_ids = {id(src) for src in self.passed_srcs}
            results = [
                {
                    "src": src,
                    "status": "PASS" if id(src) in passed_ids else "FAIL",
                    "name": src.get("display_name", ""),
                    "detail": "",
                    "sheet": self._source_sheet_map.get(
                        source_cache_key(src), self.selected_sheet
                    ),
                    "miss": [],
                    "extra": [],
                    "dups": [],
                    "elapsed": "",
                }
                for src in self.all_sources
            ]

        for index, result in enumerate(results, start=1):
            src = result.get("src") or {}
            file_type = src.get("type", "")
            mode = src.get("mode", "")
            sheet = result.get("sheet")
            if sheet is None and file_type == "xlsx":
                sheet = self.selected_sheet
            elapsed = result.get("elapsed", "")
            rows.append({
                "No.": index,
                "File Name": result.get("name", ""),
                "File Type": file_type.upper(),
                "Source Mode": "ZIP" if mode == "zip" else "Direct",
                "Validation Status": result.get("status", ""),
                "Matched Sheet": sheet or "",
                "Details": result.get("detail", ""),
                "Missing Columns": ", ".join(result.get("miss") or []),
                "Extra Columns": ", ".join(result.get("extra") or []),
                "Duplicate Columns": ", ".join(result.get("dups") or []),
                "Validation Time (sec)": (
                    round(float(elapsed), 2)
                    if isinstance(elapsed, (int, float))
                    else ""
                ),
            })
        return pd.DataFrame(rows)

    def _run_on_ui_thread_sync(self, fn, allow_user_wait=False):
        if threading.current_thread() is threading.main_thread():
            return fn()

        result = {}
        done = threading.Event()
        started = threading.Event()
        abandoned = threading.Event()

        def wrapper():
            if abandoned.is_set():
                done.set()
                return
            started.set()
            try:
                result["value"] = fn()
            except Exception as e:
                result["error"] = e
            finally:
                done.set()

        self.after(0, wrapper)
        deadline = time.monotonic() + 30
        while not done.wait(timeout=0.25):
            if allow_user_wait and started.is_set():
                continue
            if time.monotonic() >= deadline:
                abandoned.set()
                raise TimeoutError("UI thread did not respond within 30 seconds")
        if "error" in result:
            raise result["error"]
        return result.get("value")

    def _resolve_excel_export_format(self, row_count):
        if row_count + 1 > EXCEL_HARD_ROW_LIMIT:
            choice = self._run_on_ui_thread_sync(
                lambda: messagebox.askyesnocancel(
                    "Excel row limit exceeded",
                    (
                        f"This export has {row_count:,} rows.\n\n"
                        f"Excel supports at most {EXCEL_HARD_ROW_LIMIT - 1:,} data rows plus the header per sheet.\n\n"
                        "Yes: switch to CSV\n"
                        "No: switch to Parquet\n"
                        "Cancel: stop export"
                    ),
                    parent=self,
                ), allow_user_wait=True,
            )
            if choice is True:
                return "CSV"
            if choice is False:
                return "Parquet"
            return None

        if row_count > EXCEL_WARNING_ROW_THRESHOLD:
            choice = self._run_on_ui_thread_sync(
                lambda: messagebox.askyesnocancel(
                    "Large Excel export",
                    (
                        f"This export has {row_count:,} rows.\n\n"
                        "Excel may be slow or memory-heavy for files this large.\n\n"
                        "Yes: continue with Excel\n"
                        "No: switch to CSV\n"
                        "Cancel: stop export"
                    ),
                    parent=self,
                ), allow_user_wait=True,
            )
            if choice is True:
                return "Excel"
            if choice is False:
                return "CSV"
            return None

        return "Excel"

    def _log(self, msg, tag="info"):
        self._exp_log.config(state="normal")
        self._exp_log.insert("end", msg + "\n", tag)
        self._exp_log.see("end")
        self._exp_log.config(state="disabled")

    def _set_export_running(self, running):
        self._set_operation_running(running, "export" if running else "")
        if hasattr(self, "_run_export_btn"):
            self._run_export_btn.config(state="disabled" if running else "normal")
        if hasattr(self, "_cancel_export_btn"):
            self._cancel_export_btn.config(state="normal" if running else "disabled")
        if hasattr(self, "_close_without_export_btn"):
            self._close_without_export_btn.config(state="disabled" if running else "normal")

    def _run_export(self):
        out_fmt = self._export_fmt_var.get()
        raw_out_path = self._out_var.get().strip()
        if not raw_out_path:
            messagebox.showwarning("No path", "Enter an output file path.", parent=self)
            return
        if out_fmt == "CSV-Unique text" and not self._selected_unique_columns():
            messagebox.showwarning(
                "No protected columns",
                "Select at least one text column to protect.",
                parent=self,
            )
            return
        out_path = ensure_export_extension(raw_out_path, out_fmt)
        self._out_var.set(out_path)
        if os.path.exists(out_path):
            if not messagebox.askyesno("Overwrite?",
                                        f"File already exists:\n{out_path}\n\nOverwrite?",
                                        parent=self):
                return

        export_signature = self._result_signature()
        total = len(self.passed_srcs)
        self._exp_prog["maximum"] = 100
        self._exp_prog["value"]   = 0
        self._update_export_details(status="Preparing export", elapsed=0, eta=None, output_size="--")
        self._cancel_export_requested = False
        self._set_export_running(True)

        def run():
            nonlocal out_fmt, out_path
            export_started = time.time()
            self.after(0, lambda: self._log("-" * 52, "head"))
            self.after(0, lambda: self._log("  MergeGuru Export", "head"))
            self.after(0, lambda: self._log("-" * 52, "head"))
            self.after(0, lambda: self._log(""))
            self.after(0, lambda: self._update_export_details(status="Preparing export", elapsed=0, eta=None, output_size="--"))

            if self.final_df is None:
                self.after(0, lambda: self._log("\n  No data to export.", "err"))
                self.after(0, lambda: self._set_export_running(False))
                return

            combined = self.final_df
            combined_rows = len(combined)
            self.after(0, lambda: self._log(f"  Cached combined data:  {combined_rows:,} rows", "ok"))
            self.after(0, lambda: self._exp_prog.configure(value=5))
            self.after(0, lambda: self._exp_pct.configure(text="5%"))
            self.after(0, lambda: self._update_export_details(status="Filtering data", elapsed=time.time() - export_started, eta=None))
            self.after(0, lambda: self._log(f"\n  Combined:  {combined_rows:,} rows", "info"))

            filter_started = time.time()
            try:
                filtered = self._compute_filtered_result()
                filter_stats = list(self._filter_stats_cache)
            except Exception as e:
                self.after(0, lambda err=str(e): self._log(f"  Filter error: {err}", "err"))
                self.after(0, lambda: self._update_export_details(status="Filter error", eta=None))
                self.after(0, lambda: self._set_status("Export stopped because a filter could not be applied.", ERR))
                self.after(0, lambda: self._set_export_running(False))
                self.after(0, lambda err=str(e): self._show_error_with_details(
                    "Filter error", "Export stopped because a filter could not be applied.",
                    technical_detail=err,
                    action="Return to the filters step and correct or remove the invalid filter, then try again.",
                ))
                return
            if self._cancel_export_requested:
                self.after(0, lambda: self._log("  Export cancelled before save.", "info"))
                self.after(0, lambda: self._set_status("Export cancelled.", WARN))
                self.after(0, lambda: self._set_export_running(False))
                return

            for fc, before, after in filter_stats:
                self.after(0, lambda b=before, a=after, c=fc["column"]:
                           self._log(f"  Filter on '{c}':  {b:,} -> {a:,} rows", "info"))
            self._record_perf(
                f"Filter evaluation finished in {time.time() - filter_started:.2f}s "
                f"for {len(self.filters)} filter(s)"
            )

            self.after(0, lambda: self._log(f"  After filters:  {len(filtered):,} rows", "info"))

            num_rows = len(filtered)
            if out_fmt == "Excel":
                resolved_fmt = self._resolve_excel_export_format(num_rows)
                if resolved_fmt is None:
                    self.after(0, lambda: self._log("  Export cancelled before save.", "info"))
                    self.after(0, lambda: self._set_status("Export cancelled.", WARN))
                    self.after(0, lambda: self._set_export_running(False))
                    return
                if resolved_fmt != out_fmt:
                    out_fmt = resolved_fmt
                    out_path = ensure_export_extension(out_path, out_fmt)
                    self.after(0, lambda fmt=out_fmt, path=out_path: (
                        self._export_fmt_var.set(fmt),
                        self._out_var.set(path),
                        self._log(f"  Switched export format to {fmt} for better reliability.", "info")
                    ))
                    if os.path.exists(out_path):
                        overwrite_switched = self._run_on_ui_thread_sync(
                            lambda path=out_path: messagebox.askyesno(
                                "Overwrite?",
                                f"File already exists:\n{path}\n\nOverwrite?",
                                parent=self,
                            ), allow_user_wait=True,
                        )
                        if not overwrite_switched:
                            self.after(0, lambda: self._log("  Export cancelled before save.", "info"))
                            self.after(0, lambda: self._set_status("Export cancelled.", WARN))
                            self.after(0, lambda: self._set_export_running(False))
                            return
            num_cols = len(filtered.columns)
            if out_fmt == "Excel":
                if num_rows > 700000:
                    self.after(0, lambda: self._log(
                        f"  Warning  Very large file ({num_rows:,} rows) - Excel export will be slow", "info"))
                    self.after(0, lambda: self._log(
                        f"     Processing may take several minutes", "info"))

            try:
                self.after(0, lambda: self._log(f"  Saving {num_rows:,} rows, {num_cols} columns...", "info"))
                self.after(0, lambda: self._update_export_details(status=f"Saving {out_fmt}", elapsed=time.time() - export_started, eta=None))
                out_dir = os.path.dirname(out_path) or "."
                if not os.access(out_dir, os.W_OK):
                    raise PermissionError(f"Cannot write to directory: {out_dir}")

                save_started = time.time()
                self.after(0, lambda: self._operation_file_activity("output", os.path.basename(out_path), True))
                # Pass selected text-preservation columns for CSV-Unique text format
                unique_cols = self._run_on_ui_thread_sync(
                    self._selected_unique_columns
                ) if out_fmt == "CSV-Unique text" else []
                if out_fmt == "CSV-Unique text":
                    note = ", ".join(unique_cols) if unique_cols else "none selected"
                    self.after(0, lambda cols=note: self._log(f"  Protecting text columns: {cols}", "info"))
                validation_report_df = (
                    self._run_on_ui_thread_sync(self._build_validation_report_df)
                    if out_fmt == "Excel"
                    else None
                )
                if validation_report_df is not None and not validation_report_df.empty:
                    self.after(0, lambda: self._log(
                        "  Adding worksheet: Validation Report", "info"
                    ))
                
                # OK Create progress callback for real-time feedback
                def progress_callback(pct, msg):
                    elapsed = time.time() - save_started
                    eta = None
                    if pct > 0 and pct < 100:
                        eta = elapsed * (100 - pct) / pct
                    size_text = "Available after save"
                    if pct == 100 and os.path.exists(out_path):
                        try:
                            size_text = self._format_size(os.path.getsize(out_path))
                        except OSError:
                            size_text = "--"
                    self.after(0, lambda p=pct, m=msg: (
                        self._note_operation_progress(p),
                        self._exp_prog.configure(value=p),
                        self._exp_pct.configure(text=f"{p}%"),
                        self._update_export_details(
                            status=f"Writing {out_fmt}",
                            elapsed=elapsed,
                            eta=eta,
                            output_size=size_text,
                        ),
                        self._log(f"  {m}", "info")
                    ))
                
                save_dataframe(
                    filtered,
                    out_path,
                    out_fmt,
                    unique_columns=unique_cols,
                    validation_report_df=validation_report_df,
                    progress_callback=progress_callback,
                    cancel_callback=lambda: self._cancel_export_requested,
                )
                if not os.path.exists(out_path):
                    raise FileNotFoundError(f"Export completed but output file not found: {out_path}")

                save_elapsed = time.time() - save_started
                file_size = os.path.getsize(out_path)
                fname = os.path.basename(out_path)
                audit_path = None
                try:
                    audit_path = self._write_audit_report(out_path, out_fmt, len(filtered), file_size, save_elapsed)
                    self.after(0, lambda p=audit_path: self._log(f"  Audit report: {p}", "ok"))
                except Exception as audit_err:
                    self.after(0, lambda err=str(audit_err): self._log(f"  Audit report failed: {err}", "err"))
                self.after(0, lambda: self._log(f"\n  Saved ->  {out_path}", "ok"))
                self.after(0, lambda: self._log(f"  File size: {self._format_size(file_size)}", "ok"))
                self.after(0, lambda: self._log(f"  Save time: {save_elapsed:.2f}s", "ok"))
                self.after(0, lambda: self._update_export_details(
                    status="Export complete",
                    elapsed=time.time() - export_started,
                    eta=0,
                    output_size=self._format_size(file_size),
                ))
                self.after(0, lambda: self._log("-" * 52, "head"))
                self.after(0, lambda: self._set_status(
                    f"OK  {len(filtered):,} rows exported to {fname}", OK))
                self.after(0, lambda: self._step_prog.configure(value=len(STEP_NAMES)))
                self.after(0, lambda: self._btn_next.configure(state="normal"))
                self.after(0, self._stop_overall_timer)
                history_item = {
                    "time": time.strftime("%H:%M:%S"),
                    "path": out_path,
                    "fmt": out_fmt,
                    "rows": len(filtered),
                    "size": file_size,
                    "audit_path": audit_path,
                }
                self.after(0, lambda: self._complete_export_history(history_item, export_signature))
                # Publish the completed-export signature before controls return to
                # idle so the UI cannot briefly report a successful save as stale.
                self.after(0, lambda: self._set_export_running(False))
                self._record_perf(
                    f"Export finished in {time.time() - export_started:.2f}s "
                    f"(save: {save_elapsed:.2f}s, format: {out_fmt}, rows: {len(filtered):,})"
                )
                self.after(0, lambda: self._show_export_success_dialog(
                    out_path,
                    out_fmt,
                    len(filtered),
                    file_size,
                ))
            except CancelledOperation as e:
                self.after(0, lambda err=str(e): self._log(f"\n  {err}", "info"))
                self.after(0, lambda: self._update_export_details(status="Export cancelled", elapsed=time.time() - export_started, eta=None))
                self.after(0, lambda: self._set_status("Export cancelled.", WARN))
                self.after(0, lambda: self._set_export_running(False))
            except PermissionError as e:
                err = str(e)
                self.after(0, lambda err=err: self._log(f"\n  Permission error: {err}", "err"))
                self.after(0, lambda: self._update_export_details(status="Permission error", elapsed=time.time() - export_started, eta=None))
                self.after(0, lambda: self._set_status("Permission denied - check folder write access.", ERR))
                self.after(0, lambda: self._set_export_running(False))
                self.after(0, lambda err=err: self._show_error_with_details(
                    "Export failed",
                    "MergeGuru could not write the output file because of a permission issue.",
                    technical_detail=err,
                    action="Close the output file if it is open, choose a folder you can write to, then run export again.",
                ))
            except FileNotFoundError as e:
                err = str(e)
                self.after(0, lambda err=err: self._log(f"\n  File error: {err}", "err"))
                self.after(0, lambda: self._update_export_details(status="File error", elapsed=time.time() - export_started, eta=None))
                self.after(0, lambda: self._set_status("File save failed - the output file was not created.", ERR))
                self.after(0, lambda: self._set_export_running(False))
                self.after(0, lambda err=err: self._show_error_with_details(
                    "Export failed",
                    "MergeGuru finished the save step, but the output file could not be found.",
                    technical_detail=err,
                    action="Check the output folder and try exporting again with a new file name.",
                ))
            except Exception as e:
                err = str(e)
                self.after(0, lambda err=err: self._log(f"\n  Save error: {err}", "err"))
                self.after(0, lambda: self._update_export_details(status="Export failed", elapsed=time.time() - export_started, eta=None))
                self.after(0, lambda: self._set_status("Save failed - check the log for details.", ERR))
                self.after(0, lambda: self._set_export_running(False))
                self.after(0, lambda err=err: self._show_error_with_details(
                    "Export failed",
                    "MergeGuru could not complete the export.",
                    technical_detail=err,
                    action="Try a new output file name. If the file is very large, use CSV or Parquet.",
                ))

        def guarded_run():
            try:
                run()
            except Exception as exc:
                self.after(0, lambda err=str(exc): self._export_failed_done(err))
        threading.Thread(target=guarded_run, daemon=True).start()

    def _export_failed_done(self, detail):
        self._set_export_running(False)
        self._update_export_details(status="Export failed", eta=None)
        self._set_status("Export stopped. Your combined data is still available for retry.", ERR)
        self._log(f"Export failed: {detail}", "err")
        self._show_error_with_details("Export failed", "MergeGuru could not finish preparing or saving the export.",
                                      technical_detail=detail,
                                      action="Check your filters and output location, then try again.")

    def _complete_export_history(self, item, signature):
        self._last_export_signature = signature
        self._export_history.append(item)
        self._redraw_export_history()
        self._refresh_save_state()
        if self._auto_open_output and not _open_path(item["path"]):
            self._set_status("Export saved. The file could not be opened automatically; use Open in export history.", WARN)


# =======================================================================
if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from mergeguru_diagnostics import run_self_test
        sys.exit(run_self_test(sys.argv[2], MergeGuruApp, pyi_splash))
    app = MergeGuruApp()
    if pyi_splash is not None:
        try:
            app.after(150, pyi_splash.close)
        except Exception:
            pass
    app.mainloop()

