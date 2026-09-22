"""
Line breaking and "blockiness".

FORMATTING_NOTES.md section 3: greedy wrap packs every line full and strands
the remainder on a near-empty last line. balance_wrap fixes that without
costing a line.

Everything here takes a `measure` callable (str -> width) rather than a font,
so it needs font metrics but not a canvas, and is cheap to test exhaustively
with an exact synthetic measure.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

#: A width function: report the rendered width of a run of text, in pixels.
Measure = Callable[[str], float]


def break_long_word(word: str, measure: Measure, max_width: float) -> list[str]:
    """
    Split a word too wide for the box into box-width chunks.

    Character-level, no hyphenation: this exists for junk tokens (a pasted
    hash, a URL) that would otherwise be drawn straight off the canvas. A
    single character wider than the box is emitted alone so this always makes
    progress.
    """
    chunks: list[str] = []
    current = ""
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


def greedy_wrap(text: str, measure: Measure, max_width: float) -> list[str]:
    """
    Classic fill-as-you-go wrap: the baseline balance_wrap measures against.

    A word wider than the box is hard-broken rather than left to overflow, so
    no line ever runs off the slide. See break_long_word.
    """
    lines: list[str] = []
    current = ""
    for word in text.split():
        if measure(word) > max_width:
            if current:
                lines.append(current)
            chunks = break_long_word(word, measure, max_width)
            lines.extend(chunks[:-1])
            current = chunks[-1]
            continue
        candidate = f"{current} {word}" if current else word
        if not current or measure(candidate) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def balance_wrap(text: str, measure: Measure, max_width: float) -> list[str]:
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


def raggedness(lines: Sequence[str], measure: Measure) -> float:
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


# ============================================================================
# Enhanced: Widow/orphan avoidance
# ============================================================================


def widow_penalty(lines: Sequence[str], widow_threshold: int = 4) -> float:
    """
    Penalize widow words (short words stranded at line ends).

    A widow is a word at the end of a line (excluding final line) that is
    shorter than widow_threshold characters. Returns a penalty score: 0 if no
    widows, higher if there are many.
    """
    penalty = 0.0
    for line in lines[:-1]:  # exclude final line, which is expected to be short
        words = line.split()
        if words:
            last_word = words[-1].rstrip(".,;:!?\"'")
            # Penalize short words; shorter ones get worse penalty
            if len(last_word) < widow_threshold:
                penalty += 50.0 / (len(last_word) + 1)
    return penalty


def widow_aware_wrap(
    text: str,
    measure: Measure,
    max_width: float,
    widow_threshold: int = 4,
) -> list[str]:
    """
    Balance wrap + widow avoidance penalty.

    Same as balance_wrap but penalizes breaking that leaves short words
    stranded at line ends. The binary search now optimizes for a combined score
    of raggedness + widow penalty, rather than width alone.

    Args:
        text: the text to wrap
        measure: width function
        max_width: maximum line width
        widow_threshold: words < this many characters are considered widows

    Returns wrapped lines with widow avoidance applied.
    """
    baseline = greedy_wrap(text, measure, max_width)
    if len(baseline) <= 1:
        return baseline

    floor = max(math.ceil(measure(ch)) for ch in text if not ch.isspace())
    low, high = max(1, floor), int(max_width)
    best = baseline
    best_score = raggedness(baseline, measure) + widow_penalty(
        baseline, widow_threshold
    )

    while low <= high:
        mid = (low + high) // 2
        candidate = greedy_wrap(text, measure, mid)
        if len(candidate) <= len(baseline):
            score = raggedness(candidate, measure) + widow_penalty(
                candidate, widow_threshold
            )
            if score < best_score:
                best = candidate
                best_score = score
            high = mid - 1
        else:
            low = mid + 1
    return best


def composite_score(
    lines: Sequence[str],
    measure: Measure,
    widow_weight: float = 1.0,
    raggedness_weight: float = 1.0,
) -> dict[str, float]:
    """
    Comprehensive scoring: raggedness + widow penalty with weights.

    Returns a dict with breakdowns so designers can see trade-offs.
    Lower total score is better (more balanced, fewer widows).

    Args:
        lines: wrapped lines
        measure: width function
        widow_weight: multiplier for widow penalty
        raggedness_weight: multiplier for width variance

    Returns dict with 'total', 'raggedness', and 'widow_penalty' keys.
    """
    rag = raggedness(lines, measure)
    widow = widow_penalty(lines)
    total = (rag * raggedness_weight) + (widow * widow_weight)
    return {
        "total": total,
        "raggedness": rag,
        "widow_penalty": widow,
    }
