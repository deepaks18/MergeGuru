"""Two-panel workspace that stacks without rebuilding its controls."""

import tkinter as tk

from .theme import COLORS as C


class ResponsiveWorkspace(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=C["paper"])
        self.left = tk.Frame(self, bg=C["paper"])
        self.right = tk.Frame(self, bg=C["paper"])
        self.wide = None
        self.bind("<Configure>", self.resize)

    def resize(self, event):
        wide = event.width >= 900
        if wide == self.wide:
            return
        self.wide = wide
        self.grid_columnconfigure(0, weight=4 if wide else 1, uniform="panels" if wide else "")
        self.grid_columnconfigure(1, weight=6 if wide else 0, uniform="panels" if wide else "")
        self.left.grid(row=0, column=0, sticky="new", padx=(0, 6) if wide else 0)
        self.right.grid(row=0 if wide else 1, column=1 if wide else 0,
                        sticky="new", padx=(6, 0) if wide else 0)
