"""
Rendering: turn placed text into a finished 1920x1080 RGBA TIFF that matches
the reference deck.

This is the only layer that touches the filesystem. It composes the black
left-hand scrim, draws the verse lines and the reference line at the ink tops
layout.py computed, and writes the result. `generate_slides` runs the whole
passage, skipping blank verses so one empty entry cannot abort a batch.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from functools import lru_cache

from PIL import Image

from .fonts import draw_text, load_fonts
from .layout import (
    GRADIENT_PROFILE,
    LEFT_MARGIN,
    SLIDE_HEIGHT,
    SLIDE_WIDTH,
    TEXT_BOX_WIDTH,
    layout_slide,
)
from .text import Verse, format_verses


@lru_cache(maxsize=4)
def make_gradient(width: int = SLIDE_WIDTH, height: int = SLIDE_HEIGHT) -> Image.Image:
    """
    The black left-hand scrim: opaque at the left edge, fully transparent
    by about 60% across. Interpolated from GRADIENT_PROFILE.

    Cached -- it is identical for every slide in a run, and rebuilding it per
    slide dominated generation time.
    """
    row = Image.new("RGBA", (width, 1))
    pixels = row.load()
    assert pixels is not None
    last = len(GRADIENT_PROFILE) - 1
    for x in range(width):
        pos = x / (width - 1) * last          # x mapped onto profile indices
        i = min(int(pos), last)
        j = min(i + 1, last)
        frac = pos - i
        alpha = GRADIENT_PROFILE[i] * (1 - frac) + GRADIENT_PROFILE[j] * frac
        pixels[x, 0] = (0, 0, 0, round(alpha))
    return row.resize((width, height))


def compose_slide(
    verse_text: str, reference: str, max_width: float = TEXT_BOX_WIDTH
) -> Image.Image:
    """
    Build one finished slide as an in-memory RGBA image.

    `verse_text` is expected to have been through format_verses already --
    nothing here does text normalization.
    """
    verse_font, ref_font = load_fonts()
    lines, line_tops, ref_top = layout_slide(
        verse_text, reference, font=verse_font, max_width=max_width
    )

    img = make_gradient().copy()
    for line, top in zip(lines, line_tops):
        draw_text(img, LEFT_MARGIN, top, line, verse_font)
    draw_text(img, LEFT_MARGIN, ref_top, reference, ref_font)
    return img


def render_slide(
    verse_text: str, reference: str, output_path: str, max_width: float = TEXT_BOX_WIDTH
) -> str:
    """Compose a slide and write it to `output_path` as an RGBA TIFF."""
    compose_slide(verse_text, reference, max_width=max_width).save(output_path, "TIFF")
    return output_path


_REF_PARTS_RE = re.compile(r"^(.*?)(\d+):(\d+)")


def slide_filename(reference: str, index: int) -> str:
    """
    Sortable, self-describing filename derived from the reference.

    "John 17:1 ESV" -> "John_17_001.tif". Falls back to the sequence number
    if the reference does not parse.
    """
    match = _REF_PARTS_RE.match(reference)
    if not match:
        return f"verse_{index:03d}.tif"
    book = match.group(1).strip().replace(" ", "_")
    return f"{book}_{match.group(2)}_{int(match.group(3)):03d}.tif"


def generate_slides(
    verses: Iterable[Verse], output_dir: str = "./slides", formatted: bool = False
) -> list[str]:
    """
    Render a whole passage.

    Verses with no renderable text are skipped rather than raising, so one
    blank entry in a passage cannot abort the batch. Compare len(result) with
    len(verses) to detect skips.

    Args:
        verses: list of (verse_text, reference) pairs, in order.
        output_dir: created if missing.
        formatted: set True if `verses` has already been through
            format_verses (the quote carry rule is order-dependent, so it must
            run over the full passage exactly once).

    Returns the list of written paths.
    """
    prepared = list(verses) if formatted else format_verses(verses)

    os.makedirs(output_dir, exist_ok=True)
    paths: list[str] = []
    for index, (text, ref) in enumerate(prepared, 1):
        if not text.strip():
            continue
        path = os.path.join(output_dir, slide_filename(ref, index))
        render_slide(text, ref, path)
        paths.append(path)
    return paths
