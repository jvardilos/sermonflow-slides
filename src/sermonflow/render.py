"""
Rendering: turn placed text into a finished 1920x1080 RGBA TIFF that matches
the reference deck.

This is the only layer that touches the filesystem, and since layouts/ arrived
it is also the only layer that is layout-agnostic. Everything here works on a
`Placed` -- a slide reduced to draw ops at ink coordinates -- so it composes a
verse slide, a rolling point deck, or a slide type nobody has written yet
without knowing the difference. The scrim is the one piece of artwork it owns.

`generate_slides` and `generate_points` run a whole passage or a whole list of
points, skipping blank entries so one empty item cannot abort a batch.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Sequence
from functools import lru_cache

from PIL import Image

from .fonts import draw_text, load_face
from .layouts import (
    DEFAULT_POINT_STYLE,
    GRADIENT_PROFILE,
    SLIDE_HEIGHT,
    SLIDE_WIDTH,
    TEXT_BOX_WIDTH,
    EmptyVerseError,
    Placed,
    get_point_style,
    plan_verse,
    slide_stem,
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


# ---------------------------------------------------------------------------
# Layout-agnostic composition
# ---------------------------------------------------------------------------


def compose(placed: Placed) -> Image.Image:
    """Draw one planned slide onto the scrim and return the image."""
    img = make_gradient().copy()
    for op in placed.ops:
        draw_text(img, op.left, op.ink_top, op.text, load_face(op.weight))
    return img


def render(placed: Placed, output_path: str) -> str:
    """Compose a planned slide and write it to `output_path` as an RGBA TIFF."""
    compose(placed).save(output_path, "TIFF")
    return output_path


def render_deck(slides: Sequence[Placed], output_dir: str = "./slides") -> list[str]:
    """
    Write a planned deck to `output_dir` (created if missing), in order.

    Files are named from each slide's stem, which the layout chose, so verse
    decks stay in verse order and point decks in reveal order in any file
    browser or import dialog.
    """
    os.makedirs(output_dir, exist_ok=True)
    return [
        render(placed, os.path.join(output_dir, f"{placed.stem}.tif"))
        for placed in slides
    ]


# ---------------------------------------------------------------------------
# Verse slides
# ---------------------------------------------------------------------------


def compose_slide(
    verse_text: str, reference: str, max_width: float = TEXT_BOX_WIDTH
) -> Image.Image:
    """
    Build one finished verse slide as an in-memory RGBA image.

    `verse_text` is expected to have been through format_verses already --
    nothing here does text normalization.
    """
    return compose(plan_verse(verse_text, reference, max_width=max_width))


def render_slide(
    verse_text: str, reference: str, output_path: str, max_width: float = TEXT_BOX_WIDTH
) -> str:
    """Compose a verse slide and write it to `output_path` as an RGBA TIFF."""
    compose_slide(verse_text, reference, max_width=max_width).save(output_path, "TIFF")
    return output_path


def slide_filename(reference: str, index: int) -> str:
    """
    Sortable, self-describing filename derived from the reference.

    "John 17:1 ESV" -> "John_17_001.tif". Falls back to the sequence number
    if the reference does not parse.
    """
    return f"{slide_stem(reference, index)}.tif"


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

    slides: list[Placed] = []
    for index, (text, ref) in enumerate(prepared, 1):
        if not text.strip():
            continue
        slides.append(plan_verse(text, ref, index))
    return render_deck(slides, output_dir)


# ---------------------------------------------------------------------------
# Point slides
# ---------------------------------------------------------------------------


def plan_points(
    points: Sequence[str], style: str = DEFAULT_POINT_STYLE, stem: str = "point"
) -> list[Placed]:
    """
    Plan a point deck in the named style, without drawing or writing anything.

    Blank points are dropped first: the rolling style positions each point from
    the ones before it, so a blank entry left in place would leave a hole in
    the build.
    """
    kept = [text for text in points if text.strip()]
    if not kept:
        raise EmptyVerseError("no renderable points")
    return get_point_style(style).plan(kept, stem)


def generate_points(
    points: Sequence[str],
    output_dir: str = "./slides",
    style: str = DEFAULT_POINT_STYLE,
    stem: str = "point",
) -> list[str]:
    """
    Render a list of sermon points to `output_dir`.

    Args:
        points: the statements, in the order they should appear.
        output_dir: created if missing.
        style: "rolling" (accumulating reveal) or "centered" (one per slide).
            See sermonflow.layouts.POINT_STYLES.
        stem: filename stem; slides are `<stem>_001.tif` and up.

    Returns the list of written paths.
    """
    return render_deck(plan_points(points, style, stem), output_dir)
