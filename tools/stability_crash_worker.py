"""Fixture worker paused mid-write so its parent can test forced interruption."""

import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mergeguru_engine as engine


def pause_after_chunk(*args):
    Path(sys.argv[2]).write_text("chunk written", encoding="utf-8")
    while True:
        time.sleep(1)


if __name__ == "__main__":
    engine.save_dataframe(pd.DataFrame({"id": range(20_001)}), sys.argv[1], "CSV",
                          progress_callback=pause_after_chunk)
