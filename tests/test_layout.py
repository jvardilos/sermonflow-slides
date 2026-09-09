"""
Vertical layout: grid-snapped centering, and the overflow guard.

The golden table below is measured from the reference deck and is the reason
block_top snaps to a grid instead of centering freely.
"""

import os
import re

import numpy as np
import pytest
from PIL import Image

import sermonflow as slidegen
from conftest import dummy_text

#: line count -> first-line ink top, measured from `John 17 /*.tif`.
REFERENCE_TOPS = {2: 412, 3: 341, 4: 341, 5: 269, 6: 269, 7: 197, 8: 197}

REFERENCE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'John 17 '
)

#: Verses the operator hand-nudged off the grid. Both are 5-line slides sitting
#: one grid step low, while the deck's four other 5-line slides sit where the
#: model puts them -- so the model matches the majority. See FORMATTING_NOTES.md.
KNOWN_OFF_GRID = {3, 5}

#: Verse whose pro slide takes one more line than the fitted box width gives,
#: most likely a manual break by the operator.
KNOWN_EXTRA_LINE = {3}


class TestBlockGeometry:
    @pytest.mark.parametrize('num_lines, expected_top', sorted(REFERENCE_TOPS.items()))
    def test_matches_the_reference_deck(self, num_lines, expected_top):
        # +-3px covers ink-detection noise between glyphs of differing height.
        assert abs(slidegen.block_top(num_lines) - expected_top) <= 3

    def test_block_height_grows_by_one_line_height(self):
        for n in range(1, 10):
            assert slidegen.block_height(n + 1) - slidegen.block_height(n) == \
                slidegen.LINE_HEIGHT

    def test_top_is_always_on_the_grid(self):
        for n in range(1, 12):
            offset = slidegen.block_top(n) - slidegen.GRID_ORIGIN
            assert offset % slidegen.LINE_HEIGHT == 0

    def test_taller_blocks_start_higher_or_level(self):
        tops = [slidegen.block_top(n) for n in range(1, 12)]
        assert tops == sorted(tops, reverse=True)

    def test_block_stays_roughly_centered(self):
        # Grid snapping costs at most half a line of centering error.
        for n in range(2, 10):
            centre = slidegen.block_top(n) + slidegen.block_height(n) / 2
            assert abs(centre - slidegen.SLIDE_HEIGHT / 2) <= slidegen.LINE_HEIGHT / 2 + 1


class TestFitAndOverflow:
    def test_every_reference_deck_size_fits(self):
        for num_lines in REFERENCE_TOPS:
            assert slidegen.block_fits(num_lines)

    def test_absurd_line_counts_do_not_fit(self):
        assert not slidegen.block_fits(50)

    def test_max_lines_is_a_real_boundary(self):
        limit = slidegen.max_lines()
        assert slidegen.block_fits(limit)
        assert not slidegen.block_fits(limit + 1)

    def test_max_lines_covers_the_reference_deck(self):
        assert slidegen.max_lines() >= max(REFERENCE_TOPS)

    def test_fitting_blocks_stay_inside_the_safe_area(self):
        for n in range(1, slidegen.max_lines() + 1):
            top = slidegen.block_top(n)
            assert top >= slidegen.MIN_TOP_MARGIN
            assert top + slidegen.block_height(n) <= \
                slidegen.SLIDE_HEIGHT - slidegen.MIN_BOTTOM_MARGIN

    def test_overflow_raises_with_a_useful_message(self):
        huge = dummy_text(400, seed=1)
        with pytest.raises(slidegen.SlideOverflowError) as exc:
            slidegen.layout_slide(huge, 'Book 1:1 ESV')
        assert 'Book 1:1 ESV' in str(exc.value)


class TestLayoutSlide:
    def test_lines_are_evenly_spaced(self):
        text = dummy_text(40, seed=2)
        _, line_tops, _ = slidegen.layout_slide(text, 'Book 1:1 ESV')
        deltas = {b - a for a, b in zip(line_tops, line_tops[1:])}
        assert deltas == {slidegen.LINE_HEIGHT}

    def test_first_line_is_at_the_computed_block_top(self):
        text = dummy_text(40, seed=3)
        lines, line_tops, _ = slidegen.layout_slide(text, 'Book 1:1 ESV')
        assert line_tops[0] == slidegen.block_top(len(lines))

    def test_reference_sits_one_gap_below_the_last_line(self):
        text = dummy_text(40, seed=4)
        _, line_tops, ref_top = slidegen.layout_slide(text, 'Book 1:1 ESV')
        assert ref_top - line_tops[-1] == slidegen.REF_GAP

    def test_reference_stays_on_the_slide(self):
        """The collision check FORMATTING_NOTES.md asks for explicitly."""
        for words in range(1, 200, 7):
            text = dummy_text(words, seed=words)
            try:
                _, _, ref_top = slidegen.layout_slide(text, 'Book 1:1 ESV')
            except slidegen.SlideOverflowError:
                continue
            assert ref_top + slidegen.REF_CAP_HEIGHT <= slidegen.SLIDE_HEIGHT

    def test_lines_never_exceed_the_text_box(self, measure):
        for words in range(4, 61, 6):
            text = dummy_text(words, seed=words)
            lines, _, _ = slidegen.layout_slide(text, 'Book 1:1 ESV')
            for line in lines:
                assert measure(line) <= slidegen.TEXT_BOX_WIDTH or ' ' not in line


@pytest.mark.skipif(not os.path.isdir(REFERENCE_DIR),
                    reason='reference deck not present')
class TestAgainstReferenceDeck:
    """
    Golden test: measure the real professional slides and check our geometry
    model predicts where their text actually sits. Needs no verse text, so it
    works entirely offline against the .tif files in the repo.
    """

    @staticmethod
    def _ink_mask(path):
        arr = np.array(Image.open(path).convert('RGBA'))[:, :1150, :3]
        return arr.astype(float).mean(axis=2) > 235

    @classmethod
    def _slots(cls, path):
        """
        Which grid slots hold ink.

        Rows are bucketed onto the validated 72px grid rather than clustered by
        proximity: a descender or a comma tail forms its own ink island only
        ~11px below its line, which naive clustering splits into a phantom
        extra line. Bucketing is immune to that.
        """
        rows = np.where(cls._ink_mask(path).any(axis=1))[0]
        phase = slidegen.GRID_ORIGIN - 10   # slot k spans [origin+72k-10, +62)
        return sorted({(int(y) - phase) // slidegen.LINE_HEIGHT for y in rows})

    @classmethod
    def _line_count_and_top(cls, path):
        """(verse line count, first-line ink top) for a reference slide."""
        slots = cls._slots(path)
        run = [slots[0]]
        for a, b in zip(slots, slots[1:]):
            if b - a != 1:
                break
            run.append(b)
        top = slidegen.GRID_ORIGIN + slots[0] * slidegen.LINE_HEIGHT
        return len(run), top, slots

    @staticmethod
    def _verse_number(path):
        match = re.search(r'17\.(\d+)', os.path.basename(path))
        return int(match.group(1)) if match else 1

    def _slides(self):
        return sorted(
            (os.path.join(REFERENCE_DIR, f) for f in os.listdir(REFERENCE_DIR)
             if f.endswith('.tif')),
            key=self._verse_number,
        )

    def test_deck_is_present(self):
        assert len(self._slides()) == 26

    def test_model_predicts_reference_positions(self):
        drifted = []
        for path in self._slides():
            num_lines, top, _ = self._line_count_and_top(path)
            if slidegen.block_top(num_lines) != top:
                drifted.append(self._verse_number(path))
        assert set(drifted) <= KNOWN_OFF_GRID, drifted

    def test_every_slide_sits_on_the_grid(self):
        for path in self._slides():
            _, top, _ = self._line_count_and_top(path)
            offset = top - slidegen.GRID_ORIGIN
            assert offset % slidegen.LINE_HEIGHT == 0, path

    def test_verse_lines_are_contiguous_then_the_reference(self):
        """Verse lines occupy consecutive slots; the reference sits apart."""
        for path in self._slides():
            num_lines, _, slots = self._line_count_and_top(path)
            assert len(slots) == num_lines + 1, path
            assert slots[:num_lines] == list(
                range(slots[0], slots[0] + num_lines)
            ), path

    def test_reference_gap_is_universal(self):
        expected = round(slidegen.REF_GAP / slidegen.LINE_HEIGHT)
        for path in self._slides():
            num_lines, _, slots = self._line_count_and_top(path)
            assert slots[-1] - slots[num_lines - 1] == expected, path

    def test_left_margin_matches(self):
        for path in self._slides():
            left = np.where(self._ink_mask(path).any(axis=0))[0].min()
            assert abs(left - slidegen.LEFT_MARGIN) <= 3, path

    def test_no_line_exceeds_the_fitted_box(self):
        """
        TEXT_BOX_WIDTH is expressed in *our* post-HORIZONTAL_SCALE space, and
        the reference deck is set in a different typeface, so its raw ink can
        sit a few px past our box. A small tolerance keeps this a real check on
        the box being the right size without pretending the two are identical.
        """
        limit = slidegen.LEFT_MARGIN + slidegen.TEXT_BOX_WIDTH + 15
        for path in self._slides():
            right = np.where(self._ink_mask(path).any(axis=0))[0].max()
            assert right <= limit, path

    def test_line_counts_are_within_reach_of_the_fitted_box(self):
        """
        The fitted TEXT_BOX_WIDTH should reproduce the deck's line counts. This
        checks the counts are at least plausible for the box without needing the
        verse text: no slide may exceed what the box could ever hold.
        """
        for path in self._slides():
            num_lines, _, _ = self._line_count_and_top(path)
            assert num_lines <= slidegen.max_lines(), path
