#!/usr/bin/env python3
"""Generate anti-aliased MergeGuru masters, icons, and compact splashes."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mergeguru_brand import NAVY, render_brand_lockup, render_mark, render_splash


ASSETS = ROOT / "assets"


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)

    transparent_master = render_mark(1024, supersample=2)
    transparent_master.save(ASSETS / "MergeGuru_Mark_HD.png", optimize=True)
    render_brand_lockup().save(ASSETS / "MergeGuru_Brand_HD.png", optimize=True)

    icon_master = render_mark(1024, background=NAVY, supersample=2, rounded_background=True)
    icon_master.save(ASSETS / "MergeGuru_Lite_v3.png", optimize=True)
    icon_master.save(
        ASSETS / "MergeGuru_Lite_v3.ico",
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )

    render_splash("LITE v3.0").save(ASSETS / "MergeGuru_Lite_v3_splash.png", optimize=True)
    render_splash("LITE v3.1 PREVIEW").save(
        ASSETS / "MergeGuru_Lite_v3_1_splash.png",
        optimize=True,
    )


if __name__ == "__main__":
    main()
