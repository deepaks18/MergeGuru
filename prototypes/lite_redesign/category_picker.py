"""Searchable, paged category picker. Bulk actions include all search matches."""

import tkinter as tk
from tkinter import ttk

from .theme import BODY, COLORS as C, SMALL


class CategoryPicker(tk.Frame):
    PAGE_SIZE = 250

    def __init__(self, parent, selection, button_factory, on_change=None):
        super().__init__(parent, bg=C["surface"])
        self.selection = selection
        self.on_change = on_change
        self.search_var = tk.StringVar(self)
        self.match_var = tk.StringVar(self, value="Starts with")
        self.pending = None
        self.limit = self.PAGE_SIZE
        self.visible = ()
        tk.Label(self, text="Search values (for example: Wa)", font=SMALL,
                 fg=C["muted"], bg=C["surface"], anchor="w").pack(fill="x", pady=(4, 3))
        row = tk.Frame(self, bg=C["surface"])
        row.pack(fill="x")
        self.search_entry = tk.Entry(row, textvariable=self.search_var, font=BODY,
                                     bg=C["surface"], fg=C["ink"], relief="solid", bd=1,
                                     highlightcolor=C["blue"], highlightthickness=1)
        self.search_entry.pack(side="left", fill="x", expand=True, ipady=6)
        self.match_combo = ttk.Combobox(row, textvariable=self.match_var, values=("Starts with", "Contains"),
                                        state="readonly", style="Proto.TCombobox", width=13)
        self.match_combo.pack(side="right", padx=(8, 0))
        actions = tk.Frame(self, bg=C["surface"])
        actions.pack(fill="x", pady=(7, 3))
        self.select_button = button_factory(actions, "Select matches", self.select_visible)
        self.select_button.pack(side="left")
        self.clear_button = button_factory(actions, "Clear matches", self.clear_visible)
        self.clear_button.pack(side="left", padx=5)
        self.invert_button = button_factory(actions, "Invert", self.invert_visible)
        self.invert_button.pack(side="left")
        self.count = tk.Label(self, font=SMALL, fg=C["muted"], bg=C["surface"], anchor="w",
                              justify="left", wraplength=440)
        self.count.pack(fill="x", pady=3)

        bottom = tk.Frame(self, bg=C["surface"])
        bottom.pack(side="bottom", fill="x", pady=(6, 0))
        self.summary = tk.Label(bottom, font=SMALL, fg=C["ink"], bg=C["surface"],
                                anchor="w", justify="left", wraplength=440)
        self.summary.pack(fill="x")
        self.more_button = button_factory(bottom, "Show more values", self.show_more)

        shell = tk.Frame(self, bg=C["surface"])
        shell.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(shell, columns=("pick", "value"), show="headings",
                                 style="Proto.Treeview", selectmode="browse", height=5)
        self.tree.heading("pick", text="Pick")
        self.tree.heading("value", text="Value (click or press Space)")
        self.tree.column("pick", width=48, minwidth=48, stretch=False, anchor="center")
        self.tree.column("value", width=240, minwidth=120, stretch=True)
        scrollbar = ttk.Scrollbar(shell, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        self.tree.tag_configure("stripe", background=C["stripe"])
        self.tree.bind("<Button-1>", self.click_value)
        self.tree.bind("<space>", self.space_value)
        self.bind("<Configure>", self.resize)
        self.search_var.trace_add("write", self.schedule_refresh)
        self.match_combo.bind("<<ComboboxSelected>>", self.schedule_refresh)
        self.search_entry.bind("<Return>", self.focus_matches)
        self.search_entry.bind("<Down>", self.focus_matches)
        self.refresh()

    def resize(self, event):
        for label in (self.summary, self.count):
            label.configure(wraplength=max(200, event.width - 10))

    def schedule_refresh(self, *args):
        if self.pending:
            self.after_cancel(self.pending)
        self.pending = self.after(120, self.refresh)

    def refresh(self):
        if self.pending:
            self.after_cancel(self.pending)
            self.pending = None
        self.limit = self.PAGE_SIZE
        self.visible = self.selection.matches(self.search_var.get(), self.match_var.get())
        self.draw_values()

    def draw_values(self):
        self.tree.delete(*self.tree.get_children())
        for index, value in enumerate(self.visible[:self.limit]):
            self.tree.insert("", "end", iid=str(index),
                             values=("\u2611" if value in self.selection.selected else "\u2610", value or "(Blank)"),
                             tags=("stripe",) if index % 2 else ())
        self.update_summary()
        if len(self.visible) > self.limit:
            self.more_button.pack(anchor="w", pady=(4, 0))
        else:
            self.more_button.pack_forget()

    def update_summary(self):
        visible_set = set(self.visible)
        count = len(self.selection.selected)
        hidden = len(self.selection.selected - visible_set)
        shown = min(self.limit, len(self.visible))
        self.count.configure(text=f"{len(self.visible):,} matches | {shown:,} shown | {count:,} selected ({hidden:,} hidden)")
        preview = ", ".join(value or "(Blank)" for value in self.selection.result()[:3])[:100]
        extra = f" + {count - 3} more" if count > 3 else ""
        self.summary.configure(text=f"Selected: {preview}{extra}" if count else "No values selected. Search does not change your selections.")
        for button in (self.select_button, self.clear_button, self.invert_button):
            button.configure(state="normal" if self.visible else "disabled")
        if not self.visible:
            self.summary.configure(text=f"No matches. Change the search; {count} existing selections are still kept.")
        if self.on_change:
            self.on_change()

    def focus_matches(self, event=None):
        if self.pending:
            self.refresh()
        children = self.tree.get_children()
        if children:
            self.tree.focus_set()
            self.tree.focus(children[0])
            self.tree.selection_set(children[0])
        return "break"

    def select_visible(self):
        # All matches, including not-yet-rendered pages; hidden search values stay intact.
        if self.pending:
            self.refresh()
        self.selection.select(self.visible)
        self.draw_values()

    def clear_visible(self):
        if self.pending:
            self.refresh()
        self.selection.clear(self.visible)
        self.draw_values()

    def invert_visible(self):
        if self.pending:
            self.refresh()
        self.selection.invert(self.visible)
        self.draw_values()

    def show_more(self):
        self.limit += self.PAGE_SIZE
        self.draw_values()

    def click_value(self, event):
        if self.pending:
            self.refresh()
            return "break"
        if self.tree.identify_region(event.x, event.y) not in ("cell", "tree"):
            return
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.focus(iid)
            self.tree.selection_set(iid)
            self.toggle_iid(iid)
        return "break"

    def space_value(self, event):
        if self.pending:
            self.refresh()
            return "break"
        iid = self.tree.focus()
        if iid:
            self.toggle_iid(iid)
        return "break"

    def toggle_iid(self, iid):
        value = self.visible[int(iid)]
        self.selection.toggle(value)
        self.tree.item(iid, values=("\u2611" if value in self.selection.selected else "\u2610", value or "(Blank)"))
        self.update_summary()

    def destroy(self):
        if self.pending:
            self.after_cancel(self.pending)
            self.pending = None
        super().destroy()
