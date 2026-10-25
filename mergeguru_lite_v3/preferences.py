"""Small local preference store. Filters and source names are intentionally excluded."""

from __future__ import annotations

import json
import os
import tempfile


DEFAULTS = {
    "allow_extra": True,
    "different_sheets": True,
    "optimize_memory": True,
    "fast_mode": False,
    "output_format": "Excel",
    "preview_limit": 10,
    "window_geometry": "1060x780",
}


def preference_path():
    root = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(root, "MergeGuru", "lite_v3_preferences.json")


def load_preferences(path=None):
    values = dict(DEFAULTS)
    target = path or preference_path()
    try:
        with open(target, "r", encoding="utf-8") as stream:
            loaded = json.load(stream)
        for key in DEFAULTS:
            if key in loaded and isinstance(loaded[key], type(DEFAULTS[key])):
                values[key] = loaded[key]
    except (OSError, ValueError, TypeError):
        pass
    return values


def save_preferences(values, path=None):
    target = path or preference_path()
    folder = os.path.dirname(target)
    os.makedirs(folder, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".mergeguru-pref-", suffix=".json", dir=folder)
    os.close(descriptor)
    try:
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump({key: values[key] for key in DEFAULTS}, stream, indent=2)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
