"""
Vertical and horizontal layout: where a verse block sits, whether it fits, and
the safe budget for the reference line.

Nearly every constant here was derived by measuring the professionally produced
reference deck rather than guessing -- box width, line height, the 72px
placement grid, the scrim's alpha curve. FORMATTING_NOTES.md writes up how each
was arrived at, including two places where an assumption from the PSD turned out
to be wrong.

The scrim's alpha profile lives here rather than in render.py because the
reference-line budget (REF_MAX_WIDTH) is derived from it at import time, and a
layout budget must not have to import the renderer.
"""

from __future__ import annotations

from .fonts import FreeTypeFont, Face, load_fonts, text_measurer
from .wrap import balance_wrap

# ---------------------------------------------------------------------------
# Canvas and block geometry, all measured from the reference deck
# ---------------------------------------------------------------------------

SLIDE_WIDTH, SLIDE_HEIGHT = 1920, 1080

LEFT_MARGIN = 91
TEXT_BOX_WIDTH = 678          # fitted against the reference deck's line counts
                              # in post-scale space: 24/26 verses match, and the
                              # same value is best-scoring for the font choice
LINE_HEIGHT = 72              # measured line-top delta
REF_GAP = 143                 # last verse line top -> reference line top
REF_CAP_HEIGHT = 45           # reference line ink height

# The reference deck snaps the first line's ink top to this grid rather than
# centering freely, so a block's vertical position is quantized.
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


#: The reference line is set on one line and never wrapped, so it needs its own
#: budget rather than the verse box's. TEXT_BOX_WIDTH was fitted to reproduce
#: the deck's *verse* line counts and is narrower than the scrim; the longest
#: reference in the canon ("Song of Solomon 8:14 ESV") overruns it by 8px in
#: Neue Haas while still sitting well inside legible background. Measuring the
#: scrim instead of reusing the verse box is what makes that a non-issue.
REF_MAX_WIDTH = _scrim_limit() - LEFT_MARGIN


class SlideOverflowError(ValueError):
    """Raised when a verse needs more lines than the slide can hold."""


class EmptyVerseError(ValueError):
    """Raised when a verse has no renderable text. generate_slides skips these."""


# ---------------------------------------------------------------------------
# Block geometry
# ---------------------------------------------------------------------------


def block_height(num_lines: int) -> int:
    """Ink height of the whole block: verse lines, gap, then reference line."""
    return (num_lines - 1) * LINE_HEIGHT + REF_GAP + REF_CAP_HEIGHT


def block_top(num_lines: int) -> int:
    """
    Ink top of the first verse line.

    The block is centered vertically, then snapped to the reference deck's
    72px grid. Snapping is what the reference deck does -- an unsnapped centre
    would sit up to half a line off from every slide the operator produced.
    """
    ideal = (SLIDE_HEIGHT - block_height(num_lines)) / 2
    steps = round((ideal - GRID_ORIGIN) / LINE_HEIGHT)
    return GRID_ORIGIN + steps * LINE_HEIGHT


def block_fits(num_lines: int) -> bool:
    """Whether a block of this many verse lines stays within the safe area."""
    top = block_top(num_lines)
    return (
        top >= MIN_TOP_MARGIN
        and top + block_height(num_lines) <= SLIDE_HEIGHT - MIN_BOTTOM_MARGIN
    )


def max_lines() -> int:
    """Largest verse line count that still fits the safe area."""
    n = 1
    while block_fits(n + 1):
        n += 1
    return n


# ---------------------------------------------------------------------------
# Placing a verse
# ---------------------------------------------------------------------------


def layout_slide(
    verse_text: str,
    reference: str,
    font: Face | FreeTypeFont | None = None,
    max_width: float = TEXT_BOX_WIDTH,
) -> tuple[list[str], list[int], int]:
    """
    Work out the finished geometry without drawing anything.

    Returns (lines, line_tops, reference_top) where the tops are ink tops.
    Raises SlideOverflowError if the verse cannot fit the safe area, and
    EmptyVerseError if there is no renderable text.
    """
    verse_font: Face | FreeTypeFont
    if font is None:
        verse_font, _ = load_fonts()
    else:
        verse_font = font
    measure = text_measurer(verse_font)

    lines = balance_wrap(verse_text, measure, max_width)
    if not lines:
        raise EmptyVerseError(f"{reference}: no renderable text")
    if not block_fits(len(lines)):
        raise SlideOverflowError(
            f"{reference}: needs {len(lines)} lines, "
            f"at most {max_lines()} fit on a slide"
        )

    top = block_top(len(lines))
    line_tops = [top + i * LINE_HEIGHT for i in range(len(lines))]
    return lines, line_tops, line_tops[-1] + REF_GAP


def find_overlong_reference(reference: str) -> list[tuple[str, str]]:
    """
    Report a reference line too wide to sit on legible background.

    Lives with the other find_* checks conceptually but has to be defined here
    because it needs font metrics. Returns a list of (kind, detail) pairs so it
    composes with find_artifacts and find_unrenderable in the validation gate.
    """
    _, ref_face = load_fonts()
    width = text_measurer(ref_face)(reference)
    if width <= REF_MAX_WIDTH:
        return []
    return [("reference-too-wide", f"{width:.0f}px > {REF_MAX_WIDTH}px")]
