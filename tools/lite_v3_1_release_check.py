#!/usr/bin/env python3
"""Complete regression gate for the MergeGuru Lite v3.1 preview."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.lite_v3_beta_check import *  # noqa: F401,F403


if __name__ == "__main__":
    unittest.main(verbosity=2)
