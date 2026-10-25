"""Responsive filter editor for MergeGuru Lite v3."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import ttk

import pandas as pd

from mergeguru_engine import build_filter_mask
from prototypes.lite_redesign.category_picker import CategoryPicker
from prototypes.lite_redesign.selection import ValueSelection
from prototypes.lite_redesign.theme import BODY, BOLD, COLORS as C, SECTION, SMALL


CATEGORY_LIMIT = 20_000
VALUE_SCAN_CHUNK = 100_000


def unique_values_limited(series, limit=CATEGORY_LIMIT):
    """Collect unique display values without retaining an unbounded set."""
    seen = {}
    for start in range(0, len(series), VALUE_SCAN_CHUNK):
        chunk = series.iloc[start : start + VALUE_SCAN_CHUNK].fillna("").astype(str)
        for value in chunk.drop_duplicates().tolist():
            seen.setdefault(value, None)
            if len(seen) > limit:
                return tuple(seen), True
    return tuple(seen), False


def matching_count(frame, filters):
    mask = pd.Series(True, index=frame.index)
    string_cache = {}
    date_cache = {}
    for config in filters:
        column = config["column"]
        strings = None
        dates = None
        if config["mode"] in {"category", "text"}:
            strings = string_cache.setdefault(column, frame[column].fillna("").astype(str))
        elif config["mode"] == "date":
            dates = date_cache.setdefault(column, pd.to_datetime(frame[column], errors="coerce"))
        mask &= build_filter_mask(frame, config, strings, dates)
    return int(mask.sum())


class FilterDialog(tk.Toplevel):
    """Edit one filter while keeping high-cost scans away from Tk's UI thread."""

    OPERATIONS = {
        "Include selected values": ("category", "include"),
        "Exclude selected values": ("category", "exclude"),
        "Text starts with": ("text", "starts_with"),
        "Text contains": ("text", "contains"),
    }

    def __init__(self, owner, index=None):
        super().__init__(owner, bg=C["surface"], padx=18, pady=12)
        self.owner = owner
        self.index = index
        self.item = owner.state.filters[index] if index is not None else None
        self.result_queue = queue.Queue()
        self.generation = 0
        self.draft_generation = 0
        self.closed = False
        self.value_cache = owner.value_cache
        self.selections = {}
        self.searches = {}
        self.current_picker = None
        self.current_column = None
        self.pending_draft = None
        self.worker_threads = []

        self.title("Edit filter" if self.item else "Add filter")
        self.transient(owner)
        self.geometry("600x680")
        self.minsize(440, 520)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda event: self.close())
        self.bind("<Control-Return>", lambda event: self.apply())

        owner.label(self, "Choose values to include or exclude", SECTION).pack(anchor="w", pady=(4, 10))
        fields = tk.Frame(self, bg=C["surface"])
        fields.pack(fill="x", pady=(0, 8))
        fields.grid_columnconfigure(0, weight=1, uniform="filter-fields")
        fields.grid_columnconfigure(1, weight=1, uniform="filter-fields")
        owner.label(fields, "Column", SMALL, "muted").grid(row=0, column=0, sticky="w")
        owner.label(fields, "Action", SMALL, "muted").grid(row=0, column=1, sticky="w", padx=(8, 0))

        columns = owner.state.columns
        initial_column = self.item.get("column") if self.item else columns[0]
        if initial_column not in columns:
            initial_column = columns[0]
        self.column_var = tk.StringVar(self, value=initial_column)
        self.column_combo = ttk.Combobox(
            fields,
            textvariable=self.column_var,
            values=columns,
            state="readonly",
            style="Proto.TCombobox",
        )
        self.column_combo.grid(row=1, column=0, sticky="ew")
        self.column_combo.bind("<<ComboboxSelected>>", self.populate)

        initial_operation = "Include selected values"
        if self.item:
            for label, (mode, operation) in self.OPERATIONS.items():
                actual = self.item.get("action") if mode == "category" else self.item.get("operator")
                if self.item.get("mode") == mode and actual == operation:
                    initial_operation = label
                    break
        self.operation_var = tk.StringVar(self, value=initial_operation)
        self.operation_combo = ttk.Combobox(
            fields,
            textvariable=self.operation_var,
            values=tuple(self.OPERATIONS),
            state="readonly",
            style="Proto.TCombobox",
        )
        self.operation_combo.grid(row=1, column=1, sticky="ew", padx=(8, 0))
        self.operation_combo.bind("<<ComboboxSelected>>", self.populate)

        self.area = tk.Frame(self, bg=C["surface"])
        self.area.pack(fill="both", expand=True)
        self.result_label = owner.label(self, "", SMALL, "blue")
        self.result_label.pack(side="bottom", fill="x", pady=(5, 0))
        self.error_label = owner.label(self, "", SMALL, "amber")
        self.error_label.pack(side="bottom", fill="x")
        footer = tk.Frame(self, bg=C["surface"])
        footer.pack(side="bottom", fill="x", pady=(10, 0))
        owner.button(footer, "Cancel", self.close).pack(side="right")
        self.apply_button = owner.button(footer, "Apply filter", self.apply, primary=True)
        self.apply_button.pack(side="right", padx=(0, 8))

        initial_term = self.item.get("value", "") if self.item and self.item.get("mode") == "text" else ""
        self.term_var = tk.StringVar(self, value=initial_term)
        self.term_var.trace_add("write", self.schedule_draft)
        self.after(50, self.populate)
        self.after(80, self.poll_results)

    def populate(self, event=None):
        if self.closed:
            return
        if self.current_picker is not None and self.current_column:
            self.searches[self.current_column] = (
                self.current_picker.search_var.get(),
                self.current_picker.match_var.get(),
            )
        for child in self.area.winfo_children():
            child.destroy()
        self.current_picker = None
        self.current_column = self.column_var.get()
        self.error_label.configure(text="")
        mode, _ = self.OPERATIONS[self.operation_var.get()]
        if mode == "text":
            self.owner.label(self.area, "Text to find (case-insensitive)", SMALL, "muted").pack(
                anchor="w", pady=(8, 4)
            )
            entry = tk.Entry(
                self.area,
                textvariable=self.term_var,
                font=BODY,
                bg=C["surface"],
                fg=C["ink"],
                relief="solid",
                bd=1,
            )
            entry.pack(fill="x", ipady=7)
            self.owner.paragraph(
                self.area,
                "Use Starts with for prefixes such as Wa, or Contains when the text may appear anywhere.",
            )
            entry.focus_set()
            self.schedule_draft()
            return
        self._load_values(self.current_column)

    def _load_values(self, column):
        if column in self.value_cache:
            self._show_values(column, self.value_cache[column])
            return
        self.generation += 1
        generation = self.generation
        self.owner.label(self.area, f"Loading unique values from {column}...", BOLD, "blue").pack(
            anchor="w", pady=12
        )
        progress = ttk.Progressbar(self.area, mode="indeterminate", style="Proto.Horizontal.TProgressbar")
        progress.pack(fill="x")
        progress.start(12)
        frame = self.owner.state.final_df
        result_queue = self.result_queue

        def worker():
            try:
                values, truncated = unique_values_limited(frame[column])
                result_queue.put(("values", generation, column, (values, truncated), None))
            except Exception as exc:
                result_queue.put(("values", generation, column, ((), False), exc))

        thread = threading.Thread(target=worker, name="MergeGuru-filter-values", daemon=True)
        self.worker_threads.append(thread)
        thread.start()

    def _show_values(self, column, cached):
        if self.closed or column != self.column_var.get():
            return
        values, truncated = cached
        for child in self.area.winfo_children():
            child.destroy()
        if truncated:
            self.owner.paragraph(
                self.area,
                f"This column has more than {CATEGORY_LIMIT:,} unique values. Category checkboxes are limited to "
                f"{CATEGORY_LIMIT:,} to protect responsiveness. Choose Text starts with or Text contains above.",
                "amber",
            )
            self.apply_button.configure(state="disabled")
            self.result_label.configure(text="Use a text action for this high-cardinality column.")
            return
        if column not in self.selections:
            selected = ()
            if self.item and self.item.get("mode") == "category" and self.item.get("column") == column:
                selected = self.item.get("values", ())
            self.selections[column] = ValueSelection(values, selected)
        action = "excluded" if self.OPERATIONS[self.operation_var.get()][1] == "exclude" else "included"
        help_label = self.owner.label(
            self.area,
            f"Checked values will be {action}. Search Wa to show values starting with Wa; bulk actions affect all matches.",
            SMALL,
            "muted",
            wraplength=520,
        )
        help_label.pack(fill="x", pady=(0, 4))
        self.current_picker = CategoryPicker(
            self.area,
            self.selections[column],
            self.owner.button,
            on_change=self.schedule_draft,
        )
        self.current_picker.pack(fill="both", expand=True)
        saved_search = self.searches.get(column)
        if saved_search:
            self.current_picker.search_var.set(saved_search[0])
            self.current_picker.match_var.set(saved_search[1])
            self.current_picker.refresh()
        self.apply_button.configure(state="normal")
        self.schedule_draft()

    def candidate(self):
        column = self.column_var.get()
        mode, operation = self.OPERATIONS[self.operation_var.get()]
        if mode == "category":
            selection = self.selections.get(column)
            values = list(selection.result()) if selection else []
            if not values:
                raise ValueError("Select at least one value.")
            return {"column": column, "mode": "category", "action": operation, "values": values}
        value = self.term_var.get().strip()
        if not value:
            raise ValueError("Enter text to find.")
        return {"column": column, "mode": "text", "operator": operation, "value": value}

    def schedule_draft(self, *args):
        if self.closed:
            return
        if self.pending_draft:
            self.after_cancel(self.pending_draft)
        self.pending_draft = self.after(260, self.start_draft)

    def start_draft(self):
        self.pending_draft = None
        try:
            candidate = self.candidate()
        except ValueError as exc:
            self.result_label.configure(text=str(exc))
            return
        filters = [dict(config) for config in self.owner.state.filters]
        if self.index is None:
            filters.append(candidate)
        else:
            filters[self.index] = candidate
        self.draft_generation += 1
        generation = self.draft_generation
        self.result_label.configure(text="Calculating matching rows...")
        frame = self.owner.state.final_df
        result_queue = self.result_queue

        def worker():
            try:
                count = matching_count(frame, filters)
                result_queue.put(("draft", generation, count, None, None))
            except Exception as exc:
                result_queue.put(("draft", generation, 0, exc, None))

        thread = threading.Thread(target=worker, name="MergeGuru-filter-preview", daemon=True)
        self.worker_threads.append(thread)
        thread.start()

    def poll_results(self):
        if self.closed:
            return
        while True:
            try:
                kind, generation, value, extra, error = self.result_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "values" and generation == self.generation:
                column, values, error = value, extra, error
                if error:
                    self.error_label.configure(text=f"Could not load values: {error}")
                else:
                    self.value_cache[column] = values
                    self._show_values(column, values)
            elif kind == "draft" and generation == self.draft_generation:
                count, error = value, extra
                if error:
                    self.result_label.configure(text=f"Preview unavailable: {error}")
                else:
                    total = len(self.owner.state.final_df)
                    self.result_label.configure(text=f"With this filter: {count:,} of {total:,} rows match.")
        self.after(80, self.poll_results)

    def apply(self):
        try:
            config = self.candidate()
        except ValueError as exc:
            self.error_label.configure(text=str(exc))
            return
        self.owner.commit_filter(self.index, config)
        self.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.pending_draft:
            self.after_cancel(self.pending_draft)
            self.pending_draft = None
        for thread in self.worker_threads:
            if thread.is_alive() and thread is not threading.current_thread():
                thread.join(timeout=0.25)
        self.worker_threads.clear()
        self.grab_release()
        self.destroy()
        self.owner.filter_dialog_window = None
