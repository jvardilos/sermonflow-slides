"""
What is bold, and what is not.

    point slide      text       BOLD
    verse slide      verse text NOT bold
    verse slide      reference  BOLD

Pinned three ways, because each alone can be fooled: the weight names on the
planned draw ops (what the layouts decided), the weight names' own family (so
"bold" cannot quietly mean Medium), and the ink actually rendered (so a font
table that mapped two names to one file would still fail).
"""

import pytest

import sermonflow as slidegen
from sermonflow.layouts.base import DrawOp, Placed

SAMPLE = "Handgloves"
BOLD_FAMILIES = ("bold", "black")


def is_bold(weight: str) -> bool:
    return weight.startswith(BOLD_FAMILIES)


def verse_ops() -> tuple[DrawOp, ...]:
    return slidegen.plan_verse("For God so loved the world.", "John 3:16 ESV").ops


def point_ops() -> dict[str, list[DrawOp]]:
    points = ["Grace comes first.", "Faith receives it."]
    return {
        "rolling": [op for p in slidegen.plan_rolling(points) for op in p.ops],
        "centered": [op for p in slidegen.plan_centered(points) for op in p.ops],
        "stacked": [op for p in slidegen.plan_stacked(points) for op in p.ops],
    }


class TestPlannedWeights:
    def test_verse_text_is_not_bold(self):
        *verse_lines, _ = verse_ops()
        assert verse_lines
        assert not any(is_bold(op.weight) for op in verse_lines)

    def test_reference_is_bold(self):
        *_, reference = verse_ops()
        assert reference.text == "John 3:16 ESV"
        assert is_bold(reference.weight)

    @pytest.mark.parametrize("style", ["rolling", "centered", "stacked"])
    def test_every_point_line_is_bold(self, style):
        ops = point_ops()[style]
        assert ops
        assert all(is_bold(op.weight) for op in ops), style

    def test_constants_agree_with_the_ops(self):
        *verse_lines, reference = verse_ops()
        assert {op.weight for op in verse_lines} == {slidegen.VERSE_WEIGHT}
        assert reference.weight == slidegen.REFERENCE_WEIGHT
        assert not is_bold(slidegen.VERSE_WEIGHT)
        assert is_bold(slidegen.REFERENCE_WEIGHT)
        assert is_bold(slidegen.POINT_WEIGHT)


def ink(weight: str) -> int:
    """Count of bright (text) pixels when SAMPLE is drawn in `weight`."""
    img = slidegen.compose(
        Placed((DrawOp(SAMPLE, slidegen.LEFT_MARGIN, 300, weight),), "sample")
    )
    pixels = img.convert("RGB").load()
    assert pixels is not None
    return sum(
        1
        for x in range(img.width)
        for y in range(250, 450)
        if min(pixels[x, y]) > 200
    )


class TestRenderedInk:
    """
    Bold has to *look* bold, not just be named so. Measured against the real
    Bold face: Medium inks ~84% of it, Bold Italic ~95%, Roman ~55%, so 90% and
    60% separate the three roles cleanly.
    """

    def test_reference_inks_like_bold(self):
        *_, reference = verse_ops()
        assert ink(reference.weight) >= 0.9 * ink("bold")

    def test_verse_text_inks_nothing_like_bold(self):
        verse = verse_ops()[0]
        assert ink(verse.weight) <= 0.6 * ink("bold")

    @pytest.mark.parametrize("style", ["rolling", "centered", "stacked"])
    def test_points_ink_like_bold(self, style):
        point = point_ops()[style][0]
        assert ink(point.weight) >= 0.9 * ink("bold")
