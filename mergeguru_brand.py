"""High-resolution MergeGuru brand rendering shared by UI and build tools."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont


NAVY = (4, 23, 46, 255)
WHITE = (255, 255, 255, 255)
MUTED = (193, 211, 235, 255)
BLUE = (20, 82, 232, 255)
CYAN = (0, 201, 213, 255)

STREAM = (
    (7, 29), (7, 20), (9, 13), (14, 8), (21, 6), (27, 7),
    (42, 17), (46, 22), (48, 29), (48, 73), (44, 78),
    (50, 85), (50, 94), (32, 76), (31, 72), (34, 70),
    (38, 70), (38, 43), (36, 38), (31, 34), (19, 27),
    (15, 26), (11, 27),
)
WING = (
    (7, 33), (11, 30), (15, 30), (26, 36), (26, 60),
    (24, 64), (10, 73), (8, 72), (7, 70),
)


def blend(left, right, fraction):
    fraction = max(0.0, min(1.0, float(fraction)))
    return tuple(round(a + (b - a) * fraction) for a, b in zip(left, right))


def render_mark(size=1024, *, background=None, supersample=4, rounded_background=False):
    """Render an anti-aliased mark from normalized geometry."""
    size = max(16, int(size))
    supersample = max(1, int(supersample))
    work_size = size * supersample
    background_rgba = _rgba(background) if background is not None else (0, 0, 0, 0)
    image = Image.new("RGBA", (work_size, work_size), (0, 0, 0, 0))
    if background is not None:
        draw = ImageDraw.Draw(image)
        if rounded_background:
            radius = round(work_size * 0.20)
            draw.rounded_rectangle(
                (0, 0, work_size - 1, work_size - 1),
                radius=radius,
                fill=background_rgba,
            )
        else:
            draw.rectangle((0, 0, work_size, work_size), fill=background_rgba)

    margin = work_size * 0.08
    mirror = lambda shape: tuple((100 - x, y) for x, y in shape)
    _gradient_polygon(image, _scaled(STREAM, work_size, margin), (20, 82, 232), (0, 156, 232))
    _gradient_polygon(image, _scaled(mirror(STREAM), work_size, margin), (0, 225, 226), (0, 156, 232))
    _gradient_polygon(image, _scaled(WING, work_size, margin), (20, 91, 251), (6, 64, 228))
    _gradient_polygon(image, _scaled(mirror(WING), work_size, margin), (18, 75, 221), (8, 40, 145))
    if supersample > 1:
        image = image.resize((size, size), Image.Resampling.LANCZOS)
    return image


def render_brand_lockup(width=1600, height=400, *, supersample=2):
    """Render a high-resolution horizontal logo lockup on the brand navy."""
    width, height = int(width), int(height)
    factor = max(1, int(supersample))
    work = Image.new("RGBA", (width * factor, height * factor), NAVY)
    draw = ImageDraw.Draw(work)
    scale = work.height / 400
    mark_size = round(300 * scale)
    mark = render_mark(mark_size, supersample=1)
    work.alpha_composite(mark, (round(45 * scale), round(50 * scale)))

    title = _font(round(102 * scale), bold=True)
    tagline = _font(round(30 * scale))
    x, y = round(390 * scale), round(92 * scale)
    draw.text((x, y), "Merge", font=title, fill=WHITE)
    merge_width = draw.textlength("Merge", font=title)
    draw.text((x + merge_width, y), "Guru", font=title, fill=CYAN)
    draw.text((x + 4 * scale, round(238 * scale)), "MERGE.  VALIDATE.  EXPORT.", font=tagline, fill=MUTED)
    if factor > 1:
        work = work.resize((width, height), Image.Resampling.LANCZOS)
    return work


def render_splash(label="LITE v3.1 PREVIEW", width=720, height=360, *, supersample=2):
    """Render the compact splash from a supersampled composition."""
    width, height = int(width), int(height)
    factor = max(1, int(supersample))
    work_width, work_height = width * factor, height * factor
    work = Image.new("RGBA", (work_width, work_height), NAVY)
    draw = ImageDraw.Draw(work)
    scale = work_width / 640

    for y in range(work_height):
        fraction = y / max(1, work_height - 1)
        color = blend((4, 23, 46, 255), (2, 17, 38, 255), fraction)
        draw.line((0, y, work_width, y), fill=color)
    for x in range(work_width):
        color = blend(BLUE, CYAN, x / max(1, work_width - 1))
        draw.line((x, work_height - round(6 * scale), x, work_height - 1), fill=color)

    mark_size = round(180 * scale)
    mark = render_mark(mark_size, supersample=1)
    work.alpha_composite(mark, (round(34 * scale), round(58 * scale)))

    title = _font(round(49 * scale), bold=True)
    small = _font(round(16 * scale))
    badge = _font(round(15 * scale), bold=True)
    title_x, title_y = round(242 * scale), round(78 * scale)
    draw.text((title_x, title_y), "Merge", font=title, fill=WHITE)
    merge_width = draw.textlength("Merge", font=title)
    draw.text((title_x + merge_width, title_y), "Guru", font=title, fill=CYAN)
    draw.text((round(245 * scale), round(143 * scale)), "MERGE.  VALIDATE.  EXPORT.", font=small, fill=MUTED)

    badge_x, badge_y = round(244 * scale), round(184 * scale)
    text_box = draw.textbbox((0, 0), label, font=badge)
    badge_width = max(round(121 * scale), text_box[2] - text_box[0] + round(34 * scale))
    badge_height = round(34 * scale)
    draw.rounded_rectangle(
        (badge_x, badge_y, badge_x + badge_width, badge_y + badge_height),
        radius=round(8 * scale),
        fill=BLUE,
    )
    draw.text(
        (badge_x + round(17 * scale), badge_y + round(6 * scale)),
        label,
        font=badge,
        fill=WHITE,
    )
    draw.text(
        (round(245 * scale), round(239 * scale)),
        "Starting local data workspace...",
        font=small,
        fill=MUTED,
    )
    if factor > 1:
        work = work.resize((width, height), Image.Resampling.LANCZOS)
    return work.convert("RGB")


def _gradient_polygon(image, points, start, end):
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).polygon(points, fill=255)
    gradient = Image.new("RGBA", image.size, (0, 0, 0, 0))
    gradient_draw = ImageDraw.Draw(gradient)
    for y in range(image.height):
        color = blend(start + (255,), end + (255,), y / max(1, image.height - 1))
        gradient_draw.line((0, y, image.width, y), fill=color)
    image.alpha_composite(Image.composite(gradient, Image.new("RGBA", image.size), mask))


def _scaled(points, size, margin):
    usable = size - margin * 2
    return [(margin + x * usable / 100, margin + y * usable / 100) for x, y in points]


def _font(size, bold=False):
    candidates = [
        Path("C:/Windows/Fonts/bahnschrift.ttf") if bold else Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/segoeuib.ttf") if bold else Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def _rgba(value):
    if isinstance(value, str):
        return ImageColor.getrgb(value) + (255,)
    if len(value) == 3:
        return tuple(value) + (255,)
    return tuple(value)
