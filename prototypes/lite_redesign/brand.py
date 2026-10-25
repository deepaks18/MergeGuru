"""Crisp, DPI-friendly MergeGuru branding for the Tk interface."""

import tkinter as tk

from PIL import ImageTk

from mergeguru_brand import render_mark

from .theme import COLORS as C, SMALL, WORDMARK


def blend(start, end, fraction):
    fraction = max(0, min(1, fraction))
    values = []
    for offset in (1, 3, 5):
        left, right = int(start[offset:offset + 2], 16), int(end[offset:offset + 2], 16)
        values.append(round(left + (right - left) * fraction))
    return "#" + "".join(f"{value:02x}" for value in values)


def make_icon(master):
    """Use a large master so Windows can downsample each icon presentation."""
    return ImageTk.PhotoImage(
        render_mark(256, background=C["navy"], supersample=4, rounded_background=True),
        master=master,
    )


def make_header_mark(master, size=46):
    return ImageTk.PhotoImage(render_mark(size, supersample=5), master=master)


class BrandHeader(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=C["navy"], padx=16, pady=6)
        self.grid_columnconfigure(0, weight=1)
        identity = tk.Frame(self, bg=C["navy"])
        identity.grid(row=0, column=0, sticky="w")
        self.mark_image = make_header_mark(self)
        self.mark = tk.Label(
            identity,
            image=self.mark_image,
            width=46,
            height=46,
            bg=C["navy"],
            bd=0,
            highlightthickness=0,
        )
        self.mark.pack(side="left", padx=(0, 10))
        words = tk.Frame(identity, bg=C["navy"])
        words.pack(side="left")
        name = tk.Frame(words, bg=C["navy"])
        name.pack(anchor="w")
        tk.Label(name, text="Merge", font=WORDMARK, bg=C["navy"], fg=C["surface"]).pack(side="left")
        tk.Label(name, text="Guru", font=WORDMARK, bg=C["navy"], fg=C["cyan"]).pack(side="left")
        tk.Label(
            words,
            text="MERGE. VALIDATE. EXPORT.",
            font=("Segoe UI", 8),
            bg=C["navy"],
            fg="#c1d3eb",
        ).pack(anchor="w")
        self.preview_badge = tk.Label(
            self,
            text="LITE PREVIEW / SAMPLE DATA ONLY",
            font=SMALL,
            bg=C["navy"],
            fg=C["surface"],
        )
        self.preview_badge.grid(row=0, column=1, sticky="e", padx=(16, 0))
        self.band = tk.Canvas(self, height=3, bg=C["navy"], highlightthickness=0)
        self.band.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.band.bind("<Configure>", self._draw_band)

    def _draw_band(self, event):
        self.band.delete("all")
        for index in range(64):
            self.band.create_rectangle(
                index * event.width / 64,
                0,
                (index + 1) * event.width / 64 + 1,
                3,
                fill=blend(C["blue"], C["cyan"], index / 63),
                outline="",
            )
