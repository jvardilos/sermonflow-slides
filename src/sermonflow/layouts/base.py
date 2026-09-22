"""
Canvas geometry every layout shares, and the small IR they all produce.

Split out of the old single-purpose layout.py when the second slide type
arrived. The rule for what belongs here: anything a *new* layout would
otherwise have to re-derive from the reference deck -- the canvas, the left
margin, the 72px placement grid, the scrim and how far right it stays legible.
Anything specific to one slide type (the reference line's gap, the point
styles' step) belongs in that layout's own module.

Every layout ends at the same place: a `Placed`, which is a finished slide
expressed as draw operations at ink coordinates and nothing else. That is the
seam that lets render.py stay layout-agnostic -- it composes a `Placed` without
knowing whether a verse, a point or something not written yet produced it.

Constants here were measured from the professionally produced reference decks
(verse deck in slides/, point deck in template/point-templates/), not guessed.
"""

from __future__ import annotations

from typing import NamedTuple

# ---------------------------------------------------------------------------
# Canvas
# ---------------------------------------------------------------------------

SLIDE_WIDTH, SLIDE_HEIGHT = 1920, 1080

LEFT_MARGIN = 91              # both decks set every line from this x
LINE_HEIGHT = 72              # measured line-top delta within a block
CAP_HEIGHT = 45               # ink height of a line with no descender

#: The decks snap a block's first ink top to this grid rather than centering
#: freely, so vertical position is quantized. Both the verse deck and the point
#: templates sit on it: the rolling points start exactly here, and every
#: centered point lands on GRID_ORIGIN + k * LINE_HEIGHT.
GRID_ORIGIN = 197
MIN_TOP_MARGIN = 40
MIN_BOTTOM_MARGIN = 40

# Alpha profile of the black left-hand scrim, sampled every 64px from the
# reference deck (the PSD's "Rectangle 1" layer flattened with its 207/255
# layer opacity). Interpolating these 31 points reproduces the reference
# within ~0.2/255 mean, which a fitted smoothstep curve cannot match.
GRADIENT_PROFILE: tuple[int, ...] = (
    207, 207, 207, 207, 207, 205, 202, 197, 190, 180, 165, 146, 124, 101,
    77, 52, 25, 5, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
)
GRADIENT_PROFILE_STEP = 64

#: Minimum scrim alpha for white text to stay comfortably legible. 100/207 is
#: about half the scrim's peak opacity.
LEGIBLE_ALPHA = 100


def _scrim_limit(min_alpha: int = LEGIBLE_ALPHA) -> int:
    """Rightmost x where the scrim is still at least `min_alpha` opaque."""
    dark = [i for i, alpha in enumerate(GRADIENT_PROFILE) if alpha >= min_alpha]
    return max(dark) * GRADIENT_PROFILE_STEP


#: Widest a line can be drawn from LEFT_MARGIN and still sit on legible
#: background. This is a property of the artwork, not of any one slide type, so
#: layouts that have no narrower reason to wrap sooner use it directly (the
#: point styles do; the verse box is deliberately narrower -- see verse.py).
SCRIM_LIMIT = _scrim_limit()
MAX_TEXT_WIDTH = SCRIM_LIMIT - LEFT_MARGIN


class SlideOverflowError(ValueError):
    """Raised when content needs more room than the slide can give it."""


class EmptyVerseError(ValueError):
    """Raised when a slide has no renderable text. Batch renders skip these."""


# ---------------------------------------------------------------------------
# Vertical placement
# ---------------------------------------------------------------------------


def snap_top(block_height: int) -> int:
    """
    Ink top for a vertically centered block of `block_height`, snapped to grid.

    Snapping is what the reference decks do -- an unsnapped centre would sit up
    to half a line off from every slide the operator produced. Both slide types
    that centre anything go through here, so they cannot drift apart.
    """
    ideal = (SLIDE_HEIGHT - block_height) / 2
    steps = round((ideal - GRID_ORIGIN) / LINE_HEIGHT)
    return GRID_ORIGIN + steps * LINE_HEIGHT


def fits(top: int, block_height: int) -> bool:
    """Whether a block placed at `top` stays inside the safe area."""
    return (
        top >= MIN_TOP_MARGIN
        and top + block_height <= SLIDE_HEIGHT - MIN_BOTTOM_MARGIN
    )


# ---------------------------------------------------------------------------
# The intermediate representation
# ---------------------------------------------------------------------------


class DrawOp(NamedTuple):
    """
    One line of text, placed.

    `weight` is a key into fonts.WEIGHTS rather than a loaded font, so planning
    stays free of font *objects* (and of the filesystem) while still deciding
    the typeface -- which is a layout decision: the verse deck is Roman, the
    point templates are Medium Italic.
    """

    text: str
    left: float
    ink_top: float
    weight: str


class Placed(NamedTuple):
    """
    One finished slide, ready to draw: ordered ops plus a filename stem.

    `stem` is what render.py names the file after ("John_17_001", "point_003").
    Layouts own it because only the layout knows what identifies a slide.
    """

    ops: tuple[DrawOp, ...]
    stem: str
