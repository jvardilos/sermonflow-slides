"""
Point slides: geometry, both styles, and the registry that holds them.

The golden numbers here are the ones measured off template/point-templates/ --
the first ink top, the 144px rolling step, the grid every centered block lands
on. They are written as literals rather than derived from the constants they
pin, so a change to a constant fails a test instead of quietly moving the deck.

The templates themselves are not committed (they are artwork, and heavy), so
the tests that want a pixel comparison skip when the folder is absent and the
rest of the file still covers the geometry.
"""

import os

import numpy as np
import pytest
from PIL import Image

import sermonflow as slidegen

TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "template",
    "point-templates",
)

#: The five statements the numbered rolling templates are set with, in order.
ROLLING_POINTS = [
    "The Sovereignty of Christ.",
    'Jesus as the Divine "I AM".',
    "Jesus the Good Shepherd.",
    "The Atonement.",
    "The Kingdom of God.",
]

#: Ink tops of those five lines, measured from #5.tif.
ROLLING_TOPS = [197, 341, 485, 629, 773]


def ink_tops(placed):
    """Ink top of every draw op on a planned slide."""
    return [op.ink_top for op in placed.ops]


def has_templates():
    return os.path.isdir(TEMPLATE_DIR)


needs_templates = pytest.mark.skipif(
    not has_templates(), reason="reference point templates not present"
)


class TestRollingGeometry:
    def test_one_slide_per_point(self):
        deck = slidegen.plan_rolling(ROLLING_POINTS)
        assert len(deck) == len(ROLLING_POINTS)

    def test_slide_n_shows_points_up_to_n(self):
        deck = slidegen.plan_rolling(ROLLING_POINTS)
        for i, placed in enumerate(deck, 1):
            assert [op.text for op in placed.ops] == ROLLING_POINTS[:i]

    def test_tops_match_the_reference_template(self):
        deck = slidegen.plan_rolling(ROLLING_POINTS)
        assert ink_tops(deck[-1]) == ROLLING_TOPS

    def test_a_point_never_moves_between_slides(self):
        # The whole reveal effect depends on this: adding point 5 must not
        # shift points 1-4 by a pixel.
        deck = slidegen.plan_rolling(ROLLING_POINTS)
        for i, placed in enumerate(deck):
            assert ink_tops(placed) == ROLLING_TOPS[: i + 1]

    def test_step_is_two_line_heights(self):
        assert slidegen.ROLLING_STEP == 2 * slidegen.LINE_HEIGHT == 144

    def test_starts_at_the_shared_grid_origin(self):
        deck = slidegen.plan_rolling(["One."])
        assert ink_tops(deck[0]) == [slidegen.GRID_ORIGIN]

    def test_wrapped_point_keeps_its_gap(self):
        # A point that needs two lines pushes the next one down by its extra
        # line, not into it.
        long_point = "The point that will not fit on one line " * 2
        deck = slidegen.plan_rolling([long_point, "After."])
        first = slidegen.wrap_point(long_point)
        assert len(first) > 1
        tops = ink_tops(deck[-1])
        assert tops[len(first)] - tops[len(first) - 1] == slidegen.ROLLING_STEP

    def test_too_many_points_overflow(self):
        with pytest.raises(slidegen.SlideOverflowError):
            slidegen.plan_rolling([f"Point number {i}." for i in range(12)])

    def test_overflow_message_names_the_safe_area(self):
        with pytest.raises(slidegen.SlideOverflowError) as exc:
            slidegen.plan_rolling([f"Point number {i}." for i in range(12)])
        assert "safe area" in str(exc.value)


class TestCenteredGeometry:
    @pytest.mark.parametrize("num_lines,expected", [(1, 485), (2, 485), (4, 413)])
    def test_tops_match_the_reference_templates(self, num_lines, expected):
        assert slidegen.centered_top(num_lines) == expected

    def test_lands_on_the_shared_grid(self):
        for n in range(1, 8):
            offset = slidegen.centered_top(n) - slidegen.GRID_ORIGIN
            assert offset % slidegen.LINE_HEIGHT == 0

    def test_sits_a_little_above_true_centre(self):
        # Centering the cap box rather than the full ink box is what lifts a
        # short statement off the middle of the canvas.
        top = slidegen.centered_top(1)
        centre = top + slidegen.CAP_HEIGHT / 2
        assert 0 < slidegen.SLIDE_HEIGHT / 2 - centre < slidegen.LINE_HEIGHT

    def test_one_slide_per_point_no_accumulation(self):
        deck = slidegen.plan_centered(["First.", "Second."])
        assert len(deck) == 2
        assert [op.text for op in deck[0].ops] == ["First."]
        assert [op.text for op in deck[1].ops] == ["Second."]

    def test_uses_the_same_centring_rule_as_a_verse_block(self):
        # Both slide types go through snap_top, so they cannot drift apart.
        for n in range(1, 6):
            height = (n - 1) * slidegen.LINE_HEIGHT + slidegen.CAP_HEIGHT
            assert slidegen.centered_top(n) == slidegen.snap_top(height)


class TestPointTypography:
    def test_set_in_medium_italic(self):
        placed = slidegen.plan_centered(["A statement."])[0]
        assert {op.weight for op in placed.ops} == {"medium-italic"}
        assert slidegen.POINT_WEIGHT == "medium-italic"

    def test_left_margin_matches_the_verse_deck(self):
        placed = slidegen.plan_rolling(ROLLING_POINTS)[-1]
        assert {op.left for op in placed.ops} == {slidegen.LEFT_MARGIN}

    def test_wraps_wider_than_the_verse_box(self):
        # Measured: point lines in the templates run out to the scrim's
        # legible limit, past where a verse would have broken.
        assert slidegen.POINT_BOX_WIDTH == slidegen.MAX_TEXT_WIDTH
        assert slidegen.POINT_BOX_WIDTH > slidegen.TEXT_BOX_WIDTH

    def test_no_line_exceeds_the_box(self):
        measure = slidegen.text_measurer(slidegen.load_face(slidegen.POINT_WEIGHT))
        for placed in slidegen.plan_rolling(ROLLING_POINTS):
            for op in placed.ops:
                assert measure(op.text) <= slidegen.POINT_BOX_WIDTH

    def test_no_reference_line(self):
        # A point slide is exactly its own text -- nothing is appended.
        placed = slidegen.plan_centered(["A statement."])[0]
        assert [op.text for op in placed.ops] == ["A statement."]


class TestPointStyleRegistry:
    def test_both_styles_registered(self):
        assert set(slidegen.point_style_names()) == {"rolling", "centered"}

    def test_default_is_registered(self):
        assert slidegen.DEFAULT_POINT_STYLE in slidegen.POINT_STYLES

    def test_every_style_has_a_summary(self):
        # The summaries are what the CLI help and the MCP tool description are
        # built from, so an unexplained style is a bug.
        for style in slidegen.POINT_STYLES.values():
            assert len(style.summary) > 20

    def test_unknown_style_names_the_valid_ones(self):
        with pytest.raises(ValueError) as exc:
            slidegen.get_point_style("sideways")
        assert "rolling" in str(exc.value) and "centered" in str(exc.value)

    def test_lookup_returns_the_planner(self):
        assert slidegen.get_point_style("rolling").plan is slidegen.plan_rolling


class TestRenderPoints:
    def test_renders_one_file_per_slide(self, tmp_path):
        paths = slidegen.generate_points(
            ROLLING_POINTS[:2], output_dir=str(tmp_path), style="rolling"
        )
        assert len(paths) == 2
        assert all(os.path.exists(p) for p in paths)

    def test_filenames_sort_into_reveal_order(self, tmp_path):
        paths = slidegen.generate_points(ROLLING_POINTS, output_dir=str(tmp_path))
        assert [os.path.basename(p) for p in paths] == sorted(
            os.path.basename(p) for p in paths
        )

    def test_output_is_a_full_canvas(self, tmp_path):
        path = slidegen.generate_points(["One."], output_dir=str(tmp_path))[0]
        with Image.open(path) as img:
            assert img.size == (slidegen.SLIDE_WIDTH, slidegen.SLIDE_HEIGHT)
            assert img.mode == "RGBA"

    def test_blank_points_are_dropped(self, tmp_path):
        paths = slidegen.generate_points(
            ["One.", "   ", "Two."], output_dir=str(tmp_path)
        )
        assert len(paths) == 2

    def test_all_blank_raises(self):
        with pytest.raises(slidegen.EmptyVerseError):
            slidegen.plan_points(["", "  "])

    def test_dry_run_reports_overflow_without_a_traceback(self, capsys):
        # An operator running --dry-run to check a deck before a service gets
        # the reason, not a stack trace.
        from sermonflow.cli import build_points

        with pytest.raises(SystemExit) as exc:
            build_points([f"Point number {i}." for i in range(12)], dry_run=True)
        assert "safe area" in capsys.readouterr().err
        assert "cannot lay these points out" in str(exc.value)

    def test_stem_prefix_is_honoured(self, tmp_path):
        paths = slidegen.generate_points(
            ["One."], output_dir=str(tmp_path), stem="outline"
        )
        assert os.path.basename(paths[0]) == "outline_001.tif"


@needs_templates
class TestAgainstTheTemplates:
    """Pixel comparisons against the artwork the constants were measured from."""

    def _ink_rows(self, arr):
        """Ink top of each text line in an RGBA array, as the measurement did."""
        ink = (arr[:, :, 0] > 140) & (arr[:, :, 3] > 140)
        rows = np.where(ink.any(axis=1))[0]
        tops, previous = [], None
        for row in rows:
            if previous is None or row > previous + 1:
                tops.append(int(row))
            previous = row
        return tops

    def test_rolling_matches_the_template_ink(self):
        placed = slidegen.plan_rolling(ROLLING_POINTS)[-1]
        ours = np.array(slidegen.compose(placed)).astype(int)
        theirs = np.array(
            Image.open(os.path.join(TEMPLATE_DIR, "#5.tif")).convert("RGBA")
        ).astype(int)
        # Sub-pixel kerning drift along a line leaves thin edges differing, so
        # this is an ink-coverage comparison, not a bit-for-bit one.
        differing = (np.abs(ours - theirs).max(axis=2) > 32).mean()
        assert differing < 0.02

    def test_centered_single_line_matches_the_template_top(self):
        placed = slidegen.plan_centered(["Jesus is Yahweh incarnate."])[0]
        ours = np.array(slidegen.compose(placed)).astype(int)
        theirs = np.array(
            Image.open(os.path.join(TEMPLATE_DIR, "Yahweh.tif")).convert("RGBA")
        ).astype(int)
        assert self._ink_rows(ours) == self._ink_rows(theirs)
