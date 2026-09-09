"""
Text normalization: the "light edits" that make a verse readable standing
alone on a screen.

Pure string work -- no font metrics, no PIL, no network. This is the layer
that must survive a retrieval-backend swap, which is why it lives here and not
in a provider: whether the raw verse came from a scraper, an API or a local
corpus, the same quote-carry, artifact-scrubbing and capitalization rules apply
before it reaches a slide.

Three separable steps, combined in `format_verses`:

  1. strip_artifacts  -- remove scrape residue, normalize whitespace and quotes
  2. apply_quote_carry -- quote each verse as if it stands alone on its slide
  3. capitalize_first_letter

Steps 1 and 3 are per-verse; step 2 is order-dependent across the whole
passage, which is why `format_verses` takes and returns the passage as a list.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

#: A single slide's worth of source: (verse_text, "Book Chapter:Verse VERSION").
Verse = tuple[str, str]

OPEN_QUOTE = "“"   # left double quotation mark
CLOSE_QUOTE = "”"  # right double quotation mark

# BibleGateway footnote markers: [a], [b], [12], and the occasional [aa].
_FOOTNOTE_MARKER_RE = re.compile(r"\[\s*[0-9a-zA-Z]{1,3}\s*\]")
# Cross-reference markers: (A), (BZ), (CAA). Restricted to short all-caps runs
# so a legitimate parenthetical is never eaten.
_CROSSREF_MARKER_RE = re.compile(r"\(\s*[A-Z]{1,3}\s*\)")
# A verse number left stranded at the head of the text, e.g. "16 They do not".
_LEADING_VERSENUM_RE = re.compile(r"^\s*\d{1,3}\s+(?=[\w‘“])")
_WHITESPACE_RE = re.compile(r"\s+")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:!?’”])")

_STRAIGHT_DOUBLE = '"'
_STRAIGHT_SINGLE = "'"
_CLOSING_CONTEXT = ",.;:!?’”)"


def normalize_quotes(text: str) -> str:
    """
    Convert straight quotes to typographic ones so the carry state machine
    has a single set of characters to reason about.

    A double quote closes if the character before it ends a word; otherwise it
    opens. A single quote is an apostrophe when it follows a word character.
    """
    out: list[str] = []
    for i, ch in enumerate(text):
        prev = text[i - 1] if i else ""
        if ch == _STRAIGHT_DOUBLE:
            closing = bool(prev) and (prev.isalnum() or prev in _CLOSING_CONTEXT)
            out.append(CLOSE_QUOTE if closing else OPEN_QUOTE)
        elif ch == _STRAIGHT_SINGLE:
            out.append("’" if prev.isalnum() else "‘")
        else:
            out.append(ch)
    return "".join(out)


def strip_artifacts(text: str) -> str:
    """
    Remove scrape residue that would otherwise show up on a slide, and
    normalize whitespace and quote characters.

    Only unambiguous edits happen here. Anything that *might* be legitimate
    verse content is left alone and reported by find_artifacts instead.
    """
    text = _FOOTNOTE_MARKER_RE.sub("", text)
    text = _CROSSREF_MARKER_RE.sub("", text)
    text = _LEADING_VERSENUM_RE.sub("", text)
    text = normalize_quotes(text)
    text = _WHITESPACE_RE.sub(" ", text)
    text = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)
    return text.strip()


def find_artifacts(text: str) -> list[tuple[str, str]]:
    """
    Report anything that looks like scrape residue or a typographic mistake.

    Returns a list of (kind, snippet) pairs, empty when the text is clean.
    Used as a validation pass by the CLI and asserted on in the tests -- it is
    the safety net for markers a future retrieval backend forgets to strip.
    """
    problems: list[tuple[str, str]] = []
    for match in _FOOTNOTE_MARKER_RE.finditer(text):
        problems.append(("footnote-marker", match.group()))
    for match in _CROSSREF_MARKER_RE.finditer(text):
        problems.append(("crossref-marker", match.group()))
    leading = _LEADING_VERSENUM_RE.match(text)
    if leading:
        problems.append(("leading-verse-number", leading.group().strip()))
    if _STRAIGHT_DOUBLE in text:
        problems.append(("straight-double-quote", _STRAIGHT_DOUBLE))
    if _STRAIGHT_SINGLE in text:
        problems.append(("straight-single-quote", _STRAIGHT_SINGLE))
    if "  " in text:
        problems.append(("double-space", "  "))
    if text != text.strip():
        problems.append(("edge-whitespace", repr(text[:1] + "..." + text[-1:])))
    for ch, name in (("\n", "newline"), ("\t", "tab"), ("\r", "carriage-return")):
        if ch in text:
            problems.append((name, repr(ch)))
    unbalanced = text.count(OPEN_QUOTE) - text.count(CLOSE_QUOTE)
    if abs(unbalanced) > 1:
        problems.append(("unbalanced-quotes", f"{unbalanced:+d}"))
    return problems


def apply_quote_carry(texts: Sequence[str]) -> list[str]:
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

    Takes a sequence and returns a list, because the rule is order-dependent.
    """
    out: list[str] = []
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


def capitalize_first_letter(text: str) -> str:
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


def format_verses(verses: Iterable[Verse]) -> list[Verse]:
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
