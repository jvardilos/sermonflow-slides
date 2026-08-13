"""
The verse layout: a wrapped passage with its reference underneath.

This is the original slide type, moved here unchanged when layouts/ appeared;
the constants and the placement maths are exactly what was fitted against the
reference deck in slides/. FORMATTING_NOTES.md writes up how each was arrived
at, including two places where an assumption from the PSD turned out to be
wrong.

What is verse-specific lives here: the narrower text box, the gap down to the
reference line, and the reference line's own width budget. The canvas, the
grid and the scrim are shared, and come from base.
"""

from __future__ import annotations

import re

from ..fonts import FreeTypeFont, Face, load_fonts, text_measurer
from ..wrap import balance_wrap
from .base import (
    CAP_HEIGHT,
    LEFT_MARGIN,
    LINE_HEIGHT,
    SCRIM_LIMIT,
    DrawOp,
    EmptyVerseError,
    Placed,
    SlideOverflowError,
    fits,
    snap_top,
)

#: Weight keys (see fonts.WEIGHTS) the verse deck is set in.
VERSE_WEIGHT = "roman"
REFERENCE_WEIGHT = "medium"

TEXT_BOX_WIDTH = 678          # fitted against the reference deck's line counts
                              # in post-scale space: 24/26 verses match, and the
                              # same value is best-scoring for the font choice
REF_GAP = 143                 # last verse line top -> reference line top
REF_CAP_HEIGHT = CAP_HEIGHT   # reference line ink height

#: The reference line is set on one line and never wrapped, so it needs its own
#: budget rather than the verse box's. TEXT_BOX_WIDTH was fitted to reproduce
#: the deck's *verse* line counts and is narrower than the scrim; the longest
#: reference in the canon ("Song of Solomon 8:14 ESV") overruns it by 8px in
#: Neue Haas while still sitting well inside legible background. Measuring the
#: scrim instead of reusing the verse box is what makes that a non-issue.
REF_MAX_WIDTH = SCRIM_LIMIT - LEFT_MARGIN


# ---------------------------------------------------------------------------
# Block geometry
# ---------------------------------------------------------------------------


def block_height(num_lines: int) -> int:
    """Ink height of the whole block: verse lines, gap, then reference line."""
    return (num_lines - 1) * LINE_HEIGHT + REF_GAP + REF_CAP_HEIGHT


def block_top(num_lines: int) -> int:
    """Ink top of the first verse line: centered, then snapped to the grid."""
    return snap_top(block_height(num_lines))


def block_fits(num_lines: int) -> bool:
    """Whether a block of this many verse lines stays within the safe area."""
    return fits(block_top(num_lines), block_height(num_lines))


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


def plan_verse(
    verse_text: str,
    reference: str,
    index: int = 1,
    max_width: float = TEXT_BOX_WIDTH,
) -> Placed:
    """
    The whole slide as draw ops -- the form render.py consumes.

    A thin wrapper over layout_slide, which stays public because the CLI's
    preview and the validation gate both want the lines without the ops.
    """
    verse_font, _ = load_fonts()
    lines, line_tops, ref_top = layout_slide(
        verse_text, reference, font=verse_font, max_width=max_width
    )
    ops = tuple(
        DrawOp(line, LEFT_MARGIN, top, VERSE_WEIGHT)
        for line, top in zip(lines, line_tops)
    )
    ops += (DrawOp(reference, LEFT_MARGIN, ref_top, REFERENCE_WEIGHT),)
    return Placed(ops, slide_stem(reference, index))


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


# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------

_REF_PARTS_RE = re.compile(r"^(.*?)(\d+):(\d+)")

#: A single-chapter book is cited by verse alone ("Jude 3 ESV"), so there is no
#: "chapter:verse" for the pattern above to find. Anchored on the whole label
#: before the number so this cannot match the chapter half of a normal
#: reference -- _REF_PARTS_RE is tried first regardless.
_REF_VERSE_ONLY_RE = re.compile(r"^([1-3]?\s?[A-Za-z][A-Za-z .]*?)\s+(\d+)\b")


def slide_stem(reference: str, index: int) -> str:
    """
    Sortable, self-describing filename stem derived from the reference.

    "John 17:1 ESV" -> "John_17_001", "Jude 3 ESV" -> "Jude_003". Falls back to
    the sequence number if the reference does not parse.
    """
    match = _REF_PARTS_RE.match(reference)
    if match:
        book = match.group(1).strip().replace(" ", "_")
        return f"{book}_{match.group(2)}_{int(match.group(3)):03d}"

    verse_only = _REF_VERSE_ONLY_RE.match(reference)
    if verse_only:
        book = verse_only.group(1).strip().replace(" ", "_")
        return f"{book}_{int(verse_only.group(2)):03d}"

    return f"verse_{index:03d}"
