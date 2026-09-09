"""
Fonts: selection, metrics, kerning and glyph drawing.

The typeface is the concrete thing the reference deck is set in, and the part
most easily got wrong, so it lives in its own module. Everything font-shaped is
here: which files to load, how to measure a run of text the way it will
actually render, the GPOS pair kerning PIL will not apply on its own, and the
per-glyph draw that lays that kerning down.

The font is now **bundled** with the package (see assets/fonts) and located via
importlib.resources, so it resolves identically on macOS, Linux and Windows with
nothing installed. That is a change from the proof of concept, which looked in
macOS system font directories and silently fell back to a bitmap face
everywhere else.

Two NamedTuples carry the state the standard library does not:

  Face     -- a PIL font plus the kerning table PIL ignores
  _Kerning -- the GPOS pair adjustments, scaled to pixels on demand
"""

from __future__ import annotations

import math
import os
from functools import lru_cache
from importlib.resources import files
from typing import Any, NamedTuple, cast

from PIL import Image, ImageDraw, ImageFont
from PIL.ImageFont import FreeTypeFont

from .wrap import Measure

# ---------------------------------------------------------------------------
# Font selection
# ---------------------------------------------------------------------------

FONT_SIZE = 60

#: weight name -> bundled Neue Haas filename under assets/fonts. Layouts name a
#: weight from this table rather than a file, so a layout never has to know
#: that Medium's file is spelled "Mediu".
WEIGHTS: dict[str, str] = {
    "roman": "NeueHaasDisplayRoman.ttf",
    "medium": "NeueHaasDisplayMediu.ttf",
    "bold": "NeueHaasDisplayBold.ttf",
    "black": "NeueHaasDisplayBlack.ttf",
    "roman-italic": "NeueHaasDisplayRomanItalic.ttf",
    "medium-italic": "NeueHaasDisplayMediumItalic.ttf",
    "bold-italic": "NeueHaasDisplayBoldItalic.ttf",
    "black-italic": "NeueHaasDisplayBlackItalic.ttf",
}

#: Verse body. The PSD specifies 55 Roman.
VERSE_WEIGHT = "roman"

#: Reference line. The PSD specifies 65 Medium and the deck is set in it, which
#: is why it reads heavier than the verse above it -- that contrast is the
#: deck's own design, not an artifact. Raise to "bold" or "black" for a heavier
#: line; nothing else needs adjusting, since cap height does not change with
#: weight and REF_MAX_WIDTH has room for the widest reference in the canon at
#: any of them.
REFERENCE_WEIGHT = "medium"

#: Point slides. Measured, not guessed: rendering the point templates' lines in
#: Medium Italic reproduces their ink boxes to within a pixel horizontally and
#: exactly vertically, while Bold Italic -- what this constant provisionally
#: held before template/point-templates/ existed -- runs about 25px wide on a
#: 26-character line. See layouts/points.py for the full measurement.
POINT_WEIGHT = "medium-italic"

#: (path, collection index). Bundled Neue Haas is plain TTF, so index is 0.
_FontFace = tuple[str, int]
#: (label, verse face, reference face, horizontal scale).
_FontChoice = tuple[str, _FontFace, _FontFace, float]


def _font_file(name: str) -> str:
    """Absolute path to a bundled font file, wherever the package installed."""
    return str(files("sermonflow").joinpath("assets", "fonts", name))


def _font_choices(verse_weight: str, reference_weight: str) -> tuple[_FontChoice, ...]:
    """
    Font candidates, best first, for a pair of weight names.

    There is a single candidate now that the real typeface travels with the
    package: the Helvetica-substitute-with-horizontal-condense path the proof
    of concept carried existed only because the real font was not reliably
    present, and is gone. The scale is therefore always 1.0 -- text is drawn
    straight onto the slide with no resample step, which is both exact and
    sharper. The tuple shape is kept so a future alternative could slot in.
    """
    return (
        (
            "Neue Haas Grotesk Display Pro",
            (_font_file(WEIGHTS[verse_weight]), 0),
            (_font_file(WEIGHTS[reference_weight]), 0),
            1.0,
        ),
    )


FONT_CHOICES = _font_choices(VERSE_WEIGHT, REFERENCE_WEIGHT)


def _choose_fonts() -> _FontChoice:
    """First font choice whose files are all present."""
    for choice in FONT_CHOICES:
        _, regular, medium, _ = choice
        if os.path.exists(regular[0]) and os.path.exists(medium[0]):
            return choice
    return ("none", ("", 0), ("", 0), 1.0)


FONT_NAME, _REGULAR_FACE, _MEDIUM_FACE, HORIZONTAL_SCALE = _choose_fonts()

#: Kept as module constants because the glyph-coverage check and the tests both
#: reach for the verse face by path.
FONT_PATH, FONT_INDEX_REGULAR = _REGULAR_FACE
FONT_PATH_MEDIUM, FONT_INDEX_MEDIUM = _MEDIUM_FACE

#: True when rendering with the typeface the deck was actually set in. With the
#: font bundled this is the normal state; it drops to False only if the packaged
#: files somehow cannot be read, in which case a bitmap fallback keeps the
#: pipeline runnable (but non-reference-matching).
IS_REFERENCE_FONT = FONT_NAME == FONT_CHOICES[0][0]


# ---------------------------------------------------------------------------
# Kerning: read GPOS pair adjustments PIL's basic layout ignores
# ---------------------------------------------------------------------------


class _Kerning(NamedTuple):
    pairs: dict[tuple[str, str], int]  # (glyph name, glyph name) -> delta, font units
    upem: int                          # units per em, for scaling to pixels
    cmap: dict[int, str]               # codepoint -> glyph name


class Face(NamedTuple):
    """
    A PIL font plus the kerning PIL cannot apply on its own.

    Pillow's basic layout engine positions each glyph by its bare advance
    width, ignoring GPOS entirely. Photoshop kerns, so the reference deck is
    kerned and unkerned text runs measurably wide -- about 0.3% on a typical
    line and up to 1.3% on one full of kerned pairs, which is enough to move a
    line break. `kerning` carries what is needed to close that gap; it is None
    when the font has no GPOS kerning or fontTools is unavailable, in which
    case everything below degrades to plain PIL behaviour.
    """

    font: FreeTypeFont
    kerning: _Kerning | None = None


def _open_font(path: str, index: int) -> Any:
    """
    Open a font with fontTools as an untyped (Any) object, or None.

    fontTools ships no type stubs, so its objects are walled off behind this
    single Any boundary rather than leaking "unknown type" through the strict
    call sites that inspect kerning and glyph coverage. Returns None when
    fontTools is unavailable or the path does not exist.
    """
    try:
        from fontTools.ttLib import TTCollection, TTFont
    except ImportError:
        return None
    if not path or not os.path.exists(path):
        return None
    collection: Any = TTCollection
    single: Any = TTFont
    if path.lower().endswith(".ttc"):
        return collection(path).fonts[index]
    return single(path)


@lru_cache(maxsize=4)
def _load_kerning(path: str, index: int) -> _Kerning | None:
    """
    Pair kerning from the font's GPOS 'kern' feature, or None.

    Only LookupType 2 (pair adjustment) is read, which is all Neue Haas uses
    and all that matters for Latin text. Contextual kerning is ignored -- it
    would change metrics the layout constants were fitted against without
    measurably improving the match.
    """
    tt = _open_font(path, index)
    if tt is None:
        return None
    try:
        if "GPOS" not in tt:
            return None
        gpos = tt["GPOS"].table
        wanted: set[int] = set()
        for record in gpos.FeatureList.FeatureRecord:
            if record.FeatureTag == "kern":
                wanted.update(record.Feature.LookupListIndex)

        pairs: dict[tuple[str, str], int] = {}
        for i in sorted(wanted):
            lookup = gpos.LookupList.Lookup[i]
            if lookup.LookupType != 2:
                continue
            for sub in lookup.SubTable:
                if sub.Format == 1:
                    _read_pairs_by_glyph(sub, pairs)
                elif sub.Format == 2:
                    _read_pairs_by_class(sub, pairs)
        if not pairs:
            return None
        return _Kerning(pairs, int(tt["head"].unitsPerEm), tt.getBestCmap())
    except Exception:
        return None


def _read_pairs_by_glyph(sub: Any, pairs: dict[tuple[str, str], int]) -> None:
    """PairPos format 1: explicit first-glyph -> second-glyph adjustments."""
    for first, pairset in zip(sub.Coverage.glyphs, sub.PairSet):
        for record in pairset.PairValueRecord:
            delta = getattr(record.Value1, "XAdvance", 0)
            if delta:
                pairs[(first, record.SecondGlyph)] = delta


def _read_pairs_by_class(sub: Any, pairs: dict[tuple[str, str], int]) -> None:
    """
    PairPos format 2: adjustments between glyph *classes*.

    Expanded to explicit pairs once, at load, so lookup stays a dict hit per
    character. Format 1 wins on conflict, matching OpenType subtable order.
    """
    by_first: dict[int, list[str]] = {}
    for glyph in sub.Coverage.glyphs:
        by_first.setdefault(sub.ClassDef1.classDefs.get(glyph, 0), []).append(glyph)
    by_second: dict[int, list[str]] = {}
    for glyph, cls in sub.ClassDef2.classDefs.items():
        by_second.setdefault(cls, []).append(glyph)

    for i, class1 in enumerate(sub.Class1Record):
        if i not in by_first:
            continue
        for j, class2 in enumerate(class1.Class2Record):
            delta = getattr(class2.Value1, "XAdvance", 0)
            if not delta:
                continue
            for first in by_first[i]:
                for second in by_second.get(j, ()):
                    pairs.setdefault((first, second), delta)


def kern_width(text: str, kerning: _Kerning | None, size: int = FONT_SIZE) -> float:
    """Total kerning adjustment for `text`, in pixels. Negative tightens."""
    if kerning is None or len(text) < 2:
        return 0.0
    names = [kerning.cmap.get(ord(ch)) for ch in text]
    units = sum(
        kerning.pairs.get((a, b), 0)
        for a, b in zip(names, names[1:])
        if a and b
    )
    return units * size / kerning.upem


# ---------------------------------------------------------------------------
# Loading and measuring
# ---------------------------------------------------------------------------


@lru_cache(maxsize=16)
def load_face(weight: str, size: int = FONT_SIZE) -> Face:
    """
    The Face for one named weight from WEIGHTS.

    This is the general entry point: a layout picks a weight by name and gets a
    kerned Face back, so adding a slide type set in a different cut of the
    typeface takes no font code at all. load_fonts is the verse pipeline's
    two-face shorthand over it.

    Falls back to PIL's bitmap default only if the bundled font cannot be read,
    which makes output non-reference-matching but keeps the pipeline runnable.
    """
    filename = WEIGHTS.get(weight)
    if filename is None:
        raise ValueError(
            f"unknown weight {weight!r}; choose from {', '.join(WEIGHTS)}"
        )
    path = _font_file(filename)
    if os.path.exists(path):
        try:
            return Face(ImageFont.truetype(path, size), _load_kerning(path, 0))
        except OSError:
            pass
    # Defensive: only reached if the bundled font cannot be read. load_default
    # returns the freetype face when Pillow has freetype (which truetype above
    # also requires), so the cast holds for every Pillow this runs on.
    return Face(cast(FreeTypeFont, ImageFont.load_default(size)))


@lru_cache(maxsize=4)
def load_fonts(size: int = FONT_SIZE) -> tuple[Face, Face]:
    """(verse_face, reference_face) -- the pair the verse layout draws with."""
    return load_face(VERSE_WEIGHT, size), load_face(REFERENCE_WEIGHT, size)


def _as_face(font: Face | FreeTypeFont) -> Face:
    """Accept a Face or a bare PIL font, so callers may pass either."""
    return font if isinstance(font, Face) else Face(font)


def _font_size(font: FreeTypeFont) -> int:
    """The point size a FreeTypeFont was loaded at, defaulting to FONT_SIZE."""
    return int(getattr(font, "size", FONT_SIZE))


def text_measurer(font: Face | FreeTypeFont, scale: float | None = None) -> Measure:
    """
    A `measure(str) -> float` callable for the wrap functions.

    Widths are reported in *rendered* space, i.e. kerned and then scaled by
    HORIZONTAL_SCALE, so wrapping and TEXT_BOX_WIDTH both talk about the pixels
    that end up on the slide rather than the font's bare advance widths.

    Note on kerning: a Pillow built with Raqm (HarfBuzz) already shapes and
    kerns whole strings in `textlength`, so on such a build `kern_width` here is
    an *additional* pair adjustment on top of native shaping. That is
    deliberate and safe -- it only tightens, so a line can break early but never
    overflow the box -- and it keeps wrapping identical whether or not the
    running Pillow happens to ship Raqm. See the layout box-bound tests.
    """
    face = _as_face(font)
    factor = HORIZONTAL_SCALE if scale is None else scale
    scratch = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    size = _font_size(face.font)

    def measure(text: str) -> float:
        natural = scratch.textlength(text, font=face.font)
        return (natural + kern_width(text, face.kerning, size)) * factor

    return measure


# ---------------------------------------------------------------------------
# Glyph coverage
# ---------------------------------------------------------------------------


@lru_cache(maxsize=2)
def _font_charset() -> frozenset[int] | None:
    """
    Every codepoint the verse font can draw, or None if it cannot be inspected.

    fontTools is optional here: without it the glyph check simply reports
    nothing rather than blocking a render.
    """
    font = _open_font(FONT_PATH, FONT_INDEX_REGULAR)
    if font is None:
        return None
    try:
        covered: set[int] = set()
        for table in font["cmap"].tables:
            covered |= {int(codepoint) for codepoint in table.cmap}
        return frozenset(covered)
    except Exception:
        return None


def find_unrenderable(text: str) -> list[tuple[str, str]]:
    """
    Characters the verse font has no glyph for.

    These do not fail -- they render as tofu boxes, which is worse than
    failing because it looks like output. CJK, Hebrew and emoji all land here,
    so the validation gate catches them before anything reaches a screen.

    Returns a list of (kind, character) pairs.
    """
    covered = _font_charset()
    if covered is None:
        return []
    seen: set[str] = set()
    problems: list[tuple[str, str]] = []
    for ch in text:
        if ch.isspace() or ch in seen:
            continue
        seen.add(ch)
        if ord(ch) not in covered:
            problems.append(("unrenderable-character", f"{ch!r} U+{ord(ch):04X}"))
    return problems


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

_WHITE = (255, 255, 255, 255)


def _ink_offset(font: FreeTypeFont) -> int:
    """
    Distance from PIL's draw origin down to the top of capital ink.

    PIL anchors text at the ascender, but every layout constant was measured
    from ink, so drawing needs this correction.
    """
    return int(font.getbbox("H")[1])


def _draw_line(
    draw: ImageDraw.ImageDraw, left: float, top: float, text: str, face: Face
) -> None:
    """
    Draw one run of text at (left, top), applying kerning if the face has it.

    Without kerning this is a single PIL call. With it, glyphs are placed one
    at a time at running kerned positions. That is safe to do: PIL's basic
    layout engine already positions each glyph independently by its advance
    width, so drawing per character at the same accumulated offsets is
    pixel-identical to drawing the whole string (verified over the deck), and
    adding the kern deltas is then the only difference.
    """
    if face.kerning is None:
        draw.text((left, top), text, fill=_WHITE, font=face.font)
        return

    kerning = face.kerning
    size = _font_size(face.font)
    names = [kerning.cmap.get(ord(ch)) for ch in text]
    x = float(left)
    for i, ch in enumerate(text):
        draw.text((x, top), ch, fill=_WHITE, font=face.font)
        x += draw.textlength(ch, font=face.font)
        if i + 1 < len(text) and names[i] and names[i + 1]:
            first, second = names[i], names[i + 1]
            assert first is not None and second is not None
            x += kerning.pairs.get((first, second), 0) * size / kerning.upem


def draw_text(
    img: Image.Image,
    left: float,
    ink_top: float,
    text: str,
    font: Face | FreeTypeFont,
    scale: float | None = None,
) -> None:
    """
    Draw one line with its ink top at `ink_top`, condensed by `scale`.

    Only the horizontal axis is scaled, so cap height, baseline and line
    spacing are untouched -- the same thing Photoshop's HorizontalScale does.
    At scale 1.0 (the normal case with the bundled font) the text is drawn
    straight onto the slide; otherwise it goes to its own transparent layer, is
    resampled, then composited, because PIL cannot scale glyphs while drawing.
    """
    face = _as_face(font)
    factor = HORIZONTAL_SCALE if scale is None else scale
    top = ink_top - _ink_offset(face.font)

    if factor == 1.0:
        _draw_line(ImageDraw.Draw(img), left, top, text, face)
        return

    ascent, descent = face.font.getmetrics()
    scratch = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    natural = scratch.textlength(text, font=face.font)
    natural += kern_width(text, face.kerning, _font_size(face.font))
    width, height = max(1, math.ceil(natural) + 4), ascent + descent + 4

    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    _draw_line(ImageDraw.Draw(layer), 0, 0, text, face)
    layer = layer.resize(
        (max(1, round(width * factor)), height), Image.Resampling.LANCZOS
    )
    img.alpha_composite(layer, (round(left), round(top)))
