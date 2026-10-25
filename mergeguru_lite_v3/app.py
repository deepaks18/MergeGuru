"""Functional, responsive MergeGuru Lite workbench."""

from __future__ import annotations

import math
import os
import queue
import subprocess
import sys
import threading
import time
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pandas as pd

from mergeguru_engine import (
    CancelledOperation,
    EXPORT_FORMATS,
    apply_filters as apply_engine_filters,
    check_memory_before_combine,
    classify_file_error,
    combine_sources,
    discover_sources,
    ensure_export_extension,
    filter_summary,
    get_dataframe_memory_mb,
    get_sheet_names,
    possible_duplicate_sources,
    save_dataframe,
    source_cache_key,
    source_size,
    validate_sources,
)
from prototypes.lite_redesign.brand import BrandHeader, make_icon
from prototypes.lite_redesign.category_picker import CategoryPicker
from prototypes.lite_redesign.selection import ValueSelection
from prototypes.lite_redesign.theme import BODY, BOLD, COLORS as C, SECTION, SMALL, TITLE
from prototypes.lite_redesign.workspace import ResponsiveWorkspace

from .diagnostics import DiagnosticRecorder
from .filter_dialog import FilterDialog
from .preferences import load_preferences, save_preferences
from .projects import (
    PROJECT_EXTENSION,
    build_project_payload,
    load_project as read_project,
    resolve_project_inputs,
    save_project as write_project,
    source_matches_descriptor,
)
from .reports import format_size, validation_report_frame, write_audit_report
from .state import LITE_VERSION, LiteV3State, default_output_path, next_available_path, source_identity


SUPPORTED_SUFFIXES = {".xlsx", ".csv", ".zip"}
PREVIEW_COLUMN_LIMIT = 50


def _enable_windows_dpi_awareness():
    """Prevent Windows from bitmap-scaling the interface and brand artwork."""
    if os.name != "nt":
        return
    try:
        import ctypes

        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError, ValueError):
        pass


class MergeGuruLiteV3(tk.Tk):
    STEPS = ("Sources", "Check & Prepare", "Filters", "Export")

    def __init__(self, *, preference_file=None, diagnostic_file=None):
        _enable_windows_dpi_awareness()
        super().__init__()
        self.preference_file = preference_file
        self.preferences = load_preferences(preference_file)
        self.state = LiteV3State(
            allow_extra=self.preferences["allow_extra"],
            different_sheets=self.preferences["different_sheets"],
            optimize_memory=self.preferences["optimize_memory"],
            fast_mode=self.preferences["fast_mode"],
            output_format=self.preferences["output_format"],
        )
        self.preview_limit = self.preferences["preview_limit"]
        self.step = 0
        self.busy = False
        self.stopping = False
        self.task_kind = ""
        self.task_title = ""
        self.task_started = 0.0
        self.task_percent = 0
        self.task_detail = ""
        self.task_queue = queue.Queue()
        self.task_thread = None
        self.task_poll = None
        self.cancel_event = threading.Event()
        self.task_done_callback = None
        self.task_error_callback = None
        self.notice_text = "Choose a folder or select files to begin. Source data stays on this computer."
        self.notice_kind = "info"
        self.technical_detail = ""
        self.wrap_labels = []
        self.filter_dialog_window = None
        self.filter_undo = None
        self.value_cache = {}
        self.performance_open = False
        self.validation_open = True
        self.preview_table = None
        self.preview_columns = []
        self.mousewheel_bound = False
        self.last_error_type = ""
        self.diagnostics = DiagnosticRecorder(LITE_VERSION, diagnostic_file)

        self.title(f"MergeGuru Lite | {LITE_VERSION}")
        self.geometry(self.preferences["window_geometry"])
        self.minsize(720, 560)
        self.configure(bg=C["paper"])
        self.brand_icon = make_icon(self)
        self.iconphoto(True, self.brand_icon)
        self._style()
        self._shell()
        self.render()
        self.protocol("WM_DELETE_WINDOW", self.request_close)
        self.bind("<Alt-n>", lambda event: self.primary())
        self.bind("<Alt-b>", lambda event: self.go(self.step - 1))
        self.bind("<Control-o>", lambda event: self.browse_files())
        self.bind("<Control-Shift-O>", lambda event: self.open_project())
        self.bind("<Control-s>", lambda event: self.save_project())
        self.bind("<Control-f>", self.keyboard_filter)
        self.bind("<Escape>", lambda event: self.cancel_task() if self.busy else None)
        self.after_idle(self._close_splash)

    def _close_splash(self):
        try:
            import pyi_splash

            pyi_splash.close()
        except (ImportError, RuntimeError):
            pass

    def _style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Proto.TCombobox", padding=7, fieldbackground=C["surface"], foreground=C["ink"])
        style.map(
            "Proto.TCombobox",
            fieldbackground=[("disabled", C["wash"]), ("readonly", C["surface"])],
            foreground=[("disabled", C["disabled"])],
        )
        style.configure(
            "Proto.Treeview",
            background=C["surface"],
            fieldbackground=C["surface"],
            foreground=C["ink"],
            rowheight=28,
            font=BODY,
            borderwidth=0,
        )
        style.configure(
            "Proto.Treeview.Heading",
            background=C["wash"],
            foreground=C["ink"],
            font=BOLD,
            padding=7,
            relief="flat",
        )
        style.map(
            "Proto.Treeview",
            background=[("selected", C["blue"])],
            foreground=[("selected", C["surface"])],
        )
        style.configure(
            "Proto.Horizontal.TProgressbar",
            background=C["cyan"],
            troughcolor=C["line"],
            borderwidth=0,
            thickness=8,
        )
        style.configure(
            "TScrollbar",
            background=C["line"],
            troughcolor=C["paper"],
            arrowcolor=C["muted"],
            bordercolor=C["line"],
        )

    def label(self, parent, text, font=BODY, color="ink", background=None, **kwargs):
        kwargs.setdefault("anchor", "w")
        kwargs.setdefault("justify", "left")
        return tk.Label(
            parent,
            text=text,
            font=font,
            fg=C[color],
            bg=background or parent.cget("bg"),
            **kwargs,
        )

    def paragraph(self, parent, text, color="muted"):
        widget = self.label(parent, text, color=color, wraplength=300)
        widget.pack(fill="x", pady=(3, 3))
        widget.bind("<Configure>", lambda event: widget.configure(wraplength=max(120, event.width)))
        self.wrap_labels.append(widget)
        return widget

    def button(self, parent, text, command, primary=False):
        widget = tk.Button(
            parent,
            text=text,
            command=command,
            font=BOLD,
            cursor="hand2",
            bg=C["blue"] if primary else C["surface"],
            fg=C["surface"] if primary else C["ink"],
            activebackground=C["blue_hover"] if primary else C["wash"],
            activeforeground=C["surface"] if primary else C["ink"],
            disabledforeground=C["disabled_on_blue"] if primary else C["disabled"],
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=C["line"],
            highlightcolor=C["blue"],
            padx=10,
            pady=6,
            takefocus=True,
        )
        widget.bind("<Return>", lambda event: widget.invoke())
        return widget

    def card(self, title, parent=None):
        frame = tk.Frame(
            parent or self.content,
            bg=C["surface"],
            padx=12,
            pady=10,
            highlightthickness=1,
            highlightbackground=C["line"],
        )
        frame.pack(fill="x", pady=(0, 10))
        if title:
            self.label(frame, title, SECTION).pack(anchor="w", pady=(0, 6))
        return frame

    def check(self, parent, text, value, command):
        variable = tk.BooleanVar(parent, value=value)
        widget = tk.Checkbutton(
            parent,
            text=text,
            variable=variable,
            command=lambda: command(variable.get()),
            bg=parent.cget("bg"),
            fg=C["ink"],
            selectcolor=C["surface"],
            activebackground=C["wash"],
            activeforeground=C["ink"],
            font=BODY,
            anchor="w",
            justify="left",
            wraplength=560,
            padx=0,
            pady=5,
            takefocus=True,
        )
        widget.pack(fill="x", anchor="w")
        widget.bind("<Configure>", lambda event: widget.configure(wraplength=max(120, event.width - 30)))
        self.wrap_labels.append(widget)
        return widget

    def disclosure(self, parent, title, flag):
        row = tk.Frame(parent, bg=parent.cget("bg"))
        row.pack(fill="x", pady=(4, 2))
        self.label(row, title, BOLD).pack(side="left")

        def toggle():
            setattr(self, flag, not getattr(self, flag))
            self.render()

        self.button(row, "Hide" if getattr(self, flag) else "Show", toggle).pack(side="right")
        body = tk.Frame(parent, bg=parent.cget("bg"))
        if getattr(self, flag):
            body.pack(fill="x", pady=(5, 0))
        return body

    def table(self, parent, columns, *, height=5, widths=None, selectmode="browse"):
        shell = tk.Frame(parent, bg=C["surface"])
        shell.pack(fill="both", expand=True, pady=(6, 0))
        ids = tuple(f"c{index}" for index in range(len(columns)))
        tree = ttk.Treeview(
            shell,
            columns=ids,
            show="headings",
            style="Proto.Treeview",
            height=height,
            selectmode=selectmode,
        )
        for index, (column_id, title) in enumerate(zip(ids, columns)):
            width = widths[index] if widths and index < len(widths) else 140
            tree.heading(column_id, text=title)
            tree.column(column_id, width=width, minwidth=45, stretch=index != 0 or len(ids) == 1)
        vertical = ttk.Scrollbar(shell, orient="vertical", command=tree.yview)
        horizontal = ttk.Scrollbar(shell, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        shell.grid_rowconfigure(0, weight=1)
        shell.grid_columnconfigure(0, weight=1)
        tree.tag_configure("stripe", background=C["stripe"])
        tree.tag_configure("template", foreground=C["amber"])
        tree.bind("<MouseWheel>", lambda event: None)
        return tree

    def _shell(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.brand_header = BrandHeader(self)
        self.brand_header.preview_badge.configure(text=f"LITE {LITE_VERSION} / DEVELOPMENT")
        self.brand_header.grid(row=0, column=0, sticky="ew")

        nav = tk.Frame(self, bg=C["surface"], padx=12, pady=6)
        nav.grid(row=1, column=0, sticky="ew")
        self.steps, self.step_states, self.step_marks = [], [], []
        for index, name in enumerate(self.STEPS):
            nav.grid_columnconfigure(index, weight=1, uniform="steps")
            button = self.button(nav, f"{index + 1}  {name}", lambda target=index: self.go(target))
            button.configure(font=SMALL, pady=4, padx=6)
            button.grid(row=0, column=index, sticky="ew", padx=4)
            self.steps.append(button)
            caption = self.label(nav, "", ("Segoe UI", 8), "muted", anchor="center")
            caption.grid(row=1, column=index, sticky="ew", pady=(1, 4))
            self.step_states.append(caption)
            mark = tk.Frame(nav, bg=C["line"], height=2)
            mark.grid(row=2, column=index, sticky="ew", padx=4)
            self.step_marks.append(mark)

        shell = tk.Frame(self, bg=C["paper"])
        shell.grid(row=2, column=0, sticky="nsew")
        self.canvas = tk.Canvas(shell, bg=C["paper"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(shell, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.content = tk.Frame(self.canvas, bg=C["paper"], padx=16, pady=12)
        self.content_window = self.canvas.create_window(0, 0, window=self.content, anchor="nw")
        self.content.bind("<Configure>", lambda event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._resize)
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)

        self.dock = tk.Frame(self, bg=C["surface"], padx=20, pady=5)
        self.dock.grid(row=3, column=0, sticky="ew")
        self.dock.grid_columnconfigure(0, weight=1)
        self.progress_title = self.label(self.dock, "Ready", BOLD)
        self.progress_title.grid(row=0, column=0, sticky="w")
        self.cancel_button = self.button(self.dock, "Cancel", self.cancel_task)
        self.cancel_button.grid(row=0, column=1, rowspan=2, padx=(10, 0))
        self.progress_caption = self.label(self.dock, "", SMALL)
        self.progress_caption.grid(row=1, column=0, sticky="ew", pady=(3, 4))
        self.progress = ttk.Progressbar(
            self.dock, style="Proto.Horizontal.TProgressbar", maximum=100, mode="determinate"
        )
        self.progress.grid(row=2, column=0, columnspan=2, sticky="ew")

        footer = tk.Frame(self, bg=C["surface"], padx=16, pady=9)
        footer.grid(row=4, column=0, sticky="ew")
        self.back_button = self.button(footer, "Back", lambda: self.go(self.step - 1))
        self.back_button.pack(side="left")
        self.primary_button = self.button(footer, "Review layout", self.primary, primary=True)
        self.primary_button.pack(side="right")
        self.close_button = self.button(footer, "Close without export", self.request_close)
        self.close_button.pack(side="right", padx=8)
        self.next_hint = self.label(footer, "", SMALL, "muted", wraplength=260)
        self.next_hint.pack(side="left", fill="x", expand=True, padx=12)
        self.next_hint.bind(
            "<Configure>", lambda event: self.next_hint.configure(wraplength=max(100, event.width))
        )

    def _resize(self, event):
        self.canvas.itemconfigure(self.content_window, width=event.width)

    def _bind_mousewheel(self, event=None):
        if self.mousewheel_bound:
            return
        self.bind_all("<MouseWheel>", self._wheel)
        self.bind_all("<Button-4>", self._wheel)
        self.bind_all("<Button-5>", self._wheel)
        self.mousewheel_bound = True

    def _unbind_mousewheel(self, event=None):
        if not self.mousewheel_bound:
            return
        self.unbind_all("<MouseWheel>")
        self.unbind_all("<Button-4>")
        self.unbind_all("<Button-5>")
        self.mousewheel_bound = False

    def _wheel(self, event):
        if event.widget.winfo_toplevel() != self or isinstance(event.widget, (ttk.Treeview, ttk.Combobox)):
            return
        units = -1 if getattr(event, "num", 0) == 4 else 1 if getattr(event, "num", 0) == 5 else 0
        if not units and getattr(event, "delta", 0):
            units = -max(1, abs(int(event.delta / 120))) if event.delta > 0 else max(1, abs(int(event.delta / 120)))
        self.canvas.yview_scroll(units, "units")

    def announce(self, text, kind="info", technical=""):
        self.notice_text = text
        self.notice_kind = kind
        self.technical_detail = technical

    def can_go(self, target):
        if self.busy or not 0 <= target < len(self.STEPS):
            return False
        if target == 0:
            return True
        if target == 1:
            return bool(self.state.sources)
        return self.state.prepared

    def go(self, target):
        if self.can_go(target):
            self.step = target
            self.render()

    def keyboard_filter(self, event=None):
        if self.step == 2 and self.state.prepared and not self.busy:
            self.open_filter_dialog()
        return "break"

    def render(self):
        for child in self.content.winfo_children():
            child.destroy()
        self.wrap_labels = []
        self.canvas.yview_moveto(0)
        headings = (
            ("Choose your data", "Select a folder or individual files, then choose the reference template."),
            ("Check and prepare", "Confirm worksheet and layout rules, then validate and combine once."),
            ("Filter your results", "Search values, include or exclude groups, and preview the cached result."),
            ("Review and export", "Choose a format and destination, then export without rereading sources."),
        )
        title, subtitle = headings[self.step]
        self.label(self.content, title, TITLE).pack(anchor="w", pady=(4, 0))
        self.paragraph(self.content, subtitle)
        if self.notice_text:
            bg = C["amber_wash"] if self.notice_kind == "warning" else C["green_wash"] if self.notice_kind == "success" else C["wash"]
            color = "amber" if self.notice_kind == "warning" else "green" if self.notice_kind == "success" else "ink"
            notice = tk.Frame(self.content, bg=bg, padx=10, pady=5)
            notice.pack(fill="x", pady=(5, 8))
            self.paragraph(notice, self.notice_text, color)
            if self.technical_detail:
                self.button(notice, "Show technical detail", self.show_technical_detail).pack(anchor="e", pady=(3, 0))
        (self.sources_page, self.prepare_page, self.filters_page, self.export_page)[self.step]()
        self._navigation()
        if self.busy:
            self._disable_content(self.content)
        self.after_idle(lambda: self.canvas.yview_moveto(0))

    def _disable_content(self, widget):
        for child in widget.winfo_children():
            if isinstance(child, (tk.Button, tk.Checkbutton, tk.Entry, tk.Spinbox, ttk.Combobox)):
                try:
                    child.configure(state="disabled")
                except tk.TclError:
                    pass
            self._disable_content(child)

    def _navigation(self):
        state = self.state
        completed = (bool(state.sources), state.prepared, state.prepared, state.saved)
        captions = (
            f"{len(state.sources)} files selected" if state.sources else "Choose files",
            "Ready" if state.prepared else "Prepare first",
            f"{len(state.filters)} filters" if state.prepared else "Prepare data first",
            "Current result saved" if state.saved else "Not exported" if state.prepared else "Prepare data first",
        )
        for index, button in enumerate(self.steps):
            prefix = "OK" if completed[index] else str(index + 1)
            button.configure(
                text=f"{prefix}  {self.STEPS[index]}",
                bg=C["wash"] if index == self.step else C["surface"],
                fg=C["blue"] if index == self.step or completed[index] else C["muted"],
                state="normal" if self.can_go(index) else "disabled",
            )
            self.step_marks[index].configure(bg=C["blue"] if index == self.step else C["line"])
            self.step_states[index].configure(text=captions[index])

        names = (
            "Review layout",
            "Continue to filters" if state.prepared else "Check and prepare data",
            "Review export",
            "Finish (Close)" if state.saved else "Export file",
        )
        allowed = not self.busy
        hint = ""
        if self.step == 0:
            allowed = allowed and bool(state.sources)
            hint = "Choose one or more supported files to continue." if not state.sources else "Template and source selection are ready."
        elif self.step == 1:
            allowed = allowed and bool(state.sources) and bool(state.template_source)
            hint = "Prepared data is cached; continue without rereading files." if state.prepared else "Validation and combine run in the background."
        elif self.step == 2:
            problem = state.filter_problem()
            allowed = allowed and state.filtered_df is not None and not state.filtered_df.empty and not problem
            hint = problem or ("No rows match. Adjust the filters." if state.filtered_df is not None and state.filtered_df.empty else "Preview uses cached combined data; sources are not reread.")
        else:
            if state.saved:
                hint = "Export complete. Finish, open the file, or create another export."
            else:
                try:
                    state.validate_export()
                    hint = "Export writes to a temporary file first, then commits the completed output."
                except ValueError as exc:
                    allowed = False
                    hint = str(exc)
        if self.busy:
            hint = "Processing is active. Settings and navigation are locked; Cancel remains available."
        self.primary_button.configure(text=names[self.step], state="normal" if allowed else "disabled")
        self.back_button.configure(state="normal" if self.step and not self.busy else "disabled")
        self.close_button.pack_forget()
        if self.step == 3:
            self.close_button.configure(state="disabled" if self.busy else "normal")
            self.close_button.pack(side="right", padx=8)
        self.next_hint.configure(text=hint)
        if self.busy:
            self.dock.configure(bg=C["cyan_wash"], pady=8)
            self.progress_title.configure(bg=C["cyan_wash"], text=self.task_title)
            self.progress_caption.configure(bg=C["cyan_wash"])
            self.progress_caption.grid()
            self.progress.grid()
            self.cancel_button.grid()
            self.cancel_button.configure(state="disabled" if self.stopping else "normal")
        else:
            self.dock.configure(bg=C["surface"], pady=5)
            self.progress_title.configure(bg=C["surface"], text="Ready")
            self.progress_caption.grid_remove()
            self.progress.grid_remove()
            self.cancel_button.grid_remove()

    def primary(self):
        if self.busy:
            return
        if self.step == 0:
            self.go(1)
        elif self.step == 1:
            self.go(2) if self.state.prepared else self.start_prepare()
        elif self.step == 2:
            self.go(3)
        elif self.state.saved:
            self.request_close()
        else:
            self.start_export()

    def sources_page(self):
        project = self.card("Reusable project")
        project_actions = tk.Frame(project, bg=C["surface"])
        project_actions.pack(fill="x")
        self.button(project_actions, "Open project...", self.open_project).pack(side="left")
        save_button = self.button(project_actions, "Save project...", self.save_project)
        save_button.pack(side="left", padx=6)
        save_button.configure(state="normal" if self.state.sources else "disabled")
        self.button(project_actions, "Save diagnostics...", self.save_diagnostics).pack(side="right")
        if self.state.project_path:
            self.paragraph(project, f"Current project: {os.path.basename(self.state.project_path)}", "green")
        else:
            self.paragraph(
                project,
                "Projects store source locations, workflow settings, and filter criteria, but never source rows. "
                "Opening a project always checks the source files again.",
            )

        card = self.card(f"Source files / {len(self.state.sources)} selected")
        actions = tk.Frame(card, bg=C["surface"])
        actions.pack(fill="x")
        self.button(actions, "Browse folder", self.browse_folder, primary=True).pack(side="left")
        self.label(actions, "or", SMALL, "muted").pack(side="left", padx=12)
        self.button(actions, "Select files", self.browse_files).pack(side="left")
        self.paragraph(card, "Supported: Excel (.xlsx), CSV, and ZIP archives containing Excel/CSV. Ctrl+O opens file selection.")
        if not self.state.sources:
            empty = tk.Frame(card, bg=C["wash"], padx=14, pady=16)
            empty.pack(fill="x", pady=(8, 0))
            self.paragraph(empty, "No source files selected. Choose a folder for a complete dump, or select files from different locations.")
            return

        table = self.table(card, ("", "File", "Type", "Size"), height=min(8, max(3, len(self.state.sources))), widths=(34, 360, 70, 90), selectmode="extended")
        self.source_table = table
        template_index = self.state.template_index
        for index, source in enumerate(self.state.sources):
            template = index == template_index
            values = (
                "\u2605" if template else "",
                source["display_name"],
                ("ZIP / " if source["mode"] == "zip" else "") + source["type"].upper(),
                format_size(source.get("_size", source_size(source))),
            )
            tags = ("template",) if template else (("stripe",) if index % 2 else ())
            table.insert("", "end", iid=str(index), values=values, tags=tags)
        if template_index is not None:
            table.selection_set(str(template_index))
        table.bind("<<TreeviewSelect>>", self.source_selection_changed)
        table.bind("<Return>", lambda event: self.set_template())
        row = tk.Frame(card, bg=C["surface"])
        row.pack(fill="x", pady=(8, 0))
        self.template_button = self.button(row, "\u2605  Use as template", self.set_template)
        self.template_button.pack(side="left")
        self.exclude_button = self.button(row, "Exclude selected", self.exclude_sources)
        self.exclude_button.pack(side="left", padx=8)
        if self.state.excluded_sources:
            self.button(row, f"Restore {len(self.state.excluded_sources)} excluded", self.restore_sources).pack(side="left")
        self.source_summary = self.paragraph(card, "Select one or more rows. The yellow star marks the reference template.")
        self.source_selection_changed()
        if self.state.duplicate_groups:
            self.paragraph(
                card,
                f"Possible duplicate sources detected in {len(self.state.duplicate_groups)} group(s). Review names and sizes before preparing.",
                "amber",
            )
        if self.state.source_errors:
            self.paragraph(card, f"{len(self.state.source_errors)} source(s) could not be inspected. See the notice detail.", "amber")

    def source_selection_changed(self, event=None):
        if not hasattr(self, "source_table") or not self.source_table.winfo_exists():
            return
        selected = self.selected_source_indices()
        state = "normal" if selected and not self.busy else "disabled"
        can_set_template = len(selected) == 1 and not self.busy
        self.template_button.configure(
            state="normal" if can_set_template else "disabled",
            bg=C["star"] if can_set_template else C["wash"],
            fg=C["ink"] if can_set_template else C["disabled"],
            activebackground="#ffdc66",
            activeforeground=C["ink"],
            highlightbackground=C["star"] if can_set_template else C["line"],
        )
        self.exclude_button.configure(state=state)
        if not selected:
            self.source_summary.configure(text="No row selected. Choose a row to set the template or exclude files.")
            return
        total = sum(self.state.sources[index].get("_size", 0) for index in selected)
        names = ", ".join(self.state.sources[index]["display_name"] for index in selected[:2])
        more = f" +{len(selected) - 2} more" if len(selected) > 2 else ""
        self.source_summary.configure(text=f"Selected: {names}{more} | {format_size(total)}")

    def selected_source_indices(self):
        return sorted(int(item) for item in self.source_table.selection())

    def browse_folder(self):
        if self.busy:
            return
        folder = filedialog.askdirectory(title="Choose source folder", parent=self)
        if not folder:
            return
        try:
            paths = [
                entry.path
                for entry in os.scandir(folder)
                if entry.is_file()
                and not entry.name.startswith("~$")
                and os.path.splitext(entry.name)[1].lower() in SUPPORTED_SUFFIXES
            ]
        except OSError as exc:
            self.announce("The folder could not be read. Check access permissions and try again.", "warning", str(exc))
            self.render()
            return
        self.discover_paths(
            sorted(paths),
            project_inputs=[{"kind": "folder", "path": os.path.abspath(folder)}],
        )

    def browse_files(self):
        if self.busy:
            return
        paths = filedialog.askopenfilenames(
            title="Select source files",
            parent=self,
            filetypes=[
                ("Supported files", "*.xlsx *.csv *.zip"),
                ("Excel files", "*.xlsx"),
                ("CSV files", "*.csv"),
                ("ZIP archives", "*.zip"),
                ("All files", "*.*"),
            ],
        )
        if paths:
            self.discover_paths(
                paths,
                project_inputs=[{"kind": "file", "path": os.path.abspath(path)} for path in paths],
            )

    def open_project(self):
        if self.busy:
            return
        if self.state.prepared and not self.state.saved and not messagebox.askyesno(
            "Open another project?",
            "The current prepared result has not been exported. Open another project anyway?",
            parent=self,
        ):
            return
        path = filedialog.askopenfilename(
            title="Open MergeGuru project",
            parent=self,
            filetypes=[("MergeGuru projects", f"*{PROJECT_EXTENSION}"), ("JSON files", "*.json")],
        )
        if not path:
            return
        try:
            payload = read_project(path)
            paths, warnings = resolve_project_inputs(payload)
            if not paths:
                raise ValueError("None of the source locations saved in this project are currently available.")
        except ValueError as exc:
            self.announce(str(exc), "warning")
            self.diagnostics.record("project_open_failed", error_type=exc.__class__.__name__)
            self.render()
            return
        self.discover_paths(
            paths,
            project_inputs=payload["source_inputs"],
            project_payload=payload,
            project_path=os.path.abspath(path),
            project_warnings=warnings,
        )

    def save_project(self):
        if self.busy or not self.state.sources:
            return
        current = self.state.project_path
        initial_directory = os.path.dirname(current) if current else os.path.dirname(
            self.state.template_source.get("full_path")
            or self.state.template_source.get("zip_path")
            or os.getcwd()
        )
        path = filedialog.asksaveasfilename(
            title="Save MergeGuru project",
            parent=self,
            initialdir=initial_directory,
            initialfile=os.path.basename(current) if current else f"MergeGuru_Project{PROJECT_EXTENSION}",
            defaultextension=PROJECT_EXTENSION,
            filetypes=[("MergeGuru projects", f"*{PROJECT_EXTENSION}"), ("JSON files", "*.json")],
        )
        if not path:
            return
        try:
            payload = build_project_payload(self.state, LITE_VERSION)
            saved_path = write_project(path, payload)
        except (OSError, ValueError) as exc:
            self.announce("The project could not be saved. Choose another location and retry.", "warning", str(exc))
            self.diagnostics.record("project_save_failed", error_type=exc.__class__.__name__)
            self.render()
            return
        self.state.project_path = saved_path
        self.diagnostics.record(
            "project_saved",
            source_count=len(self.state.sources),
            filter_count=len(self.state.filters or self.state.pending_filters),
        )
        self.announce(
            "Project saved. It contains source locations and workflow criteria, but no source rows.",
            "success",
        )
        self.render()

    def _restore_project(self, payload, sheets, project_path):
        state = self.state
        messages = []
        settings = payload["settings"]
        for key in (
            "allow_extra",
            "different_sheets",
            "fix_layout",
            "header_row",
            "footer_rows",
            "optimize_memory",
            "fast_mode",
        ):
            setattr(state, key, settings[key])

        template = next(
            (
                source
                for source in state.sources
                if source_matches_descriptor(source, payload.get("template"))
            ),
            None,
        )
        if template is None and state.sources:
            template = state.sources[0]
            messages.append("The saved reference source was unavailable; the first available source is the template.")

        excluded = []
        included = []
        for source in state.sources:
            should_exclude = any(
                source_matches_descriptor(source, descriptor)
                for descriptor in payload.get("excluded_sources", [])
            )
            if should_exclude and source is not template:
                excluded.append(source)
            else:
                included.append(source)
        state.sources = included
        state.excluded_sources = excluded
        state.template_key = source_identity(template) if template in state.sources else (
            source_identity(state.sources[0]) if state.sources else None
        )
        state.sheet_names = list(sheets)
        saved_sheet = settings["selected_sheet"]
        if state.template_source and state.template_source["type"] == "xlsx":
            if saved_sheet and saved_sheet in sheets:
                state.selected_sheet = saved_sheet
            else:
                state.selected_sheet = sheets[0] if sheets else ""
                if saved_sheet:
                    messages.append("The saved reference worksheet was unavailable; the first worksheet was selected.")
        else:
            state.selected_sheet = ""

        state.filters = []
        state.pending_filters = [dict(config) for config in payload["filters"]]
        state.output_format = payload["export"]["format"]
        state.protected_columns = set(payload["export"]["protected_columns"])
        state.output_path = default_output_path(state.template_source, state.output_format)
        output_directory = payload["export"]["output_directory"]
        if output_directory:
            if os.path.isdir(output_directory):
                state.output_path = next_available_path(
                    os.path.join(output_directory, os.path.basename(state.output_path))
                )
            else:
                messages.append("The saved output folder was unavailable; the template folder will be used.")
        state.project_path = project_path
        state.saved_signature = None
        return messages

    def discover_paths(
        self,
        paths,
        *,
        project_inputs=None,
        project_payload=None,
        project_path="",
        project_warnings=(),
    ):
        unique_paths = list(dict.fromkeys(os.path.abspath(path) for path in paths))
        if not unique_paths:
            self.announce("No supported files were found in that selection.", "warning")
            self.render()
            return

        def worker(report, cancelled):
            report(5, "Inspecting selected paths", f"0/{len(unique_paths)} paths")
            sources, errors = discover_sources(unique_paths)
            if cancelled():
                raise CancelledOperation("Source discovery cancelled.")
            if not sources:
                raise ValueError("No readable .xlsx or .csv sources were found.")
            for index, source in enumerate(sources, start=1):
                if cancelled():
                    raise CancelledOperation("Source discovery cancelled.")
                source["_size"] = source_size(source)
                report(10 + 65 * index / len(sources), "Inspecting sources", f"{index}/{len(sources)}: {source['display_name']}")
            template = sources[0]
            if project_payload and project_payload.get("template"):
                template = next(
                    (
                        source
                        for source in sources
                        if source_matches_descriptor(source, project_payload["template"])
                    ),
                    template,
                )
            sheets = get_sheet_names(template) if template["type"] == "xlsx" else []
            duplicates = possible_duplicate_sources(sources)
            return sources, errors, sheets, duplicates

        def done(result):
            sources, errors, sheets, duplicates = result
            inputs = project_inputs or [
                {"kind": "file", "path": path}
                for path in unique_paths
            ]
            self.state.set_sources(sources, errors, inputs)
            if project_payload:
                restore_messages = self._restore_project(project_payload, sheets, project_path)
            else:
                self.state.sheet_names = sheets
                self.state.selected_sheet = sheets[0] if sheets else ""
                restore_messages = []
            self.state.duplicate_groups = duplicates
            self.filter_undo = None
            self.value_cache.clear()
            detail = "\n".join(f"{item.get('path', '')}: {item.get('error', '')}" for item in errors)
            detail = "\n".join(part for part in (detail, *project_warnings, *restore_messages) if part)
            if project_payload:
                message = (
                    f"Project opened: {len(self.state.sources)} source file(s) ready. "
                    "Review the settings, then run Check and Prepare to restore its filters."
                )
            else:
                message = f"{len(sources)} source file(s) ready. Choose the yellow-star template or continue."
            if errors:
                message += f" {len(errors)} item(s) could not be opened."
            warning_count = len(errors) + len(project_warnings) + len(restore_messages)
            self.announce(message, "warning" if warning_count else "success", detail)
            self.diagnostics.record(
                "sources_ready",
                source_count=len(self.state.sources),
                error_count=len(errors),
                project=bool(project_payload),
            )

        self.start_task("discover", "Finding source files", worker, done)

    def set_template(self):
        selected = self.selected_source_indices()
        if len(selected) != 1:
            return
        source = self.state.sources[selected[0]]
        if source_identity(source) == self.state.template_key:
            return
        self.state.set_template(source)
        self.filter_undo = None
        self.value_cache.clear()
        if source["type"] != "xlsx":
            self.state.sheet_names = []
            self.state.selected_sheet = ""
            self.announce("Template updated. Check and Prepare must run again.", "warning")
            self.render()
            return

        def worker(report, cancelled):
            report(20, "Reading worksheet names", source["display_name"])
            names = get_sheet_names(source)
            if cancelled():
                raise CancelledOperation("Worksheet scan cancelled.")
            return names

        def done(names):
            self.state.sheet_names = names
            self.state.selected_sheet = names[0] if names else ""
            self.announce("Template updated. Choose its worksheet, then run Check and Prepare.", "warning")

        self.start_task("sheets", "Reading template worksheets", worker, done)

    def exclude_sources(self):
        selected = self.selected_source_indices()
        if not selected:
            return
        self.state.exclude([self.state.sources[index] for index in selected])
        self.filter_undo = None
        self.value_cache.clear()
        self.announce("Selected files were excluded. Restore them here if needed.", "warning")
        if self.state.template_source and self.state.template_source["type"] == "xlsx":
            self._load_current_template_sheets()
        else:
            self.render()

    def restore_sources(self):
        self.state.restore_excluded()
        self.filter_undo = None
        self.value_cache.clear()
        self.announce("Excluded files were restored. Check and Prepare must run again.", "warning")
        self.render()

    def _load_current_template_sheets(self):
        source = self.state.template_source
        if not source or source["type"] != "xlsx":
            self.state.sheet_names = []
            self.state.selected_sheet = ""
            self.render()
            return

        def worker(report, cancelled):
            report(20, "Reading worksheet names", source["display_name"])
            names = get_sheet_names(source)
            if cancelled():
                raise CancelledOperation("Worksheet scan cancelled.")
            return names

        def done(names):
            self.state.sheet_names = names
            self.state.selected_sheet = names[0] if names else ""

        self.start_task("sheets", "Reading template worksheets", worker, done)

    def prepare_page(self):
        state = self.state
        card = self.card("Data layout")
        reference = state.template_source["display_name"] if state.template_source else "No template selected"
        self.paragraph(card, f"Reference: {reference}")
        if state.template_source and state.template_source["type"] == "xlsx":
            self.label(card, "Reference worksheet", SMALL, "muted").pack(anchor="w", pady=(5, 3))
            sheet_var = tk.StringVar(card, value=state.selected_sheet)
            combo = ttk.Combobox(
                card,
                textvariable=sheet_var,
                values=state.sheet_names,
                state="readonly" if state.sheet_names else "disabled",
                style="Proto.TCombobox",
            )
            combo.pack(fill="x")
            combo.bind("<<ComboboxSelected>>", lambda event: self.change_sheet(sheet_var.get()))
        self.check(
            card,
            "Different sheet names, same data layout",
            state.different_sheets,
            lambda value: self.change_setting("different_sheets", value),
        )
        self.paragraph(card, "Matches each workbook by the template headers when dated worksheet names differ.")
        self.check(
            card,
            "Keep extra columns at the end",
            state.allow_extra,
            lambda value: self.change_setting("allow_extra", value),
        )
        self.paragraph(card, "Files with every template column remain valid; extra columns are appended after the template columns.")
        self.layout_check = self.check(
            card,
            "Header is not on row 1, or footer rows must be ignored",
            state.fix_layout,
            lambda value: self.change_setting("fix_layout", value),
        )
        self.layout_fields = tk.Frame(card, bg=C["wash"], padx=10, pady=8)
        if state.fix_layout:
            self.layout_fields.pack(fill="x", pady=6)
            self._number_setting(self.layout_fields, "Header row", "header_row", state.header_row, 1)
            self._number_setting(self.layout_fields, "Footer rows to ignore", "footer_rows", state.footer_rows, 0)
            self.paragraph(self.layout_fields, "Example: two title rows above the header means Header row = 3.")

        if state.prepared:
            summary = state.validation.get("summary", {})
            prepared = self.card("Preparation summary")
            memory = get_dataframe_memory_mb(state.final_df)
            self.paragraph(
                prepared,
                f"{len(state.validation.get('passed_sources', []))} files combined | {state.total_rows:,} rows | "
                f"{len(state.columns):,} columns | {memory:.1f} MB in memory" if memory is not None else
                f"{len(state.validation.get('passed_sources', []))} files combined | {state.total_rows:,} rows | {len(state.columns):,} columns",
                "green",
            )
            self.paragraph(
                prepared,
                f"Validation: {summary.get('pass', 0)} passed, {summary.get('warn', 0)} warning, "
                f"{summary.get('fail', 0)} failed/excluded.",
                "amber" if summary.get("fail") or summary.get("warn") else "muted",
            )
            if state.extra_columns:
                self.paragraph(prepared, "Extra columns appended: " + ", ".join(state.extra_columns), "amber")
            self._validation_table(prepared)

        options = self.card("Processing options")
        mode = "Controlled parallel reads" if state.fast_mode else "Sequential reads"
        memory_mode = "Memory optimization on" if state.optimize_memory else "Original data types"
        self.paragraph(options, f"{memory_mode} | {mode}")
        body = self.disclosure(options, "Advanced performance options", "performance_open")
        self.button(body, "Use recommended settings", self.recommended_settings).pack(anchor="w", pady=(0, 5))
        self.check(
            body,
            "Optimize memory after combine (recommended)",
            state.optimize_memory,
            lambda value: self.change_setting("optimize_memory", value),
        )
        self.paragraph(body, "Downcasts only when values are preserved. This reduces memory used by the cached result.")
        self.check(
            body,
            "Read files with controlled parallelism",
            state.fast_mode,
            lambda value: self.change_setting("fast_mode", value),
        )
        self.paragraph(body, "Uses conservative worker limits; Excel and very large jobs use fewer concurrent readers.")
        total_size = sum(source.get("_size", source_size(source)) for source in state.sources)
        safe, warning, available, estimated = check_memory_before_combine(total_size, len(state.sources))
        if available is not None:
            self.paragraph(
                options,
                f"Memory check: {available:.1f} GB available | approximately {estimated:.1f} GB input expansion | "
                f"{'ready' if safe else 'low-memory warning'}.",
                "muted" if safe else "amber",
            )

    def _number_setting(self, parent, title, key, value, minimum):
        row = tk.Frame(parent, bg=C["wash"])
        row.pack(fill="x", pady=3)
        self.label(row, title).pack(side="left")
        variable = tk.IntVar(row, value=value)
        spin = tk.Spinbox(
            row,
            from_=minimum,
            to=10000,
            width=8,
            textvariable=variable,
            state="readonly",
            command=lambda: self.change_setting(key, int(variable.get())),
            font=BODY,
        )
        spin.pack(side="right")

    def change_sheet(self, sheet):
        if sheet == self.state.selected_sheet:
            return
        self.state.selected_sheet = sheet
        self.state.invalidate(clear_filters=True)
        self.filter_undo = None
        self.value_cache.clear()
        self.announce("Worksheet changed. Check and Prepare must run again.", "warning")
        self.render()

    def change_setting(self, key, value):
        if getattr(self.state, key) == value:
            return
        setattr(self.state, key, value)
        self.state.invalidate(clear_filters=True)
        self.filter_undo = None
        self.value_cache.clear()
        self.announce("Layout or processing settings changed. Check and Prepare must run again.", "warning")
        self.render()

    def recommended_settings(self):
        changed = not self.state.optimize_memory or self.state.fast_mode
        self.state.optimize_memory = True
        self.state.fast_mode = False
        if changed:
            self.state.invalidate(clear_filters=True)
            self.filter_undo = None
            self.value_cache.clear()
        self.announce("Recommended settings applied." + (" Prepare the data again to use them." if changed else ""))
        self.render()

    def _validation_table(self, parent):
        results = self.state.validation.get("results", [])
        if not results:
            return
        table = self.table(parent, ("File", "Status", "Sheet", "Details"), height=min(7, len(results)), widths=(240, 80, 140, 380))
        for index, result in enumerate(results):
            table.insert(
                "",
                "end",
                values=(
                    result.get("name", ""),
                    str(result.get("status", "")).upper(),
                    result.get("sheet") or "",
                    result.get("detail", ""),
                ),
                tags=("stripe",) if index % 2 else (),
            )

    def start_prepare(self):
        state = self.state
        if not state.sources or state.template_index is None:
            return
        if state.template_source["type"] == "xlsx" and not state.selected_sheet:
            self.announce("Choose the reference worksheet before preparing.", "warning")
            self.render()
            return
        total_size = sum(source.get("_size", source_size(source)) for source in state.sources)
        safe, warning, _, _ = check_memory_before_combine(total_size, len(state.sources))
        if not safe and not messagebox.askyesno(
            "Low-memory warning",
            warning + "\n\nContinue with the current selection?",
            parent=self,
        ):
            return
        sources = list(state.sources)
        reference_index = state.template_index
        selected_sheet = state.selected_sheet or None
        header_row = state.header_row if state.fix_layout else 1
        footer_rows = state.footer_rows if state.fix_layout else 0

        def worker(report, cancelled):
            validation_started = time.monotonic()

            def validation_progress(done, total):
                if cancelled():
                    raise CancelledOperation("Validation cancelled.")
                report(5 + 35 * done / max(1, total), "Validating file layouts", f"{done}/{total} files checked")

            validation = validate_sources(
                sources,
                reference_index,
                selected_sheet=selected_sheet,
                header_row=header_row,
                footer_rows=footer_rows,
                allow_extra=state.allow_extra,
                auto_match_sheet=state.different_sheets,
                progress_callback=validation_progress,
            )
            validation["elapsed_seconds"] = time.monotonic() - validation_started
            passed = validation["passed_sources"]
            reference = sources[reference_index]
            passed_keys = {source_cache_key(source) for source in passed}
            if source_cache_key(reference) not in passed_keys:
                raise ValueError("The reference template failed validation. Review its worksheet and header settings.")
            if not passed:
                raise ValueError("No source passed validation. Review the validation settings and retry.")

            def combine_progress(done, total, bytes_done, bytes_total):
                if cancelled():
                    raise CancelledOperation("Combine cancelled.")
                ratio = bytes_done / max(1, bytes_total)
                report(43 + 54 * ratio, "Combining validated files", f"{done}/{total} files | {format_size(bytes_done)} of {format_size(bytes_total)}")

            final_df, extras, memory_stats = combine_sources(
                passed,
                reference,
                validation["reference_columns"],
                selected_sheet=selected_sheet,
                source_sheet_map=validation["source_sheet_map"],
                header_row=header_row,
                footer_rows=footer_rows,
                allow_extra=state.allow_extra,
                extra_columns=validation["extra_columns"],
                fast_mode=state.fast_mode,
                optimize_memory=state.optimize_memory,
                progress_callback=combine_progress,
                cancel_callback=cancelled,
            )
            report(99, "Finalizing cached result", f"{len(final_df):,} rows ready")
            return validation, final_df, extras, memory_stats

        def done(result):
            validation, final_df, extras, memory_stats = result
            pending_filters = [dict(config) for config in state.pending_filters]
            state.set_prepared(validation, final_df, extras, memory_stats)
            restored_filters = [
                config for config in pending_filters if config.get("column") in state.columns
            ]
            skipped_filters = len(pending_filters) - len(restored_filters)
            restored_count = 0
            state.pending_filters = []
            if restored_filters:
                try:
                    state.filters = restored_filters
                    state.filtered_df = apply_engine_filters(state.final_df, restored_filters)
                    restored_count = len(restored_filters)
                except Exception:
                    skipped_filters += len(restored_filters)
                    state.filters = []
                    state.filtered_df = state.final_df
            self.filter_undo = None
            self.value_cache.clear()
            summary = validation["summary"]
            kind = "warning" if summary.get("fail") or summary.get("warn") or skipped_filters else "success"
            filter_note = ""
            if restored_count and not skipped_filters:
                filter_note = f" {restored_count} project filter(s) restored."
            elif pending_filters:
                filter_note = (
                    f" {restored_count} project filter(s) restored; "
                    f"{skipped_filters} incompatible filter(s) skipped."
                )
            self.announce(
                f"Preparation complete: {len(validation['passed_sources'])} files, {len(final_df):,} rows. "
                f"{summary.get('fail', 0)} failed file(s) were excluded.{filter_note}",
                kind,
            )
            self.diagnostics.record(
                "prepare_completed",
                source_count=len(validation["passed_sources"]),
                row_count=len(final_df),
                column_count=len(final_df.columns),
                failed_count=summary.get("fail", 0),
                restored_filters=restored_count,
                skipped_filters=skipped_filters,
            )

        self.start_task("prepare", "Checking file layouts", worker, done)

    def filters_page(self):
        state = self.state
        workspace = ResponsiveWorkspace(self.content)
        workspace.pack(fill="x")
        card = self.card(f"Filters / {len(state.filters)} active", workspace.left)
        self.paragraph(card, f"{state.result_rows:,} of {state.total_rows:,} rows match. Source files are not reread.")
        row = tk.Frame(card, bg=C["surface"])
        row.pack(fill="x", pady=8)
        self.add_filter_button = self.button(row, "+ Add filter", self.open_filter_dialog)
        self.add_filter_button.pack(side="left")
        clear = self.button(row, "Clear", self.clear_filters)
        clear.pack(side="left", padx=5)
        clear.configure(state="normal" if state.filters else "disabled")
        undo = self.button(row, "Undo", self.undo_filter_change)
        undo.pack(side="left")
        undo.configure(state="normal" if self.filter_undo is not None else "disabled")
        if not state.filters:
            self.paragraph(card, "No filters yet. Export every row, or add a filter and search a prefix such as Wa.")
        for index, config in enumerate(state.filters):
            strip = tk.Frame(card, bg=C["wash"], padx=10, pady=6)
            strip.pack(fill="x", pady=4)
            actions = tk.Frame(strip, bg=C["wash"])
            actions.pack(side="right")
            self.button(actions, "Edit", lambda position=index: self.open_filter_dialog(position)).pack(side="left")
            self.button(actions, "Remove", lambda position=index: self.remove_filter(position)).pack(side="left", padx=(6, 0))
            self.paragraph(strip, filter_summary(config), "ink")
        if state.filter_problem():
            self.paragraph(card, state.filter_problem(), "amber")
        elif state.filtered_df is not None and state.filtered_df.empty:
            self.paragraph(card, "Nothing matches all filters. Edit or remove a filter before export.", "amber")
        self.paragraph(card, "Ctrl+F opens the filter editor. All active filters must match.")
        self.preview(self.card("Result preview", workspace.right))

    def open_filter_dialog(self, index=None):
        if self.busy or not self.state.prepared:
            return
        if self.filter_dialog_window and self.filter_dialog_window.winfo_exists():
            self.filter_dialog_window.lift()
            return
        if not self.state.columns:
            self.announce("No columns are available for filtering.", "warning")
            self.render()
            return
        self.filter_dialog_window = FilterDialog(self, index)

    def commit_filter(self, index, config):
        updated = [dict(item) for item in self.state.filters]
        if index is None:
            updated.append(config)
        else:
            updated[index] = config
        self.apply_filter_change(updated)

    def clear_filters(self):
        if self.state.filters:
            self.apply_filter_change([])

    def remove_filter(self, index):
        updated = [dict(item) for item in self.state.filters]
        updated.pop(index)
        self.apply_filter_change(updated)

    def undo_filter_change(self):
        if self.filter_undo is None or self.busy:
            return
        updated = [dict(item) for item in self.filter_undo]
        self.apply_filter_change(updated, consume_undo=True)

    def apply_filter_change(self, updated, consume_undo=False):
        previous_filters = [dict(item) for item in self.state.filters]
        source_frame = self.state.final_df

        def worker(report, cancelled):
            report(15, "Applying filters", f"{len(updated)} active filter(s)")
            if cancelled():
                raise CancelledOperation("Filter update cancelled.")
            result = apply_engine_filters(source_frame, updated)
            if cancelled():
                raise CancelledOperation("Filter update cancelled.")
            report(95, "Updating cached preview", f"{len(result):,} rows match")
            return result

        def done(result):
            self.state.filters = updated
            self.state.filtered_df = result
            self.state.saved_signature = None
            self.filter_undo = None if consume_undo else previous_filters
            self.announce(f"Filters updated: {len(result):,} of {self.state.total_rows:,} rows match.", "success")

        def failed(exc, detail):
            self.announce("The filter could not be applied. Previous filters were restored.", "warning", detail)

        self.start_task("filter", "Updating filtered result", worker, done, failed)

    def preview(self, parent):
        state = self.state
        controls = tk.Frame(parent, bg=C["surface"])
        controls.pack(fill="x")
        self.label(controls, "Rows shown", SMALL, "muted").pack(side="left")
        preview_var = tk.StringVar(controls, value=str(self.preview_limit))
        combo = ttk.Combobox(
            controls,
            textvariable=preview_var,
            values=("5", "10", "25"),
            state="readonly",
            width=5,
            style="Proto.TCombobox",
        )
        combo.pack(side="left", padx=6)
        combo.bind("<<ComboboxSelected>>", lambda event: self.change_preview_limit(int(preview_var.get())))
        copy_button = self.button(controls, "Copy selected", self.copy_preview)
        copy_button.pack(side="right")
        frame = state.filtered_df
        if frame is None:
            self.paragraph(parent, "The preview will appear after preparation.")
            copy_button.configure(state="disabled")
            return
        visible_columns = list(frame.columns[:PREVIEW_COLUMN_LIMIT])
        self.preview_columns = visible_columns
        table = self.table(parent, visible_columns, height=min(10, self.preview_limit), widths=tuple(130 for _ in visible_columns), selectmode="extended")
        self.preview_table = table
        for index, row in enumerate(frame.loc[:, visible_columns].head(self.preview_limit).itertuples(index=False, name=None)):
            values = tuple(self._display_value(value) for value in row)
            table.insert("", "end", values=values, tags=("stripe",) if index % 2 else ())
        table.bind("<Control-c>", lambda event: self.copy_preview())
        table.bind("<<TreeviewSelect>>", lambda event: copy_button.configure(state="normal" if table.selection() else "disabled"))
        copy_button.configure(state="disabled")
        note = f"Showing up to {self.preview_limit} rows. Export includes all {len(frame):,} matching rows."
        if len(frame.columns) > PREVIEW_COLUMN_LIMIT:
            note += f" Preview is limited to the first {PREVIEW_COLUMN_LIMIT} columns for responsiveness."
        self.paragraph(parent, note)

    @staticmethod
    def _display_value(value):
        try:
            if pd.isna(value):
                return ""
        except (TypeError, ValueError):
            pass
        text = str(value)
        return text if len(text) <= 300 else text[:297] + "..."

    def change_preview_limit(self, value):
        self.preview_limit = value
        self.render()

    def copy_preview(self):
        table = self.preview_table
        if not table or not table.winfo_exists() or not table.selection():
            return
        headers = [str(column) for column in self.preview_columns]
        lines = ["\t".join(headers)]
        for item in table.selection():
            lines.append("\t".join(str(value) for value in table.item(item, "values")))
        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))
        self.announce(f"Copied {len(lines) - 1} preview row(s) with headers.", "success")

    def export_page(self):
        state = self.state
        if state.saved and state.history:
            success = self.card("Export complete")
            latest = state.history[0]
            self.paragraph(success, f"{os.path.basename(latest['path'])} | {latest['rows']:,} rows | {format_size(latest['size'])}", "green")
            row = tk.Frame(success, bg=C["surface"])
            row.pack(fill="x", pady=(5, 0))
            self.button(row, "Open file", lambda: self.open_path(latest["path"]), primary=True).pack(side="left")
            self.button(row, "Open folder", lambda: self.open_path(os.path.dirname(latest["path"]))).pack(side="left", padx=6)
            self.button(row, "Open audit report", lambda: self.open_path(latest["audit_path"])).pack(side="left")
            self.button(row, "Change filters", self.reuse_for_filters).pack(side="right")
            self.button(row, "New file, same filters", self.new_export_name).pack(side="right", padx=6)

        workspace = ResponsiveWorkspace(self.content)
        workspace.pack(fill="x")
        settings = self.card("Output settings", workspace.left)
        self.label(settings, "Format", SMALL, "muted").pack(anchor="w", pady=(0, 3))
        format_var = tk.StringVar(settings, value=state.output_format)
        combo = ttk.Combobox(
            settings,
            textvariable=format_var,
            values=tuple(EXPORT_FORMATS),
            state="readonly",
            style="Proto.TCombobox",
        )
        combo.pack(fill="x")
        combo.bind("<<ComboboxSelected>>", lambda event: self.change_export_format(format_var.get()))

        if state.output_format == "CSV-Unique text":
            picker_frame = tk.Frame(settings, bg=C["wash"], padx=10, pady=8)
            picker_frame.pack(fill="x", pady=(8, 0))
            self.label(picker_frame, "Columns to preserve as text", BOLD).pack(anchor="w")
            self.paragraph(picker_frame, "Use for IDs and values with leading zeros. This picker appears only for CSV-Unique text.")
            selection = ValueSelection((str(column) for column in state.columns), state.protected_columns)

            def protect_changed():
                state.protected_columns = set(selection.result())
                state.saved_signature = None
                self._navigation()

            self.protected_picker = CategoryPicker(picker_frame, selection, self.button, protect_changed)
            self.protected_picker.pack(fill="both", expand=True)
        else:
            self.paragraph(settings, "Choose CSV-Unique text if identifiers must remain text in downstream tools.")

        self.label(settings, "Output file", SMALL, "muted").pack(anchor="w", pady=(10, 3))
        path_row = tk.Frame(settings, bg=C["surface"])
        path_row.pack(fill="x")
        self.output_path_var = tk.StringVar(path_row, value=state.output_path)
        entry = tk.Entry(path_row, textvariable=self.output_path_var, font=BODY, relief="solid", bd=1, bg=C["surface"], fg=C["ink"])
        entry.pack(side="left", fill="x", expand=True, ipady=7)
        self.button(path_row, "Browse", self.pick_output_path).pack(side="left", padx=(6, 0))
        self.output_path_var.trace_add("write", self.output_path_changed)
        self.paragraph(settings, "A completed export replaces the destination atomically. Cancelled exports do not commit partial output.")
        self.paragraph(settings, "Not exported with the current settings." if not state.saved else "Current result has been exported.", "amber" if not state.saved else "green")

        self.preview(self.card("Result preview", workspace.right))
        if state.history:
            history = self.card("Export history / this session", workspace.right)
            for item in state.history[:5]:
                row = tk.Frame(history, bg=C["surface"])
                row.pack(fill="x", pady=3)
                self.label(row, f"{item['created']} | {os.path.basename(item['path'])} | {item['rows']:,} rows", SMALL).pack(side="left", fill="x", expand=True)
                self.button(row, "Open", lambda path=item["path"]: self.open_path(path)).pack(side="right")

    def change_export_format(self, export_format):
        if export_format == self.state.output_format:
            return
        self.state.output_format = export_format
        path = self.state.output_path
        if path:
            self.state.output_path = ensure_export_extension(path, export_format)
        elif self.state.template_source:
            from .state import default_output_path

            self.state.output_path = default_output_path(self.state.template_source, export_format)
        self.state.saved_signature = None
        self.announce("Export format updated. Prepared and filtered data remain cached.")
        self.render()

    def output_path_changed(self, *args):
        if not hasattr(self, "output_path_var"):
            return
        self.state.output_path = self.output_path_var.get()
        self.state.saved_signature = None
        self._navigation()

    def pick_output_path(self):
        state = self.state
        current = state.output_path
        path = filedialog.asksaveasfilename(
            title="Save output as",
            parent=self,
            initialdir=os.path.dirname(current) if current else None,
            initialfile=os.path.basename(current) if current else None,
            defaultextension=EXPORT_FORMATS[state.output_format]["extension"],
            filetypes=EXPORT_FORMATS[state.output_format]["filetypes"],
        )
        if path:
            state.output_path = ensure_export_extension(path, state.output_format)
            state.saved_signature = None
            self.render()

    def start_export(self):
        state = self.state
        if hasattr(self, "output_path_var"):
            state.output_path = self.output_path_var.get().strip()
        try:
            state.validate_export()
        except ValueError as exc:
            self.announce(str(exc), "warning")
            self.render()
            return
        output_path = os.path.abspath(state.output_path)
        if os.path.exists(output_path) and not messagebox.askyesno(
            "Replace existing file?",
            f"A file already exists:\n{output_path}\n\nReplace it after the new export completes?",
            parent=self,
        ):
            return
        frame = state.filtered_df
        export_format = state.output_format
        protected = sorted(state.protected_columns.intersection(state.columns))
        report_frame = validation_report_frame(state.validation)

        def worker(report, cancelled):
            started = time.monotonic()

            def export_progress(percent, detail):
                if cancelled():
                    raise CancelledOperation("Export cancelled.")
                report(percent, "Writing output safely", detail)

            save_dataframe(
                frame,
                output_path,
                export_format,
                unique_columns=protected,
                validation_report_df=report_frame,
                progress_callback=export_progress,
                cancel_callback=cancelled,
            )
            elapsed = time.monotonic() - started
            file_size = os.path.getsize(output_path)
            audit_path = ""
            audit_error = ""
            try:
                audit_path = write_audit_report(state, output_path, len(frame), file_size, elapsed)
            except Exception as exc:
                audit_error = f"{exc.__class__.__name__}: {exc}"
            return output_path, len(frame), file_size, elapsed, audit_path, audit_error

        def done(result):
            path, row_count, file_size, elapsed, audit_path, audit_error = result
            if not audit_path:
                audit_path = os.path.splitext(path)[0] + ".audit.txt"
            state.mark_exported(path, row_count, file_size, audit_path)
            if audit_error:
                self.announce(
                    f"Export complete: {row_count:,} rows. The audit report could not be written.",
                    "warning",
                    audit_error,
                )
            else:
                self.announce(f"Export complete: {row_count:,} rows written in {elapsed:.1f} seconds.", "success")

        self.start_task("export", "Preparing export", worker, done)

    def reuse_for_filters(self):
        self.state.suggest_next_output()
        self.state.saved_signature = None
        self.announce("Prepared data was kept. Change filters and export again without reloading sources.")
        self.go(2)

    def new_export_name(self):
        self.state.suggest_next_output()
        self.announce("A new output name is ready. Prepared data and filters remain unchanged.")
        self.render()

    def open_path(self, path):
        if not path or not os.path.exists(path):
            self.announce("That file or folder is no longer available.", "warning")
            self.render()
            return False
        try:
            if os.name == "nt":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
            return True
        except Exception as exc:
            self.announce("Windows could not open that location.", "warning", str(exc))
            self.render()
            return False

    def start_task(self, kind, title, worker, on_done, on_error=None):
        if self.busy:
            return
        self.busy = True
        self.stopping = False
        self.task_kind = kind
        self.task_title = title
        self.task_started = time.monotonic()
        self.task_percent = 0
        self.task_detail = "Starting..."
        self.task_done_callback = on_done
        self.task_error_callback = on_error
        self.cancel_event = threading.Event()
        self.progress.configure(value=0)
        self.diagnostics.record(
            "task_started",
            task=kind,
            step=self.step + 1,
            source_count=len(self.state.sources),
        )
        self.render()

        def report(percent, phase, detail=""):
            self.task_queue.put(("progress", float(percent), phase, detail))

        def cancelled():
            return self.cancel_event.is_set()

        def run():
            try:
                result = worker(report, cancelled)
                self.task_queue.put(("done", result))
            except CancelledOperation as exc:
                self.task_queue.put(("cancelled", str(exc)))
            except Exception as exc:
                self.task_queue.put(("error", exc, traceback.format_exc()))

        self.task_thread = threading.Thread(target=run, name=f"MergeGuru-{kind}", daemon=True)
        self.task_thread.start()
        self.task_poll = self.after(80, self.poll_task)

    def poll_task(self):
        self.task_poll = None
        handled_terminal = False
        while True:
            try:
                event = self.task_queue.get_nowait()
            except queue.Empty:
                break
            kind = event[0]
            if kind == "progress":
                _, percent, phase, detail = event
                self.task_percent = max(0, min(100, percent))
                self.task_title = phase
                self.task_detail = detail
                self.progress.configure(value=self.task_percent)
            elif kind == "done":
                handled_terminal = True
                self._finish_task_success(event[1])
            elif kind == "cancelled":
                handled_terminal = True
                self._finish_task_cancelled(event[1])
            elif kind == "error":
                handled_terminal = True
                self._finish_task_error(event[1], event[2])
        if self.busy:
            elapsed = time.monotonic() - self.task_started
            eta = "--"
            if self.task_percent > 1:
                remaining = elapsed * (100 - self.task_percent) / self.task_percent
                eta = self._format_duration(remaining)
            detail = f"Elapsed {self._format_duration(elapsed)} | ETA {eta}"
            if self.task_detail:
                detail += f" | {self.task_detail}"
            self.progress_title.configure(text=f"{self.task_title} / {self.task_percent:.0f}%")
            self.progress_caption.configure(text=detail)
            if not handled_terminal:
                self.task_poll = self.after(100, self.poll_task)

    def _end_task(self):
        thread = self.task_thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self.busy = False
        self.stopping = False
        self.task_thread = None
        self.task_kind = ""
        self.progress.configure(value=0)

    def _finish_task_success(self, result):
        callback = self.task_done_callback
        task_kind = self.task_kind
        elapsed = time.monotonic() - self.task_started
        self._end_task()
        try:
            callback(result)
        except Exception as exc:
            self.last_error_type = exc.__class__.__name__
            self.diagnostics.record(
                "task_result_failed",
                task=task_kind,
                error_type=self.last_error_type,
            )
            self.announce("The operation finished, but its result could not be shown.", "warning", traceback.format_exc())
        else:
            self.diagnostics.record("task_completed", task=task_kind, elapsed_seconds=elapsed)
        self.render()

    def _finish_task_cancelled(self, detail):
        task_kind = self.task_kind
        elapsed = time.monotonic() - self.task_started
        self._end_task()
        self.diagnostics.record("task_cancelled", task=task_kind, elapsed_seconds=elapsed)
        self.announce("Operation cancelled safely. Existing prepared data and completed outputs were kept.", "warning", detail)
        self.render()

    def _finish_task_error(self, exc, detail):
        callback = self.task_error_callback
        task_kind = self.task_kind
        elapsed = time.monotonic() - self.task_started
        self._end_task()
        self.last_error_type = exc.__class__.__name__
        self.diagnostics.record(
            "task_failed",
            task=task_kind,
            elapsed_seconds=elapsed,
            error_type=self.last_error_type,
        )
        if callback:
            callback(exc, detail)
        else:
            self.announce(self._human_error(exc), "warning", detail)
        self.render()

    def cancel_task(self):
        if not self.busy or self.stopping:
            return
        self.stopping = True
        self.cancel_event.set()
        self.task_title = "Stopping safely"
        self.task_detail = "Waiting for the current file or write checkpoint"
        self.cancel_button.configure(state="disabled")
        self._navigation()

    @staticmethod
    def _human_error(exc):
        if isinstance(exc, ValueError):
            return str(exc)
        category, detail = classify_file_error(exc)
        actions = {
            "locked/permission": "Close the file in Excel or request access, then retry.",
            "corrupt": "Download or recreate the file, then retry.",
            "password-protected": "Remove workbook protection or use an unprotected copy.",
            "unsupported": "Convert the source to .xlsx or .csv and retry.",
        }
        return f"{detail} {actions.get(category, 'Review the technical detail, correct the source, and retry.')}"

    @staticmethod
    def _format_duration(seconds):
        seconds = max(0, int(seconds))
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def show_technical_detail(self):
        dialog = tk.Toplevel(self, bg=C["surface"], padx=16, pady=12)
        dialog.title("Technical detail")
        dialog.transient(self)
        dialog.geometry("720x420")
        text = tk.Text(dialog, wrap="word", font=("Consolas", 9), bg=C["wash"], fg=C["ink"], relief="flat")
        text.pack(fill="both", expand=True)
        text.insert("1.0", self.technical_detail or "No technical detail is available.")
        text.configure(state="disabled")
        actions = tk.Frame(dialog, bg=C["surface"])
        actions.pack(fill="x", pady=(8, 0))
        self.button(actions, "Save privacy-safe diagnostics...", self.save_diagnostics).pack(side="left")
        self.button(actions, "Close", dialog.destroy, primary=True).pack(side="right")

    def save_diagnostics(self):
        default_name = time.strftime("MergeGuru_Diagnostics_%Y%m%d_%H%M%S.txt")
        path = filedialog.asksaveasfilename(
            title="Save privacy-safe diagnostics",
            parent=self,
            initialfile=default_name,
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt")],
        )
        if not path:
            return
        try:
            saved = self.diagnostics.write_report(
                path,
                self.state,
                current_step=self.STEPS[self.step],
                task_kind=self.task_kind,
                last_error_type=self.last_error_type,
            )
        except OSError as exc:
            self.announce("Diagnostics could not be saved. Choose another location and retry.", "warning", str(exc))
        else:
            self.announce(
                f"Privacy-safe diagnostics saved as {os.path.basename(saved)}. No source names or data were included.",
                "success",
            )
        self.render()

    def request_close(self):
        if self.busy:
            self.cancel_task()
            return
        if self.filter_dialog_window and self.filter_dialog_window.winfo_exists():
            self.filter_dialog_window.lift()
            return
        unsaved = self.state.prepared and not self.state.saved
        if unsaved and not messagebox.askyesno(
            "Close without exporting?",
            "The current result has not been exported. Close anyway? Existing files will be kept.",
            parent=self,
        ):
            return
        self.diagnostics.record(
            "application_closed",
            prepared=self.state.prepared,
            exported=self.state.saved,
        )
        self._save_preferences()
        self.destroy()

    def _save_preferences(self):
        geometry = self.geometry().split("+")[0]
        values = {
            "allow_extra": self.state.allow_extra,
            "different_sheets": self.state.different_sheets,
            "optimize_memory": self.state.optimize_memory,
            "fast_mode": self.state.fast_mode,
            "output_format": self.state.output_format,
            "preview_limit": self.preview_limit,
            "window_geometry": geometry,
        }
        try:
            save_preferences(values, self.preference_file)
        except OSError:
            pass

    def destroy(self):
        if self.task_poll:
            try:
                self.after_cancel(self.task_poll)
            except tk.TclError:
                pass
            self.task_poll = None
        self.cancel_event.set()
        self._unbind_mousewheel()
        icon = getattr(self, "brand_icon", None)
        if icon is not None and getattr(icon, "name", None):
            try:
                self.tk.call("image", "delete", icon.name)
                icon.name = None
            except tk.TclError:
                pass
            self.brand_icon = None
        super().destroy()
