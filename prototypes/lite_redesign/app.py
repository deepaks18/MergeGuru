"""Tkinter interaction prototype: sample data, simulated tasks, zero file writes."""

import csv
import io
import math
import time
import tkinter as tk
from tkinter import ttk

from .brand import BrandHeader, make_icon
from .category_picker import CategoryPicker
from .selection import ValueSelection
from .workspace import ResponsiveWorkspace
from .state import DemoState, Filter, FORMATS, SAMPLE_FILES
from .theme import BODY, BOLD, COLORS as C, SECTION, SMALL, TITLE


class LitePrototype(tk.Tk):
    STEPS = ("Sources", "Check & Prepare", "Filters", "Export")

    def __init__(self):
        super().__init__()
        self.title("MergeGuru Lite | Redesign prototype - SAMPLE DATA ONLY")
        self.geometry("1060x780")
        self.minsize(720, 560)
        self.configure(bg=C["paper"])
        self.brand_icon = make_icon(self)
        self.iconphoto(True, self.brand_icon)
        self.demo = DemoState()
        self.step = 0
        self.busy = False
        self.stopping = False
        self.job = ""
        self.timer = None
        self.notice_text = ""
        self.notice_kind = "info"
        self.wrap_labels = []
        self.dialog = None
        self.performance_open = False
        self.source_preview_open = False
        self.preview_limit = 10
        self.filter_undo = None
        self._style()
        self._shell()
        self.render()
        self.protocol("WM_DELETE_WINDOW", self.request_close)
        self.bind("<Alt-n>", lambda event: self.primary())
        self.bind("<Alt-b>", lambda event: self.go(self.step - 1))
        self.bind("<Escape>", lambda event: self.cancel() if self.busy else None)
        self.bind("<Control-f>", self.keyboard_filter)

    def _style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Proto.TCombobox", padding=7, fieldbackground=C["surface"], foreground=C["ink"])
        style.map("Proto.TCombobox", fieldbackground=[("disabled", C["wash"]), ("readonly", C["surface"])],
                  foreground=[("disabled", C["disabled"])])
        style.configure("Proto.Treeview", background=C["surface"], fieldbackground=C["surface"],
                        foreground=C["ink"], rowheight=28, font=BODY, borderwidth=0)
        style.configure("Proto.Treeview.Heading", background=C["wash"], foreground=C["ink"],
                        font=BOLD, padding=7, relief="flat")
        style.map("Proto.Treeview", background=[("selected", C["blue"])], foreground=[("selected", C["surface"])])
        style.configure("Proto.Horizontal.TProgressbar", background=C["cyan"],
                        troughcolor=C["line"], borderwidth=0, thickness=7)
        style.configure("TScrollbar", background=C["line"], troughcolor=C["paper"],
                        arrowcolor=C["muted"], bordercolor=C["line"])
        style.map("TScrollbar", background=[("active", C["cyan"]), ("pressed", C["blue"])])

    def label(self, parent, text, font=BODY, color="ink", background=None, **kwargs):
        bg = background or parent.cget("bg")
        kwargs.setdefault("anchor", "w")
        kwargs.setdefault("justify", "left")
        widget = tk.Label(parent, text=text, font=font, fg=C[color], bg=bg,
                          **kwargs)
        return widget

    def paragraph(self, parent, text, color="muted"):
        widget = self.label(parent, text, color=color, wraplength=280)
        widget.pack(fill="x", pady=(3, 3))
        widget.bind("<Configure>", lambda event: widget.configure(wraplength=max(120, event.width)))
        self.wrap_labels.append(widget)
        return widget

    def button(self, parent, text, command, primary=False):
        button = tk.Button(parent, text=text, command=command, font=BOLD, cursor="hand2",
                           bg=C["blue"] if primary else C["surface"],
                           fg=C["surface"] if primary else C["ink"],
                           activebackground=C["blue_hover"] if primary else C["wash"],
                           activeforeground=C["surface"] if primary else C["ink"],
                           disabledforeground=C["disabled_on_blue"] if primary else C["disabled"], relief="flat", bd=0,
                           highlightthickness=1, highlightbackground=C["line"],
                           highlightcolor=C["blue"], padx=10, pady=6, takefocus=True)
        button.bind("<Return>", lambda event: button.invoke())
        return button

    def card(self, title, parent=None):
        frame = tk.Frame(parent or self.content, bg=C["surface"], padx=12, pady=10,
                         highlightthickness=1, highlightbackground=C["line"])
        frame.pack(fill="x", pady=(0, 10))
        if title:
            self.label(frame, title, SECTION).pack(anchor="w", pady=(0, 6))
        return frame

    def disclosure(self, parent, title, flag):
        row = tk.Frame(parent, bg=parent.cget("bg"))
        row.pack(fill="x", pady=(4, 2))
        self.label(row, title, BOLD).pack(side="left")
        def toggle():
            setattr(self, flag, not getattr(self, flag))
            self.render()
        button = self.button(row, "Hide" if getattr(self, flag) else "Show", toggle)
        button.pack(side="right")
        body = tk.Frame(parent, bg=parent.cget("bg"))
        if getattr(self, flag):
            body.pack(fill="x", pady=(5, 0))
        return body, button

    def check(self, parent, text, value, command):
        var = tk.BooleanVar(self, value=value)
        widget = tk.Checkbutton(parent, text=text, variable=var, command=lambda: command(var.get()),
                                bg=parent.cget("bg"), fg=C["ink"], selectcolor=C["surface"],
                                activebackground=C["wash"], activeforeground=C["ink"],
                                font=BODY, anchor="w", justify="left", wraplength=560,
                                padx=0, pady=5, takefocus=True)
        widget.pack(fill="x", anchor="w")
        widget.bind("<Configure>", lambda event: widget.configure(wraplength=max(120, event.width - 30)))
        self.wrap_labels.append(widget)
        return widget

    def _shell(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.brand_header = BrandHeader(self)
        self.brand_header.grid(row=0, column=0, sticky="ew")
        nav = tk.Frame(self, bg=C["surface"], padx=12, pady=6)
        nav.grid(row=1, column=0, sticky="ew")
        self.steps = []
        self.step_states, self.step_marks = [], []
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
        self.bind("<MouseWheel>", self._wheel)
        self.bind("<Button-4>", self._wheel)
        self.bind("<Button-5>", self._wheel)

        self.dock = tk.Frame(self, bg=C["cyan_wash"], padx=20, pady=10)
        self.dock.grid(row=3, column=0, sticky="ew")
        self.dock.grid_columnconfigure(0, weight=1)
        self.progress_title = self.label(self.dock, "Ready to explore", BOLD)
        self.progress_title.grid(row=0, column=0, sticky="w")
        self.cancel_button = self.button(self.dock, "Cancel", self.cancel)
        self.cancel_button.grid(row=0, column=1, rowspan=2, padx=(10, 0))
        self.progress_caption = self.label(self.dock, "Simulated progress only. Your real application is unchanged.", SMALL)
        self.progress_caption.grid(row=1, column=0, sticky="ew", pady=(3, 4))
        self.progress = ttk.Progressbar(self.dock, style="Proto.Horizontal.TProgressbar", maximum=100)
        self.progress.grid(row=2, column=0, columnspan=2, sticky="ew")
        footer = tk.Frame(self, bg=C["surface"], padx=16, pady=9)
        footer.grid(row=4, column=0, sticky="ew")
        self.back_button = self.button(footer, "Back", lambda: self.go(self.step - 1))
        self.back_button.pack(side="left")
        self.primary_button = self.button(footer, "Review layout", self.primary, primary=True)
        self.primary_button.pack(side="right")
        self.close_button = self.button(footer, "Close without export", self.request_close)
        self.close_button.pack(side="right", padx=8)
        self.next_hint = self.label(footer, "", SMALL, "muted", wraplength=220)
        self.next_hint.pack(side="left", fill="x", expand=True, padx=12)
        self.next_hint.bind("<Configure>", lambda event: self.next_hint.configure(wraplength=max(100, event.width)))

    def _resize(self, event):
        self.canvas.itemconfigure(self.content_window, width=event.width)
        for label in self.wrap_labels:
            if label.winfo_exists():
                label.configure(wraplength=max(120, label.winfo_width() if label.winfo_width() > 1 else label.master.winfo_width() - 30))

    def _wheel(self, event):
        if event.widget.winfo_toplevel() != self or isinstance(event.widget, (ttk.Treeview, ttk.Combobox)):
            return
        units = -1 if getattr(event, "num", 0) == 4 else 1 if getattr(event, "num", 0) == 5 else -int(event.delta / 120)
        if not units and getattr(event, "delta", 0):
            units = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(units, "units")

    def announce(self, text, kind="info"):
        self.notice_text, self.notice_kind = text, kind

    def can_go(self, target):
        if not 0 <= target < 4 or self.busy:
            return False
        if target == 1:
            return bool(self.demo.sources)
        return target < 2 or self.demo.prepared

    def keyboard_filter(self, event=None):
        if not self.busy and self.step == 2 and self.demo.prepared:
            self.filter_dialog()
        return "break"

    def go(self, target):
        if self.can_go(target):
            self.step = target
            self.render()

    def render(self):
        for child in self.content.winfo_children():
            child.destroy()
        self.wrap_labels = []
        self.canvas.yview_moveto(0)
        headings = (("Choose your data", "Select files and use one file's columns as the template."),
                    ("Prepare your data", "Confirm the layout, then check and combine the sample files."),
                    ("Filter your results", "Search values, include or exclude groups, and review the result."),
                    ("Review and export", "Choose the format and file name, then check your result."))
        title, subtitle = headings[self.step]
        self.label(self.content, title, TITLE).pack(anchor="w", pady=(4, 0))
        self.paragraph(self.content, subtitle)
        if self.notice_text:
            notice = tk.Frame(self.content, bg=C["amber_wash"] if self.notice_kind == "warning" else C["wash"], padx=10, pady=5)
            notice.pack(fill="x", pady=(5, 8))
            self.paragraph(notice, self.notice_text, "amber" if self.notice_kind == "warning" else "ink")
        (self.sources_page, self.prepare_page, self.filters_page, self.export_page)[self.step]()
        self._navigation()
        if self.busy:
            self._disable_content(self.content)
        def finish_layout():
            self._resize(type("Size", (), {"width": self.canvas.winfo_width()})())
            self.canvas.yview_moveto(0)
        self.after_idle(finish_layout)

    def _navigation(self):
        for index, button in enumerate(self.steps):
            completed = (index == 0 and self.step > 0 and bool(self.demo.sources)) or (index == 1 and self.demo.prepared) or (index == 3 and self.demo.saved)
            prefix = "OK" if completed else str(index + 1)
            button.configure(text=f"{prefix}  {self.STEPS[index]}",
                             bg=C["wash"] if index == self.step else C["surface"],
                             fg=C["blue"] if index == self.step or completed else C["muted"],
                             disabledforeground=C["disabled"],
                             state="normal" if self.can_go(index) else "disabled")
            self.step_marks[index].configure(bg=C["blue"] if index == self.step else C["line"])
        captions = (f"{len(self.demo.sources)} files selected", "Ready" if self.demo.prepared else "Prepare first",
                    f"{len(self.demo.filters)} filters" if self.demo.prepared else "Prepare data first",
                    "Current result saved" if self.demo.saved else "Not exported" if self.demo.prepared else "Prepare data first")
        for label, caption in zip(self.step_states, captions):
            label.configure(text=caption)
        names = ("Review layout", "Continue to filters" if self.demo.prepared else "Check & prepare data",
                 "Review export", "Finish (Close)" if self.demo.saved else "Simulate export")
        allowed = not self.busy and bool(self.demo.sources)
        if self.step == 3 and not self.demo.saved:
            allowed = allowed and bool(self.demo.filtered_rows())
        if self.step == 2:
            allowed = allowed and not self.demo.filter_problem() and bool(self.demo.filtered_rows())
        export_error = ""
        if self.step == 3 and not self.demo.saved and not self.busy:
            try:
                self.demo.validate_export()
            except ValueError as exc:
                export_error = str(exc)
                allowed = False
        self.primary_button.configure(text=names[self.step], state="normal" if allowed else "disabled")
        self.back_button.configure(state="normal" if self.step and not self.busy else "disabled")
        self.close_button.configure(state="disabled" if self.busy else "normal")
        self.close_button.pack_forget()
        if self.step == 3:
            self.close_button.pack(side="right", padx=8)
        self.cancel_button.configure(state="normal" if self.busy and not self.stopping else "disabled")
        hint = ("Choose a file to continue." if not self.demo.sources else
                "Processing; Cancel is available." if self.busy else
                export_error if export_error else
                self.demo.filter_problem() if self.demo.filter_problem() else
                "No matching rows. Adjust filters." if self.step >= 2 and not self.demo.filtered_rows() else
                "Sample data only; no file writes.")
        self.next_hint.configure(text=hint)
        if self.busy:
            self.dock.configure(bg=C["cyan_wash"], pady=8)
            self.progress_caption.grid()
            self.progress.grid()
            self.cancel_button.grid()
        else:
            self.dock.configure(bg=C["surface"], pady=5)
            self.progress_caption.grid_remove()
            self.progress.grid_remove()
            self.cancel_button.grid_remove()
        self.progress_title.configure(bg=self.dock.cget("bg"))
        self.progress_caption.configure(bg=self.dock.cget("bg"))

    def _disable_content(self, widget):
        for child in widget.winfo_children():
            if isinstance(child, (tk.Button, tk.Checkbutton, tk.Entry, tk.Spinbox, ttk.Combobox)):
                child.configure(state="disabled")
            self._disable_content(child)

    def primary(self):
        if self.busy or (self.dialog and self.dialog.winfo_exists()):
            return
        if self.step == 0 and self.demo.sources:
            self.go(1)
        elif self.step == 1:
            if self.demo.prepared:
                self.go(2)
            else:
                self.start_job("prepare")
        elif self.step == 2:
            if not self.demo.filter_problem() and self.demo.filtered_rows():
                self.go(3)
        elif self.step == 3:
            if self.demo.saved:
                self.request_close()
            else:
                try:
                    self.demo.validate_export()
                    self.start_job("export")
                except ValueError as exc:
                    self.announce(str(exc), "warning")
                    self.render()

    def sources_page(self):
        card = self.card(f"Source files / {len(self.demo.sources)} selected")
        actions = tk.Frame(card, bg=C["surface"])
        actions.pack(fill="x")
        self.button(actions, "Try sample folder", self.reset_sources).pack(side="left")
        self.label(actions, "or", SMALL, "muted").pack(side="left", padx=12)
        self.button(actions, "Choose sample files", self.pick_sources).pack(side="left")
        if not self.demo.sources:
            self.paragraph(card, "No files selected. Choose sample files or restore the sample folder.", "amber")
        table = self.table(card, ("File", "Sample sheet", "Layout"), height=3)
        self.source_table = table
        for source in self.demo.sources:
            table.insert("", "end", iid=source, values=(source, f"Report - {source.split('_')[0]} Jan", "Template" if source == self.demo.template else "Extra column" if source.startswith("West") else "Matching"))
        if self.demo.template:
            table.selection_set(self.demo.template)
        row = tk.Frame(card, bg=C["surface"])
        row.pack(fill="x", pady=(8, 0))
        self.template_button = self.button(row, "Use as template", self.set_template)
        self.template_button.pack(side="left")
        self.exclude_button = self.button(row, "Exclude file", self.exclude_source)
        self.exclude_button.pack(side="left", padx=8)
        badge = tk.Frame(card, bg=C["amber_wash"], padx=10, pady=6)
        badge.pack(fill="x", pady=(10, 0))
        star = tk.Canvas(badge, width=22, height=22, bg=C["amber_wash"], highlightthickness=0)
        points = []
        for index in range(10):
            radius = 10 if index % 2 == 0 else 4.5
            angle = index * math.pi / 5 - math.pi / 2
            points.extend((11 + radius * math.cos(angle), 11 + radius * math.sin(angle)))
        star.create_polygon(points, fill=C["star"], outline=C["amber"])
        star.pack(side="left")
        self.label(badge, f"Template: {self.demo.template or 'Choose a file'}", BOLD, "amber").pack(side="left", padx=8)
        self.source_summary = self.paragraph(card, "Select a file to see its sample details. Enter sets the template.")
        table.bind("<<TreeviewSelect>>", self.source_selection_changed)
        table.bind("<Return>", lambda event: self.set_template() if not self.busy else None)
        body, self.source_preview_button = self.disclosure(card, "Selected file preview", "source_preview_open")
        self.source_preview_table = self.table(body, self.demo.columns(), height=3) if self.source_preview_open else None
        self.source_selection_changed()

    def source_selection_changed(self, event=None):
        selection = self.source_table.selection()
        for button in (self.template_button, self.exclude_button):
            button.configure(state="normal" if selection and not self.busy else "disabled")
        if not selection:
            self.source_summary.configure(text="No file selected. Choose a row to set a template or exclude it.")
            return
        source = selection[0]
        self.source_summary.configure(text=f"Selected: {source} | 6 sample rows | Template aligns columns by name.")
        if self.source_preview_table:
            table = self.source_preview_table
            table.delete(*table.get_children())
            rows = [row for row in self.demo.rows() if row["Source file"] == source][:3]
            for row in rows:
                table.insert("", "end", values=tuple(row[column] for column in self.demo.columns()))

    def reset_sources(self):
        if self.busy:
            return
        self.demo.select_sources(SAMPLE_FILES)
        self.filter_undo = None
        self.announce("Three sample files selected. Choose a template below.")
        self.render()

    def pick_sources(self):
        dialog = self.new_dialog("Choose sample files")
        self.label(dialog, "Pick any files. No Ctrl key needed.", SECTION).pack(anchor="w", pady=12)
        vars_ = {name: tk.BooleanVar(dialog, value=name in self.demo.sources) for name in SAMPLE_FILES}
        for name, var in vars_.items():
            tk.Checkbutton(dialog, text=name, variable=var, bg=C["surface"], selectcolor=C["surface"], font=BODY).pack(anchor="w", pady=6)
        def apply():
            self.demo.select_sources(name for name, var in vars_.items() if var.get())
            self.filter_undo = None
            dialog.destroy()
            self.announce("Selection changed. Check & Prepare must run again.", "warning")
            self.render()
        self.button(dialog, "Use selected files", apply, True).pack(anchor="e", pady=14)

    def set_template(self):
        if self.busy:
            return
        selection = self.source_table.selection()
        if selection:
            self.demo.template = selection[0]
            self.filter_undo = None
            self.demo.invalidate()
            self.announce("Template updated. Previous preparation is no longer valid.", "warning")
            self.render()

    def exclude_source(self):
        if self.busy:
            return
        selected = set(self.source_table.selection())
        self.demo.select_sources(source for source in self.demo.sources if source not in selected)
        self.filter_undo = None
        self.announce("Selected sample file excluded. You can restore it with Try sample folder.")
        self.render()

    def change_setting(self, key, value):
        if self.busy:
            return
        setattr(self.demo, key, value)
        self.filter_undo = None
        self.demo.invalidate()
        self.announce("Settings changed. Check & Prepare must run again before export.", "warning")
        self.render()

    def prepare_page(self):
        card = self.card("Data layout")
        self.paragraph(card, f"Reference: {self.demo.template or 'No template selected'} | Example columns: Customer ID, Region, Status, Amount")
        self.check(card, "Different sheet names, same data layout", self.demo.different_sheets,
                   lambda value: self.change_setting("different_sheets", value))
        self.paragraph(card, "Match the layout rather than a dated worksheet name. Preview only; no workbook is opened.")
        self.check(card, "Keep extra columns at the end", self.demo.allow_extra,
                   lambda value: self.change_setting("allow_extra", value))
        self.paragraph(card, "West_Jan has an extra Team column. Off: discard that column, not the file.")
        self.layout_check = self.check(card, "Header is not on row 1, or footer rows must be ignored", self.demo.fix_layout,
                                       lambda value: self.change_setting("fix_layout", value))
        self.layout_fields = tk.Frame(card, bg=C["wash"], padx=10, pady=8)
        if self.demo.fix_layout:
            self.layout_fields.pack(fill="x", pady=6)
            for title, key, minimum in (("Header row", "header_row", 1), ("Footer rows to ignore", "footer_rows", 0)):
                row = tk.Frame(self.layout_fields, bg=C["wash"])
                row.pack(fill="x", pady=3)
                self.label(row, title).pack(side="left")
                var = tk.IntVar(row, value=getattr(self.demo, key))
                spin = tk.Spinbox(row, from_=minimum, to=100, width=6, textvariable=var, state="readonly",
                                  command=lambda key=key, var=var: self.change_setting(key, var.get()), font=BODY)
                spin.pack(side="right")
            self.paragraph(self.layout_fields, "Example: two title rows above your header means Header row = 3.")

        if self.demo.prepared:
            card = self.card("Preparation summary")
            self.paragraph(card, f"{len(self.demo.sources)} sample files ready | {len(self.demo.rows())} rows | {len(self.demo.columns())} columns", "green")
            if self.demo.allow_extra and SAMPLE_FILES[2] in self.demo.sources:
                self.paragraph(card, "Team was appended. Other files have blank Team values.", "amber")
        card = self.card("Processing options")
        memory = "Optimized memory" if self.demo.optimize_memory else "Original storage"
        read = "Parallel reads" if self.demo.parallel else "Sequential reads"
        quality = "Extra checks on" if self.demo.quality_checks else "Extra checks off"
        self.paragraph(card, f"{memory} | {read} | {quality}")
        self.performance_body, self.performance_button = self.disclosure(card, "Advanced performance options", "performance_open")
        body = self.performance_body
        self.button(body, "Use recommended settings", self.recommended_settings).pack(anchor="w", pady=(0, 5))
        self.check(body, "Optimize memory (recommended)", self.demo.optimize_memory,
                   lambda value: self.change_setting("optimize_memory", value))
        self.paragraph(body, "Smaller storage only when values are preserved. Settings are simulated here.")
        self.check(body, "Read files in parallel", self.demo.parallel, lambda value: self.change_setting("parallel", value))
        self.paragraph(body, "May reduce waiting, but needs more memory. Sequential is the safer starting point.")
        self.check(body, "Include deeper data-quality checks", self.demo.quality_checks,
                   lambda value: self.change_setting("quality_checks", value))
        self.paragraph(body, "Blank/duplicate-row checks cost extra work. No real scan runs in this preview.")

    def recommended_settings(self):
        changed = not self.demo.optimize_memory or self.demo.parallel or self.demo.quality_checks
        self.demo.optimize_memory, self.demo.parallel, self.demo.quality_checks = True, False, False
        if changed:
            self.filter_undo = None
            self.demo.invalidate()
        self.announce("Recommended settings applied." + (" Prepare data again to use them." if changed else ""))
        self.render()

    def filters_page(self):
        self.filter_workspace = ResponsiveWorkspace(self.content)
        self.filter_workspace.pack(fill="x")
        card = self.card(f"Filters / {len(self.demo.filters)} active", self.filter_workspace.left)
        self.paragraph(card, f"{len(self.demo.filtered_rows())} of {len(self.demo.rows())} sample rows match. No file reload.")
        row = tk.Frame(card, bg=C["surface"])
        row.pack(fill="x", pady=8)
        self.add_filter_button = self.button(row, "+ Add filter", self.filter_dialog)
        self.add_filter_button.pack(side="left")
        self.button(row, "Clear", self.clear_filters).pack(side="left", padx=5)
        self.undo_button = self.button(row, "Undo", self.undo_filter_change)
        self.undo_button.pack(side="left")
        self.undo_button.configure(state="normal" if self.filter_undo is not None else "disabled")
        if not self.demo.filters:
            self.paragraph(card, "No filters yet. Export all sample rows, or choose Branch and search Wa to try bulk selection.")
        for index, item in enumerate(self.demo.filters):
            strip = tk.Frame(card, bg=C["wash"], padx=10, pady=6)
            strip.pack(fill="x", pady=4)
            actions = tk.Frame(strip, bg=C["wash"])
            actions.pack(side="right")
            self.button(actions, "Edit", lambda index=index: self.filter_dialog(index)).pack(side="left")
            self.button(actions, "Remove", lambda index=index: self.remove_filter(index)).pack(side="left", padx=(6, 0))
            self.paragraph(strip, item.description(), "ink")
        if self.demo.filter_problem():
            self.paragraph(card, self.demo.filter_problem(), "amber")
        if not self.demo.filtered_rows():
            self.paragraph(card, "Nothing matches all filters. Edit or remove a filter before export.", "amber")
        self.paragraph(card, "Ctrl+F opens value search. All active filters must match.")
        self.preview(self.card("Result preview", self.filter_workspace.right))

    def clear_filters(self):
        if self.demo.filters:
            self.filter_undo = list(self.demo.filters)
        self.demo.filters.clear()
        self.announce("Filters cleared. Prepared sample data was kept.")
        self.render()

    def remove_filter(self, index):
        self.filter_undo = list(self.demo.filters)
        self.demo.filters.pop(index)
        self.announce("Filter removed. Prepared sample data was kept.")
        self.render()

    def undo_filter_change(self):
        if self.filter_undo is None or self.busy:
            return
        self.demo.filters = self.filter_undo
        self.filter_undo = None
        self.announce("Last filter change undone. Prepared data was kept.")
        self.render()

    def new_dialog(self, title):
        dialog = tk.Toplevel(self, bg=C["surface"], padx=18, pady=12)
        dialog.title(title)
        dialog.transient(self)
        dialog.geometry("480x460")
        dialog.minsize(420, 400)
        dialog.grab_set()
        dialog.bind("<Escape>", lambda event: dialog.destroy())
        self.dialog = dialog
        return dialog

    def filter_dialog(self, index=None):
        if self.busy or (self.dialog and self.dialog.winfo_exists()):
            return
        item = self.demo.filters[index] if index is not None else None
        dialog = self.new_dialog("Edit filter" if item else "Add filter")
        dialog.geometry("560x650")
        dialog.minsize(420, 500)
        self.label(dialog, "Choose values to include or exclude", SECTION).pack(anchor="w", pady=(4, 10))
        sample_rows = self.demo.rows()
        columns = self.demo.columns()
        initial_column = item.column if item and item.column in columns else "Region"
        column = tk.StringVar(dialog, value=initial_column)
        fields = tk.Frame(dialog, bg=C["surface"])
        fields.pack(fill="x", pady=(0, 8))
        fields.grid_columnconfigure(0, weight=1, uniform="fields")
        fields.grid_columnconfigure(1, weight=1, uniform="fields")
        self.label(fields, "Column", SMALL, "muted").grid(row=0, column=0, sticky="w")
        self.label(fields, "Action", SMALL, "muted").grid(row=0, column=1, sticky="w", padx=(8, 0))
        combo = ttk.Combobox(fields, textvariable=column, values=columns, state="readonly", style="Proto.TCombobox", width=12)
        combo.grid(row=1, column=0, sticky="ew")
        operations = {"Include selected values": "is one of", "Exclude selected values": "is not one of", "Text contains": "contains"}
        initial_operation = next((label for label, value in operations.items() if item and value == item.operator), "Include selected values")
        operator = tk.StringVar(dialog, value=initial_operation)
        mode = ttk.Combobox(fields, textvariable=operator, values=tuple(operations), state="readonly", style="Proto.TCombobox", width=12)
        mode.grid(row=1, column=1, sticky="ew", padx=(8, 0))
        footer = tk.Frame(dialog, bg=C["surface"])
        footer.pack(side="bottom", fill="x", pady=(10, 0))
        error = self.label(dialog, "", SMALL, "amber")
        error.pack(side="bottom", fill="x")
        self.filter_result_count = self.label(dialog, "", SMALL, "blue")
        self.filter_result_count.pack(side="bottom", fill="x", pady=(5, 0))
        area = tk.Frame(dialog, bg=C["surface"])
        area.pack(fill="both", expand=True)
        selections, searches = {}, {}
        current_picker = None
        current_column = None
        term = tk.StringVar(dialog, value=item.values[0] if item and item.operator == "contains" else "")
        def update_count(*args):
            op = operations[operator.get()]
            values = (term.get().strip(),) if op == "contains" else selections.get(column.get(), ValueSelection(())).result()
            if not values or (op == "contains" and not values[0]):
                self.filter_result_count.configure(text="Choose values to preview the result.")
                return
            candidate = Filter(column.get(), op, values)
            filters = list(self.demo.filters)
            if index is None:
                filters.append(candidate)
            else:
                filters[index] = candidate
            count = sum(all(item.matches(row) for item in filters) for row in sample_rows)
            self.filter_result_count.configure(text=f"With this filter: {count} of {len(sample_rows)} sample rows match.")
        def populate(*args):
            nonlocal current_picker, current_column
            if current_picker is not None:
                searches[current_column] = (current_picker.search_var.get(), current_picker.match_var.get())
            area.unbind("<Configure>")
            for child in area.winfo_children():
                child.destroy()
            current_picker = None
            error.configure(text="")
            if operations[operator.get()] == "contains":
                self.label(area, "Text to find (case-insensitive)").pack(anchor="w", pady=6)
                tk.Entry(area, textvariable=term, font=BODY, relief="solid", bd=1).pack(fill="x")
            else:
                current_column = column.get()
                if current_column not in selections:
                    saved_values = item.values if item and item.column == current_column and item.operator != "contains" else ()
                    selections[current_column] = ValueSelection((str(row[current_column]) for row in sample_rows), saved_values)
                action = "excluded" if operations[operator.get()] == "is not one of" else "included"
                help_label = self.label(area, f"Checked values will be {action}. Bulk actions affect all search matches.", SMALL,
                                        "muted", wraplength=500)
                help_label.pack(fill="x", pady=(0, 4))
                area.bind("<Configure>", lambda event, label=help_label: label.configure(wraplength=max(200, event.width - 10)))
                current_picker = CategoryPicker(area, selections[current_column], self.button, on_change=update_count)
                current_picker.pack(fill="both", expand=True)
                if current_column in searches:
                    query, match = searches[current_column]
                    current_picker.match_var.set(match)
                    current_picker.search_var.set(query)
                    current_picker.refresh()
                current_picker.search_entry.focus_set()
            self.filter_picker = current_picker
            update_count()
        combo.bind("<<ComboboxSelected>>", populate)
        mode.bind("<<ComboboxSelected>>", populate)
        populate()
        def apply():
            op = operations[operator.get()]
            values = (term.get().strip(),) if op == "contains" else selections[column.get()].result()
            if not values or (op == "contains" and not values[0]):
                error.configure(text="Choose at least one value or enter text.")
                return
            new = Filter(column.get(), op, values)
            self.filter_undo = list(self.demo.filters)
            if index is None:
                self.demo.filters.append(new)
            else:
                self.demo.filters[index] = new
            dialog.destroy()
            self.announce("Filter applied to prepared sample data. No reload needed.")
            self.render()
        self.button(footer, "Cancel", dialog.destroy).pack(side="left")
        self.filter_apply_button = self.button(footer, "Apply filter", apply, True)
        self.filter_apply_button.pack(side="right")
        self.filter_apply = apply
        self.filter_column = column
        self.filter_column_combo = combo
        self.filter_operator = operator
        self.filter_operator_combo = mode
        self.filter_term = term
        term.trace_add("write", update_count)
        dialog.bind("<Control-Return>", lambda event: apply())
        def focus_search(event):
            if current_picker:
                current_picker.search_entry.focus_set()
            return "break"
        dialog.bind("<Control-f>", focus_search)

    def table(self, parent, columns, height=5):
        shell = tk.Frame(parent, bg=C["surface"])
        shell.pack(fill="both", expand=True, pady=(6, 0))
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(0, weight=1)
        table = ttk.Treeview(shell, columns=columns, show="headings", height=height,
                             style="Proto.Treeview", selectmode="browse")
        for column in columns:
            table.heading(column, text=column)
            table.column(column, width=145, minwidth=110, stretch=True)
        table.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(shell, command=table.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(shell, orient="horizontal", command=table.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        table.tag_configure("stripe", background=C["stripe"])
        return table

    def preview(self, parent):
        columns = self.demo.columns()
        rows = self.demo.filtered_rows()
        toolbar = tk.Frame(parent, bg=C["surface"])
        toolbar.pack(fill="x")
        self.label(toolbar, f"{len(rows)} matching rows", SMALL, "muted").pack(side="left")
        limit = tk.StringVar(parent, value=str(self.preview_limit))
        count = ttk.Combobox(toolbar, textvariable=limit, values=("5", "10", "25"), width=4,
                             state="readonly", style="Proto.TCombobox")
        count.pack(side="right", padx=(6, 0))
        self.label(toolbar, "Rows", SMALL, "muted").pack(side="right")
        def resize_preview(event):
            self.preview_limit = int(limit.get())
            self.render()
        count.bind("<<ComboboxSelected>>", resize_preview)
        table = self.table(parent, columns, 4)
        table.configure(selectmode="extended")
        for index, row in enumerate(rows[:self.preview_limit]):
            table.insert("", "end", values=tuple(row[col] for col in columns), tags=("stripe",) if index % 2 else ())
        self.copy_button = self.button(parent, "Copy selected rows", lambda: self.copy_preview(table))
        self.copy_button.pack(anchor="w", pady=(5, 0))
        self.copy_button.configure(state="disabled")
        table.bind("<<TreeviewSelect>>", lambda event: self.copy_button.configure(state="normal" if table.selection() and not self.busy else "disabled"))
        table.bind("<Control-c>", lambda event: self.copy_preview(table))
        self.paragraph(parent, "Sample preview only. Scroll for all columns; Ctrl+C copies selected rows with headers.")
        self.preview_table = table
        self.preview_count_combo = count

    def copy_preview(self, table):
        selected = table.selection()
        if not selected:
            return "break"
        output = io.StringIO()
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(table["columns"])
        writer.writerows(table.item(iid, "values") for iid in selected)
        self.clipboard_clear()
        self.clipboard_append(output.getvalue())
        self.progress_title.configure(text=f"Copied {len(selected)} sample rows with column names.")
        return "break"

    def export_page(self):
        if self.demo.saved:
            card = self.card("Sample export complete")
            self.paragraph(card, f"{self.demo.filename}  /  {len(self.demo.filtered_rows())} sample rows", "green")
            self.paragraph(card, "This was a simulation. No output or audit file was created.")
            row = tk.Frame(card, bg=C["surface"])
            row.pack(fill="x", pady=8)
            self.button(row, "Change filters", self.export_again).pack(side="left")
            self.button(row, "New file, same filters", self.new_export).pack(side="left", padx=8)
        self.export_workspace = ResponsiveWorkspace(self.content)
        self.export_workspace.pack(fill="x")
        card = self.card("Output settings", self.export_workspace.left)
        self.label(card, "Format", SMALL, "muted").pack(anchor="w", pady=(0, 3))
        self.format_var = tk.StringVar(self, value=self.demo.output_format)
        self.format_combo = ttk.Combobox(card, textvariable=self.format_var, values=FORMATS,
                                         state="readonly", style="Proto.TCombobox", font=BODY)
        self.format_combo.pack(fill="x")
        self.format_combo.bind("<<ComboboxSelected>>", self.change_format)
        self.protected_picker = tk.Frame(card, bg=C["wash"], padx=12, pady=10)
        if self.demo.output_format == "CSV-Unique text":
            self.protected_picker.pack(fill="x", pady=(8, 0))
            self.label(self.protected_picker, "Which columns must stay as text?", BOLD).pack(anchor="w")
            self.paragraph(self.protected_picker, "For IDs and leading zeros. Pick at least one column. The current engine uses apostrophe wrapping; test it in your downstream tool.")
            grid = tk.Frame(self.protected_picker, bg=C["wash"])
            grid.pack(fill="x")
            for position in (0, 1):
                grid.grid_columnconfigure(position, weight=1, uniform="columns")
            for index, column in enumerate(self.demo.columns()):
                value = tk.BooleanVar(grid, value=column in self.demo.protected)
                checkbox = tk.Checkbutton(grid, text=column, variable=value, bg=C["wash"],
                                           fg=C["ink"], selectcolor=C["surface"], font=BODY, anchor="w",
                                           command=lambda column=column, var=value: self.protect_column(column, var.get()))
                checkbox.grid(row=index // 2, column=index % 2, sticky="ew", pady=2)
        else:
            self.paragraph(card, "Need to preserve IDs as text? Choose CSV-Unique text to pick columns here.")
        self.label(card, "File name", SMALL, "muted").pack(anchor="w", pady=(10, 3))
        self.filename_var = tk.StringVar(self, value=self.demo.filename)
        self.filename_entry = tk.Entry(card, textvariable=self.filename_var, font=BODY,
                                      relief="solid", bd=1, bg=C["surface"], fg=C["ink"])
        self.filename_entry.pack(fill="x", ipady=7)
        self.filename_var.trace_add("write", self.filename_changed)
        self.paragraph(card, "Destination: Sample exports (not a real folder). Repeat exports suggest a new name.")
        self.saved_label = self.paragraph(card, "Current result saved (simulation)." if self.demo.saved else "Not exported yet - keep this window open until you finish.", "green" if self.demo.saved else "amber")
        self.preview(self.card("Result preview", self.export_workspace.right))
        if self.demo.history:
            history = self.card("Recent sample exports", self.export_workspace.right)
            for entry in self.demo.history[:5]:
                self.paragraph(history, f"{entry['name']} | {entry['format']} | {entry['rows']} sample rows")

    def change_format(self, event=None):
        self.demo.choose_format(self.format_var.get())
        self.announce("Format updated. Text-column controls appear directly below the format when needed.")
        self.render()

    def protect_column(self, column, checked):
        self.demo.protected.add(column) if checked else self.demo.protected.discard(column)
        self._navigation()
        self.saved_label.configure(text="Settings changed - simulate a new export.", fg=C["amber"])

    def filename_changed(self, *args):
        self.demo.filename = self.filename_var.get()
        self._navigation()
        if hasattr(self, "saved_label") and self.saved_label.winfo_exists():
            self.saved_label.configure(text="Current result saved (simulation)." if self.demo.saved else "Not exported with these settings yet.", fg=C["green"] if self.demo.saved else C["amber"])

    def export_again(self):
        self.demo.next_filename()
        self.announce("Prepared data kept. Change filters and export another result without reloading.")
        self.go(2)

    def new_export(self):
        self.demo.next_filename()
        self.announce("A new name is ready. Same sample data and filters; no reload.")
        self.render()

    def start_job(self, kind):
        if self.busy or not self.demo.sources:
            return
        self.job, self.busy, self.stopping = kind, True, False
        self.started = time.monotonic()
        self.announce("Demo task running. Settings are locked; Cancel stays available.")
        self.progress.configure(value=0)
        self.render()
        self.tick()

    def tick(self):
        self.timer = None
        if not self.busy:
            return
        elapsed = time.monotonic() - self.started
        duration = 5.0 if self.job == "prepare" else 3.0
        percent = min(100, int(elapsed / duration * 100))
        if self.stopping:
            self.progress_title.configure(text="Stopping safely - waiting for the demo checkpoint")
            return
        phase = "Checking layouts" if percent < 35 else "Combining sample files" if self.job == "prepare" else "Writing sample output"
        if self.job == "export":
            phase = "Simulating export"
        self.progress_title.configure(text=f"{phase}  /  {percent}%")
        file_index = min(len(self.demo.sources) - 1, int(percent / 100 * len(self.demo.sources)))
        detail = f"Output: {self.demo.filename}" if self.job == "export" else f"File {file_index + 1}/{len(self.demo.sources)}: {self.demo.sources[file_index]}"
        self.progress_caption.configure(text=f"Elapsed {elapsed:.0f}s  |  Demo ETA {max(0, duration - elapsed):.0f}s  |  {detail}")
        self.progress.configure(value=percent)
        if percent >= 100:
            self.complete_job()
        else:
            self.timer = self.after(100, self.tick)

    def complete_job(self):
        self.busy = False
        if self.job == "prepare":
            self.demo.prepared = True
            extra = " Team was appended from West_Jan; review it before continuing." if self.demo.allow_extra and SAMPLE_FILES[2] in self.demo.sources else " Continue to filters when ready."
            self.announce(f"Ready: {len(self.demo.sources)} sample files prepared." + extra)
        else:
            try:
                self.demo.mark_exported()
                self.announce("Sample export completed. No real file was written. Try another export using the same data.")
            except ValueError as exc:
                self.announce(str(exc), "warning")
        self.progress_title.configure(text="Demo complete - ready for your next action")
        self.progress_caption.configure(text="Sample data remains in this session. No source reread required.")
        self.render()

    def cancel(self):
        if not self.busy or self.stopping:
            return
        self.stopping = True
        if self.timer:
            self.after_cancel(self.timer)
            self.timer = None
        self.progress_title.configure(text="Stopping safely - waiting for the demo checkpoint")
        self.cancel_button.configure(state="disabled")
        self.timer = self.after(350, self.cancel_done)

    def cancel_done(self):
        self.timer = None
        self.busy, self.stopping = False, False
        self.announce("Demo cancelled. No output was created. You can retry.", "warning")
        self.progress_title.configure(text="Cancelled - ready to retry")
        self.progress_caption.configure(text="Existing sample data and settings were kept.")
        self.render()

    def request_close(self):
        if self.busy:
            self.cancel()
            return
        if self.dialog and self.dialog.winfo_exists():
            self.dialog.lift()
            return
        if not (self.demo.prepared or self.demo.filters) or self.demo.saved:
            self.destroy()
            return
        dialog = self.new_dialog("Leave without exporting?")
        self.label(dialog, "Nothing has been exported", SECTION).pack(anchor="w", pady=12)
        self.paragraph(dialog, "Close this prototype without exporting? Your production files are untouched. Sample session settings will be lost.")
        self.button(dialog, "Keep working", dialog.destroy, True).pack(fill="x", pady=8)
        self.button(dialog, "Close without export", self.destroy).pack(fill="x")

    def destroy(self):
        if self.timer:
            self.after_cancel(self.timer)
            self.timer = None
        super().destroy()
