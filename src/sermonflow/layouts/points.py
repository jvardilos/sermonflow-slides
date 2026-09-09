"""
Point slides: short statements, no reference line, set in Medium Italic.

Two styles, both measured off template/point-templates/:

  rolling   -- a list that accumulates. One slide per point, each showing every
               point up to that one at a fixed position, so playing the slides
               in order reads as the points being revealed one at a time.
  centered  -- one statement per slide, its block centered on the canvas and
               snapped to the grid, which lands it slightly above true centre.

What the templates gave up, and where each number below comes from:

  typeface   Neue Haas Display **Medium Italic** at the same 60px as the verse
             deck. Rendered ink boxes match the templates to within a pixel on
             all three probe lines; Bold Italic (the weight the roadmap
             guessed) runs ~25px wide on a 26-character line.
  left edge  91 -- the same LEFT_MARGIN as the verse deck.
  grid       every line in every template sits on 197 + k*72, i.e. the shared
             GRID_ORIGIN and LINE_HEIGHT. Nothing here needed its own grid.
  step       rolling points are 144 apart = exactly two line heights.
  width      wrapped lines in the templates run out to x=832-838, which is the
             scrim's legible limit and not the verse deck's narrower box. So
             points wrap at MAX_TEXT_WIDTH (741), not TEXT_BOX_WIDTH (678).

One measurement disagrees with itself and is worth knowing about: the two
four-line centered templates were placed a line apart from each other
(Paraphrase at 413, Point at 341). snap_top reproduces Paraphrase, and the
one-line and two-line templates besides, so Point.tif reads as a hand nudge
rather than a rule. If it turns out to have been deliberate, the knob is
snap_top's input, not a new constant here.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..fonts import POINT_WEIGHT, load_face, text_measurer
from ..wrap import balance_wrap
from .base import (
    CAP_HEIGHT,
    GRID_ORIGIN,
    LEFT_MARGIN,
    LINE_HEIGHT,
    MAX_TEXT_WIDTH,
    MIN_BOTTOM_MARGIN,
    SLIDE_HEIGHT,
    DrawOp,
    EmptyVerseError,
    Placed,
    SlideOverflowError,
    fits,
    snap_top,
)

#: Points wrap to the scrim's legible limit rather than the verse box.
POINT_BOX_WIDTH = MAX_TEXT_WIDTH

#: Distance from one rolling point's last line down to the next point's first.
#: Measured at 144 between single-line points, which is two line heights; a
#: point that wraps therefore keeps a two-line gap after its own last line
#: rather than swallowing the space it needs.
ROLLING_STEP = 2 * LINE_HEIGHT


def wrap_point(text: str, max_width: float = POINT_BOX_WIDTH) -> list[str]:
    """Wrapped lines for one point. Raises EmptyVerseError on blank text."""
    lines = balance_wrap(text, text_measurer(load_face(POINT_WEIGHT)), max_width)
    if not lines:
        raise EmptyVerseError("point has no renderable text")
    return lines


def block_height(num_lines: int) -> int:
    """Ink height of a point block: no reference line, so lines and cap only."""
    return (num_lines - 1) * LINE_HEIGHT + CAP_HEIGHT


def _ops(lines: Sequence[str], top: int) -> tuple[DrawOp, ...]:
    """Draw ops for one point's lines, starting at ink top `top`."""
    return tuple(
        DrawOp(line, LEFT_MARGIN, top + i * LINE_HEIGHT, POINT_WEIGHT)
        for i, line in enumerate(lines)
    )


# ---------------------------------------------------------------------------
# Rolling: the accumulating, one-at-a-time reveal
# ---------------------------------------------------------------------------


def rolling_tops(wrapped: Sequence[Sequence[str]]) -> list[int]:
    """
    Ink top of each point, top-anchored from GRID_ORIGIN.

    Computed from the *whole* list so a point sits at the same y on every slide
    it appears on -- that fixedness is the entire effect. A point is never
    re-flowed because a later one was added.
    """
    tops: list[int] = []
    top = GRID_ORIGIN
    for lines in wrapped:
        tops.append(top)
        top += (len(lines) - 1) * LINE_HEIGHT + ROLLING_STEP
    return tops


def plan_rolling(points: Sequence[str], stem: str = "point") -> list[Placed]:
    """
    One slide per point, each showing points 1..i.

    Raises SlideOverflowError if the finished list runs past the safe area, and
    EmptyVerseError if any point is blank -- both before anything is drawn, so
    a deck is never half-rendered.
    """
    wrapped = [wrap_point(text) for text in points]
    tops = rolling_tops(wrapped)
    if wrapped:
        bottom = tops[-1] + block_height(len(wrapped[-1]))
        if not fits(tops[0], bottom - tops[0]):
            raise SlideOverflowError(
                f"{len(points)} points reach {bottom}px, past the "
                f"{SLIDE_HEIGHT - MIN_BOTTOM_MARGIN}px safe area; "
                f"shorten them or split the list across two decks"
            )

    slides: list[Placed] = []
    for i in range(len(wrapped)):
        ops: tuple[DrawOp, ...] = ()
        for lines, top in zip(wrapped[: i + 1], tops[: i + 1]):
            ops += _ops(lines, top)
        slides.append(Placed(ops, f"{stem}_{i + 1:03d}"))
    return slides


# ---------------------------------------------------------------------------
# Centered: one statement, sitting a little above middle
# ---------------------------------------------------------------------------


def centered_top(num_lines: int) -> int:
    """Ink top of a centered point block of this many lines."""
    return snap_top(block_height(num_lines))


def plan_centered(points: Sequence[str], stem: str = "point") -> list[Placed]:
    """
    One slide per point, each centered on its own -- no accumulation.

    Because block_height counts cap height and not descenders, the snapped
    result sits a little above true centre, which is what the templates do.
    """
    slides: list[Placed] = []
    for i, text in enumerate(points, 1):
        lines = wrap_point(text)
        height = block_height(len(lines))
        top = centered_top(len(lines))
        if not fits(top, height):
            raise SlideOverflowError(
                f"point {i} needs {len(lines)} lines, more than a slide holds"
            )
        slides.append(Placed(_ops(lines, top), f"{stem}_{i:03d}"))
    return slides
