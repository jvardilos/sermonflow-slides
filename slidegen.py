#!/usr/bin/env python3
"""
Slide generation helpers.

Everything here is about turning verse text into a finished 1920x1080 RGBA
TIFF that matches the professionally produced reference deck (see
FORMATTING_NOTES.md for how each constant and rule below was derived by
measuring `John 17 /*.tif`).

Three separable concerns, in pipeline order:

  1. Text normalization  -- strip_artifacts / apply_quote_carry /
     capitalize_first_letter, combined in format_verses. Pure string work,
     no font metrics, no PIL. This is the layer that must survive a
     retrieval-backend swap, which is why it lives here and not in
     retrieve.py.
  2. Line breaking       -- greedy_wrap / balance_wrap. Needs font metrics
     (a `measure` callable) but not a canvas.
  3. Rendering           -- make_gradient / render_slide / generate_slides.

Nothing in layers 1 and 2 touches the network or the filesystem, so they are
cheap to test exhaustively.
"""

import math
import os
import re
from functools import lru_cache
from typing import NamedTuple

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Layout constants, all measured from the reference deck
# ---------------------------------------------------------------------------

SLIDE_WIDTH, SLIDE_HEIGHT = 1920, 1080

FONT_SIZE = 60

# The reference deck is set in Neue Haas Grotesk Display Pro -- 55 Roman for the
# verse, 65 Medium for the reference line, both 60pt, tracking 0, all read
# straight out of the PSD.
#
# Candidates in preference order: (label, regular, medium, horizontal scale),
# where each face is (path, collection index). The first whose files are all
# present wins, so installing the real font is the only step needed to use it.
#
# The scale condenses rendered text horizontally. It exists only for the
# substitute: Helvetica Neue sets ~10% wider than Neue Haas at the same size, so
# the reciprocal pulls line widths back onto the reference. With the real font
# it is 1.0 and text is drawn directly, which is both exact and sharper (no
# resample step): measured against the deck, ink overlap roughly doubles.
_USER_FONTS = os.path.expanduser('~/Library/Fonts')
_HELVETICA = '/System/Library/Fonts/HelveticaNeue.ttc'

#: The copies committed alongside this file. Both paths above are macOS-only,
#: so off a Mac neither resolved, `_choose_fonts` returned 'none', and
#: `load_fonts` fell to PIL's bitmap default. That is not a smaller version of
#: the same output: the glyph-coverage check stops finding ANY unrenderable
#: character -- CJK, Hebrew and emoji all report as drawable -- and text
#: measures 118px against a 678px box, so validation passes everything and the
#: wrapper packs whole verses onto one line. Measured on ubuntu-24.04, where it
#: failed 6 tests in test_edge_cases.py that pass on macOS: the suite was green
#: here only because this machine happens to have the font installed.
#:
#: font/ has been tracked in this repo the whole time and was never consulted,
#: because the candidates below were built solely from _USER_FONTS.
_REPO_FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'font')

#: weight name -> (Neue Haas filename, Helvetica Neue collection index).
#: Helvetica has no plain Black, so 'black' falls back to its Bold.
WEIGHTS = {
    'roman': ('NeueHaasDisplayRoman.ttf', 0),
    'medium': ('NeueHaasDisplayMediu.ttf', 10),
    'bold': ('NeueHaasDisplayBold.ttf', 1),
    'black': ('NeueHaasDisplayBlack.ttf', 1),
}

#: Verse body. The PSD specifies 55 Roman.
VERSE_WEIGHT = 'roman'

#: Reference line. The PSD specifies 65 Medium and the deck is set in it, which
#: is why it reads heavier than the verse above it -- that contrast is the
#: deck's own design, not an artifact. Raise to 'bold' or 'black' for a heavier
#: line; nothing else needs adjusting, since cap height does not change with
#: weight and REF_MAX_WIDTH has room for the widest reference in the canon at
#: any of them.
REFERENCE_WEIGHT = 'medium'

#: Point slides: a short line of emphasis with no reference. Provisional --
#: pending a reference example to measure against.
POINT_WEIGHT = 'bold'


def _font_choices(verse_weight, reference_weight):
    """Font candidates, best first, for a pair of weight names."""
    verse, reference = WEIGHTS[verse_weight], WEIGHTS[reference_weight]
    return (
        ('Neue Haas Grotesk Display Pro',
         (os.path.join(_USER_FONTS, verse[0]), 0),
         (os.path.join(_USER_FONTS, reference[0]), 0),
         1.0),
        # Same typeface, same scale, so this is a location fallback rather than
        # a substitution -- and it is ordered AFTER the installed copy so a Mac
        # with the font in ~/Library/Fonts resolves exactly as it did before.
        # It ranks above Helvetica because it IS the reference face: falling to
        # a 1/1.10-condensed substitute while the real font sits in the repo
        # would be choosing the worse render.
        ('Neue Haas Grotesk Display Pro',
         (os.path.join(_REPO_FONTS, verse[0]), 0),
         (os.path.join(_REPO_FONTS, reference[0]), 0),
         1.0),
        ('Helvetica Neue (substitute)',
         (_HELVETICA, verse[1]),
         (_HELVETICA, reference[1]),
         1 / 1.10),
    )


FONT_CHOICES = _font_choices(VERSE_WEIGHT, REFERENCE_WEIGHT)


def _choose_fonts():
    """First font choice whose files are all installed."""
    for choice in FONT_CHOICES:
        _, regular, medium, _ = choice
        if os.path.exists(regular[0]) and os.path.exists(medium[0]):
            return choice
    return ('none', (None, 0), (None, 0), 1.0)


FONT_NAME, _REGULAR_FACE, _MEDIUM_FACE, HORIZONTAL_SCALE = _choose_fonts()

#: Kept as module constants because the glyph-coverage check and the tests both
#: reach for the verse face by path.
FONT_PATH, FONT_INDEX_REGULAR = _REGULAR_FACE
FONT_PATH_MEDIUM, FONT_INDEX_MEDIUM = _MEDIUM_FACE

#: True when rendering with the typeface the deck was actually set in.
IS_REFERENCE_FONT = FONT_NAME == FONT_CHOICES[0][0]

LEFT_MARGIN = 91
TEXT_BOX_WIDTH = 678          # fitted against the reference deck's line counts
                              # in post-scale space: 24/26 verses match, and the
                              # same value is best-scoring for both font choices
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
GRADIENT_PROFILE = (
    207, 207, 207, 207, 207, 205, 202, 197, 190, 180, 165, 146, 124, 101,
    77, 52, 25, 5, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
)
GRADIENT_PROFILE_STEP = 64

#: Minimum scrim alpha for white text to stay comfortably legible. 100/207 is
#: about half the scrim's peak opacity.
LEGIBLE_ALPHA = 100


def _scrim_limit(min_alpha=LEGIBLE_ALPHA):
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

OPEN_QUOTE = '“'         # "
CLOSE_QUOTE = '”'        # "


class SlideOverflowError(ValueError):
    """Raised when a verse needs more lines than the slide can hold."""


class EmptyVerseError(ValueError):
    """Raised when a verse has no renderable text. generate_slides skips these."""


# ---------------------------------------------------------------------------
# 1. Text normalization
# ---------------------------------------------------------------------------

# BibleGateway footnote markers: [a], [b], [12], and the occasional [aa].
_FOOTNOTE_MARKER_RE = re.compile(r'\[\s*[0-9a-zA-Z]{1,3}\s*\]')
# Cross-reference markers: (A), (BZ), (CAA). Restricted to short all-caps runs
# so a legitimate parenthetical is never eaten.
_CROSSREF_MARKER_RE = re.compile(r'\(\s*[A-Z]{1,3}\s*\)')
# A verse number left stranded at the head of the text, e.g. "16 They do not".
_LEADING_VERSENUM_RE = re.compile(r'^\s*\d{1,3}\s+(?=[\w‘“])')
_WHITESPACE_RE = re.compile(r'\s+')
_SPACE_BEFORE_PUNCT_RE = re.compile(r'\s+([,.;:!?’”])')

_STRAIGHT_DOUBLE = '"'
_STRAIGHT_SINGLE = "'"
_CLOSING_CONTEXT = ',.;:!?’”)'


def normalize_quotes(text):
    """
    Convert straight quotes to typographic ones so the carry state machine
    has a single set of characters to reason about.

    A double quote closes if the character before it ends a word; otherwise it
    opens. A single quote is an apostrophe when it follows a word character.
    """
    out = []
    for i, ch in enumerate(text):
        prev = text[i - 1] if i else ''
        if ch == _STRAIGHT_DOUBLE:
            closing = bool(prev) and (prev.isalnum() or prev in _CLOSING_CONTEXT)
            out.append(CLOSE_QUOTE if closing else OPEN_QUOTE)
        elif ch == _STRAIGHT_SINGLE:
            out.append('’' if prev.isalnum() else '‘')
        else:
            out.append(ch)
    return ''.join(out)


def strip_artifacts(text):
    """
    Remove scrape residue that would otherwise show up on a slide, and
    normalize whitespace and quote characters.

    Only unambiguous edits happen here. Anything that *might* be legitimate
    verse content is left alone and reported by find_artifacts instead.
    """
    text = _FOOTNOTE_MARKER_RE.sub('', text)
    text = _CROSSREF_MARKER_RE.sub('', text)
    text = _LEADING_VERSENUM_RE.sub('', text)
    text = normalize_quotes(text)
    text = _WHITESPACE_RE.sub(' ', text)
    text = _SPACE_BEFORE_PUNCT_RE.sub(r'\1', text)
    return text.strip()


def find_artifacts(text):
    """
    Report anything that looks like scrape residue or a typographic mistake.

    Returns a list of (kind, snippet) pairs, empty when the text is clean.
    Used as a validation pass by main.py and asserted on in the tests -- it is
    the safety net for markers a future retrieval backend forgets to strip.
    """
    problems = []
    for match in _FOOTNOTE_MARKER_RE.finditer(text):
        problems.append(('footnote-marker', match.group()))
    for match in _CROSSREF_MARKER_RE.finditer(text):
        problems.append(('crossref-marker', match.group()))
    leading = _LEADING_VERSENUM_RE.match(text)
    if leading:
        problems.append(('leading-verse-number', leading.group().strip()))
    if _STRAIGHT_DOUBLE in text:
        problems.append(('straight-double-quote', _STRAIGHT_DOUBLE))
    if _STRAIGHT_SINGLE in text:
        problems.append(('straight-single-quote', _STRAIGHT_SINGLE))
    if '  ' in text:
        problems.append(('double-space', '  '))
    if text != text.strip():
        problems.append(('edge-whitespace', repr(text[:1] + '...' + text[-1:])))
    for ch, name in (('\n', 'newline'), ('\t', 'tab'), ('\r', 'carriage-return')):
        if ch in text:
            problems.append((name, repr(ch)))
    unbalanced = text.count(OPEN_QUOTE) - text.count(CLOSE_QUOTE)
    if abs(unbalanced) > 1:
        problems.append(('unbalanced-quotes', f'{unbalanced:+d}'))
    return problems


@lru_cache(maxsize=2)
def _font_charset():
    """
    Every codepoint the verse font can draw, or None if it cannot be inspected.

    fontTools is optional: without it the glyph check simply reports nothing
    rather than blocking a render.
    """
    try:
        from fontTools.ttLib import TTCollection, TTFont
    except ImportError:
        return None
    if not FONT_PATH or not os.path.exists(FONT_PATH):
        return None
    try:
        if FONT_PATH.lower().endswith('.ttc'):
            font = TTCollection(FONT_PATH).fonts[FONT_INDEX_REGULAR]
        else:
            font = TTFont(FONT_PATH)
        covered = set()
        for table in font['cmap'].tables:
            covered |= set(table.cmap)
        return frozenset(covered)
    except Exception:
        return None


def find_unrenderable(text):
    """
    Characters the verse font has no glyph for.

    These do not fail -- they render as tofu boxes, which is worse than
    failing because it looks like output. CJK, Hebrew and emoji all land here,
    so main.py's validation gate catches them before anything reaches a screen.

    Returns a list of (kind, character) pairs.
    """
    covered = _font_charset()
    if covered is None:
        return []
    seen = set()
    problems = []
    for ch in text:
        if ch.isspace() or ch in seen:
            continue
        seen.add(ch)
        if ord(ch) not in covered:
            problems.append(('unrenderable-character', f'{ch!r} U+{ord(ch):04X}'))
    return problems


def apply_quote_carry(texts):
    """
    Quote each verse as though it stands alone on its slide.

    The reference deck treats every slide as self-contained: a verse that
    lands inside an ongoing quotation gets its own opening mark, and one whose
    quotation keeps running past it gets its own closing mark -- even though
    neither appears in the source at that point. See FORMATTING_NOTES.md #1.

    A leading open-quote on a verse that is *already* inside a quotation is
    the source's paragraph-continuation convention, not a new nesting level,
    so it does not deepen the count. Single quotes are deliberately ignored:
    they nest inside double quotes and must not disturb the depth.

    Takes and returns a list, because the rule is order-dependent.
    """
    out = []
    depth = 0
    for text in texts:
        carry_in = depth > 0

        opens = text.count(OPEN_QUOTE)
        closes = text.count(CLOSE_QUOTE)
        if carry_in and text.startswith(OPEN_QUOTE):
            opens -= 1
        depth = max(0, depth + opens - closes)
        carry_out = depth > 0

        if carry_in and not text.startswith(OPEN_QUOTE):
            text = OPEN_QUOTE + text
        if carry_out and not text.endswith(CLOSE_QUOTE):
            text = text + CLOSE_QUOTE
        out.append(text)
    return out


def capitalize_first_letter(text):
    """
    Uppercase the first alphabetic character, leaving everything else as-is.

    Deliberately not str.capitalize() or .title(): a verse may begin with a
    quote mark or dash, and the rest of the first word must keep its own case
    ("I'm" stays "I'm", an all-caps name stays all-caps).
    """
    for i, ch in enumerate(text):
        if ch.isalpha():
            return text[:i] + ch.upper() + text[i + 1:]
    return text


def format_verses(verses):
    """
    Run the full text pipeline over a list of (verse_text, reference) pairs.

    Returns a new list of (display_text, reference) pairs ready to render.
    """
    cleaned = [(strip_artifacts(text), ref) for text, ref in verses]
    quoted = apply_quote_carry([text for text, _ in cleaned])
    return [
        (capitalize_first_letter(text), ref)
        for text, (_, ref) in zip(quoted, cleaned)
    ]


# ---------------------------------------------------------------------------
# 2. Line breaking
# ---------------------------------------------------------------------------

def break_long_word(word, measure, max_width):
    """
    Split a word too wide for the box into box-width chunks.

    Character-level, no hyphenation: this exists for junk tokens (a pasted
    hash, a URL) that would otherwise be drawn straight off the canvas. A
    single character wider than the box is emitted alone so this always makes
    progress.
    """
    chunks = []
    current = ''
    for ch in word:
        candidate = current + ch
        if current and measure(candidate) > max_width:
            chunks.append(current)
            current = ch
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def greedy_wrap(text, measure, max_width):
    """
    Classic fill-as-you-go wrap: the baseline balance_wrap measures against.

    A word wider than the box is hard-broken rather than left to overflow, so
    no line ever runs off the slide. See break_long_word.
    """
    lines = []
    current = ''
    for word in text.split():
        if measure(word) > max_width:
            if current:
                lines.append(current)
            chunks = break_long_word(word, measure, max_width)
            lines.extend(chunks[:-1])
            current = chunks[-1]
            continue
        candidate = f'{current} {word}' if current else word
        if not current or measure(candidate) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def balance_wrap(text, measure, max_width):
    """
    Even out line lengths without adding a line -- the "make it look like a
    box" behaviour of the reference deck.

    Greedy wrap fills each line as full as it can with no lookahead, which
    strands a half-empty line mid-paragraph. So: take greedy's line count at
    full width as the target, then binary-search the narrowest width that
    still yields that many lines and wrap there. Same technique as CSS
    `text-wrap: balance`.

    Guarantees, both asserted in the tests:
      - never returns more lines than greedy_wrap at the same width
      - never returns a line wider than greedy_wrap's widest
    """
    baseline = greedy_wrap(text, measure, max_width)
    if len(baseline) <= 1:
        return baseline

    # Never search below the widest unbreakable unit. Since greedy_wrap
    # hard-breaks oversized words, that unit is a single character.
    floor = max(math.ceil(measure(ch)) for ch in text if not ch.isspace())
    low, high = max(1, floor), int(max_width)
    best = baseline
    while low <= high:
        mid = (low + high) // 2
        candidate = greedy_wrap(text, measure, mid)
        if len(candidate) <= len(baseline):
            best = candidate
            high = mid - 1
        else:
            low = mid + 1
    return best


def raggedness(lines, measure):
    """
    Population standard deviation of line widths -- lower is blockier.

    Every line counts, including the last. That is deliberate: greedy wrap's
    signature failure is packing each line to the maximum and stranding a
    near-empty final line, and excluding that line hides precisely the defect
    balance_wrap exists to fix. Returns 0.0 when there is nothing to compare.
    """
    widths = [measure(line) for line in lines]
    if len(widths) < 2:
        return 0.0
    mean = sum(widths) / len(widths)
    return math.sqrt(sum((w - mean) ** 2 for w in widths) / len(widths))


# ---------------------------------------------------------------------------
# 3. Layout
# ---------------------------------------------------------------------------

def block_height(num_lines):
    """Ink height of the whole block: verse lines, gap, then reference line."""
    return (num_lines - 1) * LINE_HEIGHT + REF_GAP + REF_CAP_HEIGHT


def block_top(num_lines):
    """
    Ink top of the first verse line.

    The block is centered vertically, then snapped to the reference deck's
    72px grid. Snapping is what the reference deck does -- an unsnapped centre
    would sit up to half a line off from every slide the operator produced.
    """
    ideal = (SLIDE_HEIGHT - block_height(num_lines)) / 2
    steps = round((ideal - GRID_ORIGIN) / LINE_HEIGHT)
    return GRID_ORIGIN + steps * LINE_HEIGHT


def block_fits(num_lines):
    """Whether a block of this many verse lines stays within the safe area."""
    top = block_top(num_lines)
    return (
        top >= MIN_TOP_MARGIN
        and top + block_height(num_lines) <= SLIDE_HEIGHT - MIN_BOTTOM_MARGIN
    )


def max_lines():
    """Largest verse line count that still fits the safe area."""
    n = 1
    while block_fits(n + 1):
        n += 1
    return n


# ---------------------------------------------------------------------------
# 4. Rendering
# ---------------------------------------------------------------------------

@lru_cache(maxsize=4)
def make_gradient(width=SLIDE_WIDTH, height=SLIDE_HEIGHT):
    """
    The black left-hand scrim: opaque at the left edge, fully transparent
    by about 60% across. Interpolated from GRADIENT_PROFILE.

    Cached -- it is identical for every slide in a run, and rebuilding it per
    slide dominated generation time.
    """
    row = Image.new('RGBA', (width, 1))
    pixels = row.load()
    last = len(GRADIENT_PROFILE) - 1
    for x in range(width):
        pos = x / (width - 1) * last          # x mapped onto profile indices
        i = min(int(pos), last)
        j = min(i + 1, last)
        frac = pos - i
        alpha = GRADIENT_PROFILE[i] * (1 - frac) + GRADIENT_PROFILE[j] * frac
        pixels[x, 0] = (0, 0, 0, round(alpha))
    return row.resize((width, height))


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
    font: object
    kerning: object = None


class _Kerning(NamedTuple):
    pairs: dict        # (glyph name, glyph name) -> advance delta, font units
    upem: int          # units per em, for scaling to pixels
    cmap: dict         # codepoint -> glyph name


@lru_cache(maxsize=4)
def _load_kerning(path, index):
    """
    Pair kerning from the font's GPOS 'kern' feature, or None.

    Only LookupType 2 (pair adjustment) is read, which is all Neue Haas uses
    and all that matters for Latin text. Contextual kerning, and the legacy
    'kern' table that older fonts such as Helvetica Neue carry instead, are
    both ignored -- they would change metrics the layout constants were fitted
    against without measurably improving the match.
    """
    try:
        from fontTools.ttLib import TTCollection, TTFont
    except ImportError:
        return None
    if not path or not os.path.exists(path):
        return None
    try:
        tt = (TTCollection(path).fonts[index] if path.lower().endswith('.ttc')
              else TTFont(path))
        if 'GPOS' not in tt:
            return None
        gpos = tt['GPOS'].table
        wanted = set()
        for record in gpos.FeatureList.FeatureRecord:
            if record.FeatureTag == 'kern':
                wanted.update(record.Feature.LookupListIndex)

        pairs = {}
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
        return _Kerning(pairs, tt['head'].unitsPerEm, tt.getBestCmap())
    except Exception:
        return None


def _read_pairs_by_glyph(sub, pairs):
    """PairPos format 1: explicit first-glyph -> second-glyph adjustments."""
    for first, pairset in zip(sub.Coverage.glyphs, sub.PairSet):
        for record in pairset.PairValueRecord:
            delta = getattr(record.Value1, 'XAdvance', 0)
            if delta:
                pairs[(first, record.SecondGlyph)] = delta


def _read_pairs_by_class(sub, pairs):
    """
    PairPos format 2: adjustments between glyph *classes*.

    Expanded to explicit pairs once, at load, so lookup stays a dict hit per
    character. Format 1 wins on conflict, matching OpenType subtable order.
    """
    by_first = {}
    for glyph in sub.Coverage.glyphs:
        by_first.setdefault(sub.ClassDef1.classDefs.get(glyph, 0), []).append(glyph)
    by_second = {}
    for glyph, cls in sub.ClassDef2.classDefs.items():
        by_second.setdefault(cls, []).append(glyph)

    for i, class1 in enumerate(sub.Class1Record):
        if i not in by_first:
            continue
        for j, class2 in enumerate(class1.Class2Record):
            delta = getattr(class2.Value1, 'XAdvance', 0)
            if not delta:
                continue
            for first in by_first[i]:
                for second in by_second.get(j, ()):
                    pairs.setdefault((first, second), delta)


def kern_width(text, kerning, size=FONT_SIZE):
    """Total kerning adjustment for `text`, in pixels. Negative tightens."""
    if kerning is None or len(text) < 2:
        return 0.0
    names = [kerning.cmap.get(ord(ch)) for ch in text]
    units = sum(kerning.pairs.get(pair, 0)
                for pair in zip(names, names[1:])
                if pair[0] and pair[1])
    return units * size / kerning.upem


#: PIL picks its layout engine at import: Raqm when libraqm is present in the
#: Pillow build, BASIC otherwise. That choice is not cosmetic here. Raqm applies
#: GPOS itself, and this module applies pair kerning by hand precisely BECAUSE
#: basic layout ignores GPOS -- so under Raqm every kerned pair is adjusted
#: twice and measurement stops describing what is drawn.
#:
#: Measured: macOS wheels here have no libraqm, ubuntu-24.04's do, and the same
#: commit rendered 'AVATAR, Yesterday we saw' 26px narrower than
#: text_measurer() predicted on the runner while agreeing exactly on this
#: machine. Every layout constant in this file was fitted under basic layout,
#: so that is pinned rather than inherited -- a render that changes with a
#: transitive C library nobody declared is the same class of failure as the
#: font fallback above.
_LAYOUT = ImageFont.Layout.BASIC


@lru_cache(maxsize=4)
def load_fonts(size=FONT_SIZE):
    """
    (verse_face, reference_face), each a Face.

    Falls back to PIL's bitmap default only if no configured font is installed,
    which makes output non-reference-matching but keeps the pipeline runnable.
    """
    if FONT_PATH and os.path.exists(FONT_PATH):
        try:
            return (
                Face(ImageFont.truetype(FONT_PATH, size, index=FONT_INDEX_REGULAR,
                                        layout_engine=_LAYOUT),
                     _load_kerning(FONT_PATH, FONT_INDEX_REGULAR)),
                Face(ImageFont.truetype(FONT_PATH_MEDIUM, size,
                                        index=FONT_INDEX_MEDIUM,
                                        layout_engine=_LAYOUT),
                     _load_kerning(FONT_PATH_MEDIUM, FONT_INDEX_MEDIUM)),
            )
        except OSError:
            pass
    fallback = Face(ImageFont.load_default())
    return fallback, fallback


def _as_face(font):
    """Accept a Face or a bare PIL font, so callers may pass either."""
    return font if isinstance(font, Face) else Face(font)


def text_measurer(font, scale=None):
    """
    A `measure(str) -> float` callable for the wrap functions.

    Widths are reported in *rendered* space, i.e. kerned and then scaled by
    HORIZONTAL_SCALE, so wrapping and TEXT_BOX_WIDTH both talk about the pixels
    that end up on the slide rather than the font's bare advance widths.
    """
    face = _as_face(font)
    scale = HORIZONTAL_SCALE if scale is None else scale
    scratch = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
    size = getattr(face.font, 'size', FONT_SIZE)

    def measure(text):
        natural = scratch.textlength(text, font=face.font)
        return (natural + kern_width(text, face.kerning, size)) * scale

    return measure


def find_overlong_reference(reference):
    """
    Report a reference line too wide to sit on legible background.

    Lives with the other find_* checks conceptually but has to be defined here
    because it needs font metrics. Returns a list of (kind, detail) pairs so it
    composes with find_artifacts and find_unrenderable in main.validate.
    """
    _, ref_face = load_fonts()
    width = text_measurer(ref_face)(reference)
    if width <= REF_MAX_WIDTH:
        return []
    return [('reference-too-wide', f'{width:.0f}px > {REF_MAX_WIDTH}px')]


def _ink_offset(font):
    """
    Distance from PIL's draw origin down to the top of capital ink.

    PIL anchors text at the ascender, but every constant here was measured
    from ink, so drawing needs this correction.
    """
    return font.getbbox('H')[1]


def _draw_line(draw, left, top, text, face):
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
        draw.text((left, top), text, fill=(255, 255, 255, 255), font=face.font)
        return

    size = getattr(face.font, 'size', FONT_SIZE)
    names = [face.kerning.cmap.get(ord(ch)) for ch in text]
    x = float(left)
    for i, ch in enumerate(text):
        draw.text((x, top), ch, fill=(255, 255, 255, 255), font=face.font)
        x += draw.textlength(ch, font=face.font)
        if i + 1 < len(text) and names[i] and names[i + 1]:
            x += (face.kerning.pairs.get((names[i], names[i + 1]), 0)
                  * size / face.kerning.upem)


def _draw_text(img, left, ink_top, text, font, scale=None):
    """
    Draw one line with its ink top at `ink_top`, condensed by `scale`.

    Only the horizontal axis is scaled, so cap height, baseline and line
    spacing are untouched -- the same thing Photoshop's HorizontalScale does.
    At scale 1.0 the text is drawn straight onto the slide; otherwise it goes
    to its own transparent layer, is resampled, then composited, because PIL
    cannot scale glyphs while drawing.
    """
    face = _as_face(font)
    scale = HORIZONTAL_SCALE if scale is None else scale
    top = ink_top - _ink_offset(face.font)

    if scale == 1.0:
        _draw_line(ImageDraw.Draw(img), left, top, text, face)
        return

    ascent, descent = face.font.getmetrics()
    scratch = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
    natural = scratch.textlength(text, font=face.font)
    natural += kern_width(text, face.kerning, getattr(face.font, 'size', FONT_SIZE))
    width, height = max(1, math.ceil(natural) + 4), ascent + descent + 4

    layer = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    _draw_line(ImageDraw.Draw(layer), 0, 0, text, face)
    layer = layer.resize((max(1, round(width * scale)), height), Image.LANCZOS)
    img.alpha_composite(layer, (left, top))


def layout_slide(verse_text, reference, font=None, max_width=TEXT_BOX_WIDTH):
    """
    Work out the finished geometry without drawing anything.

    Returns (lines, line_tops, reference_top) where the tops are ink tops.
    Raises SlideOverflowError if the verse cannot fit the safe area.
    """
    verse_font, _ = load_fonts() if font is None else (font, font)
    measure = text_measurer(verse_font)

    lines = balance_wrap(verse_text, measure, max_width)
    if not lines:
        raise EmptyVerseError(f'{reference}: no renderable text')
    if not block_fits(len(lines)):
        raise SlideOverflowError(
            f'{reference}: needs {len(lines)} lines, '
            f'at most {max_lines()} fit on a slide'
        )

    top = block_top(len(lines))
    line_tops = [top + i * LINE_HEIGHT for i in range(len(lines))]
    return lines, line_tops, line_tops[-1] + REF_GAP


def compose_slide(verse_text, reference, max_width=TEXT_BOX_WIDTH):
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
        _draw_text(img, LEFT_MARGIN, top, line, verse_font)
    _draw_text(img, LEFT_MARGIN, ref_top, reference, ref_font)
    return img


def render_slide(verse_text, reference, output_path, max_width=TEXT_BOX_WIDTH):
    """Compose a slide and write it to `output_path` as an RGBA TIFF."""
    compose_slide(verse_text, reference, max_width=max_width).save(output_path, 'TIFF')
    return output_path


_REF_PARTS_RE = re.compile(r'^(.*?)(\d+):(\d+)')


def slide_filename(reference, index):
    """
    Sortable, self-describing filename derived from the reference.

    "John 17:1 ESV" -> "John_17_001.tif". Falls back to the sequence number
    if the reference does not parse.
    """
    match = _REF_PARTS_RE.match(reference)
    if not match:
        return f'verse_{index:03d}.tif'
    book = match.group(1).strip().replace(' ', '_')
    return f'{book}_{match.group(2)}_{int(match.group(3)):03d}.tif'


def generate_slides(verses, output_dir='./slides', formatted=False):
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
    if not formatted:
        verses = format_verses(verses)

    os.makedirs(output_dir, exist_ok=True)
    paths = []
    for index, (text, ref) in enumerate(verses, 1):
        if not text.strip():
            continue
        path = os.path.join(output_dir, slide_filename(ref, index))
        render_slide(text, ref, path)
        paths.append(path)
    return paths
