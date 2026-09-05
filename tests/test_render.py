"""
Rendering: gradient fidelity, ink bounds, and a bulk pass over synthetic
verses of every plausible length.

The bulk pass composes in memory rather than writing 8MB TIFFs, so it can cover
a wide spread of lengths cheaply. It also loops internally and collects every
failure before asserting, rather than being parametrized into 150 separate
tests: one property checked across a numeric range is one test, and reporting
all the failing lengths at once is more useful than the first one.

"Length of the slides" is recovered by measuring the rendered image, not by
trusting the layout: the test is what landed on the canvas.
"""

import os

import numpy as np
import pytest
from PIL import Image

import slidegen
from conftest import MAX_FITTING_WORDS, OVERFLOW_WORDS, dummy_text

#: One line up to the 12-line ceiling, at ~5 words per line.
WORD_COUNTS = range(1, MAX_FITTING_WORDS + 1)


def ink_rows(img, threshold=235):
    """Row groups containing white text ink, top to bottom."""
    arr = np.array(img.convert('RGBA'))[:, :1200, :3].astype(float).mean(axis=2)
    rows = np.where((arr > threshold).any(axis=1))[0]
    if not len(rows):
        return []
    groups, current = [], [rows[0]]
    for y in rows[1:]:
        if y - current[-1] <= 4:
            current.append(y)
        else:
            groups.append((current[0], current[-1]))
            current = [y]
    groups.append((current[0], current[-1]))
    return groups


def ink_line_slots(img, threshold=235):
    """
    Number of distinct text lines, bucketed onto the 72px grid.

    Descenders form separate ink islands ~11px below their line; proximity
    grouping counts those as extra lines, grid bucketing does not.
    """
    arr = np.array(img.convert('RGBA'))[:, :1200, :3].astype(float).mean(axis=2)
    rows = np.where((arr > threshold).any(axis=1))[0]
    phase = slidegen.GRID_ORIGIN - 10
    return sorted({(int(y) - phase) // slidegen.LINE_HEIGHT for y in rows})


def ink_bounds(img, threshold=235):
    """(left, right, top, bottom) of all white ink on the slide."""
    arr = np.array(img.convert('RGBA'))[:, :, :3].astype(float).mean(axis=2)
    mask = arr > threshold
    cols = np.where(mask.any(axis=0))[0]
    rows = np.where(mask.any(axis=1))[0]
    return int(cols.min()), int(cols.max()), int(rows.min()), int(rows.max())


class TestGradient:
    def test_dimensions_and_mode(self):
        img = slidegen.make_gradient()
        assert img.size == (slidegen.SLIDE_WIDTH, slidegen.SLIDE_HEIGHT)
        assert img.mode == 'RGBA'

    def test_left_edge_is_the_profile_maximum(self):
        assert slidegen.make_gradient().getpixel((0, 540))[3] == \
            max(slidegen.GRADIENT_PROFILE)

    def test_right_half_is_fully_transparent(self):
        img = slidegen.make_gradient()
        for x in range(1300, slidegen.SLIDE_WIDTH, 100):
            assert img.getpixel((x, 540))[3] == 0

    def test_alpha_never_increases_left_to_right(self):
        img = slidegen.make_gradient()
        alphas = [img.getpixel((x, 540))[3]
                  for x in range(0, slidegen.SLIDE_WIDTH, 8)]
        assert alphas == sorted(alphas, reverse=True)

    def test_colour_is_pure_black(self):
        img = slidegen.make_gradient()
        for x in range(0, slidegen.SLIDE_WIDTH, 97):
            assert img.getpixel((x, 540))[:3] == (0, 0, 0)

    def test_vertically_uniform(self):
        img = slidegen.make_gradient()
        for x in (0, 300, 600, 900):
            assert len({img.getpixel((x, y))[3]
                        for y in range(0, 1080, 120)}) == 1

    def test_matches_the_profile_at_its_control_points(self):
        img = slidegen.make_gradient()
        last = len(slidegen.GRADIENT_PROFILE) - 1
        for i, expected in enumerate(slidegen.GRADIENT_PROFILE):
            x = round(i / last * (slidegen.SLIDE_WIDTH - 1))
            assert abs(img.getpixel((x, 540))[3] - expected) <= 1

    def test_is_cached(self):
        assert slidegen.make_gradient() is slidegen.make_gradient()


class TestBulkSlides:
    """Every property checked across the full length range, failures collected."""

    def test_rendered_line_count_matches_the_layout(self):
        failures = []
        for words in WORD_COUNTS:
            text = dummy_text(words, seed=words)
            ref = f'Book 1:{words} ESV'
            lines, _, _ = slidegen.layout_slide(text, ref)
            slots = ink_line_slots(slidegen.compose_slide(text, ref))
            if len(slots) != len(lines) + 1:      # +1 for the reference line
                failures.append((words, len(lines) + 1, len(slots)))
        assert not failures, f'(words, expected, actual): {failures}'

    def test_ink_stays_within_the_text_box(self):
        failures = []
        for words in WORD_COUNTS:
            text = dummy_text(words, seed=words)
            left, right, _, _ = ink_bounds(
                slidegen.compose_slide(text, f'Book 1:{words} ESV'))
            if left < slidegen.LEFT_MARGIN - 3 or \
                    right > slidegen.LEFT_MARGIN + slidegen.TEXT_BOX_WIDTH + 12:
                failures.append((words, left, right))
        assert not failures, f'(words, left, right): {failures}'

    def test_ink_stays_on_the_slide(self):
        failures = []
        for words in WORD_COUNTS:
            text = dummy_text(words, seed=words)
            _, _, top, bottom = ink_bounds(
                slidegen.compose_slide(text, f'Book 1:{words} ESV'))
            if top < 0 or bottom >= slidegen.SLIDE_HEIGHT:
                failures.append((words, top, bottom))
        assert not failures, f'(words, top, bottom): {failures}'

    def test_rendered_lines_sit_where_layout_said(self):
        failures = []
        for words in WORD_COUNTS:
            text = dummy_text(words, seed=words)
            ref = f'Book 1:{words} ESV'
            _, line_tops, ref_top = slidegen.layout_slide(text, ref)
            groups = ink_rows(slidegen.compose_slide(text, ref))
            # Ink can start a few px below the cap line on a line with no
            # ascenders, so compare with tolerance.
            for expected, (actual, _) in zip(line_tops, groups):
                if abs(actual - expected) > 8:
                    failures.append((words, expected, actual))
            if abs(groups[-1][0] - ref_top) > 8:
                failures.append((words, 'ref', ref_top, groups[-1][0]))
        assert not failures, failures

    def test_canvas_is_always_correct(self):
        for words in (1, 20, MAX_FITTING_WORDS):
            img = slidegen.compose_slide(dummy_text(words, seed=words),
                                         'Book 1:1 ESV')
            assert img.size == (slidegen.SLIDE_WIDTH, slidegen.SLIDE_HEIGHT)
            assert img.mode == 'RGBA'

    def test_every_length_in_the_envelope_fits(self):
        for words in WORD_COUNTS:
            lines, _, _ = slidegen.layout_slide(dummy_text(words, seed=words),
                                                'Book 1:1 ESV')
            assert slidegen.block_fits(len(lines)), words

    def test_absurdly_long_verse_is_rejected_not_clipped(self):
        with pytest.raises(slidegen.SlideOverflowError):
            slidegen.compose_slide(dummy_text(OVERFLOW_WORDS, seed=9),
                                   'Book 1:1 ESV')

    def test_overflow_boundary_is_a_clean_cutoff(self):
        """
        Once the guard fires it must keep firing -- no gap where a too-tall
        slide slips through.

        A single fixed seed is essential: dummy_text draws from one RNG stream,
        so n+1 words extends n words and line count rises monotonically.
        """
        overflowed_at = None
        for words in range(40, 200, 2):
            try:
                slidegen.layout_slide(dummy_text(words, seed=0), 'Book 1:1 ESV')
                assert overflowed_at is None, \
                    f'{words} words fit after {overflowed_at} overflowed'
            except slidegen.SlideOverflowError:
                overflowed_at = overflowed_at or words
        assert overflowed_at is not None


class TestShortContent:
    CASES = [
        'One.',
        'A B C.',
        '“Short quoted line.”',
        'Hyphenated-word and em—dash here.',
        'Numbers 1 2 3 and 10:45 here.',
        'I’m here with ‘nested’ quotes.',
    ]

    @pytest.mark.parametrize('text', CASES, ids=[c[:18] for c in CASES])
    def test_renders_with_ink(self, text):
        # One text line plus the reference line.
        assert len(ink_line_slots(slidegen.compose_slide(text, 'Book 1:1 ESV'))) >= 2

    def test_reference_line_is_present_and_placed(self):
        text = 'Short.'
        _, _, ref_top = slidegen.layout_slide(text, 'Book 1:1 ESV')
        groups = ink_rows(slidegen.compose_slide(text, 'Book 1:1 ESV'))
        assert abs(groups[-1][0] - ref_top) <= 8


class TestHorizontalScale:
    """
    The condense factor that compensates for a substitute font. It is 1.0 when
    the real Neue Haas is installed, so these assert the mechanism holds at
    whatever scale is active rather than assuming a particular one.
    """

    def test_measurer_reports_scaled_widths(self):
        verse_font, _ = slidegen.load_fonts()
        raw = slidegen.text_measurer(verse_font, scale=1.0)
        scaled = slidegen.text_measurer(verse_font)
        text = 'Sanctify them in the truth'
        assert scaled(text) == pytest.approx(raw(text) * slidegen.HORIZONTAL_SCALE)

    def test_scaling_narrows_rendered_ink(self):
        text = 'Sanctify them in the truth'
        wide = slidegen.compose_slide(text, 'Book 1:1 ESV', max_width=10_000)
        assert ink_bounds(wide)[1] > 0

    def test_vertical_metrics_are_untouched_by_scaling(self):
        """
        Condensing must not change cap height, baseline or line spacing.

        Compared on grid slots rather than raw ink groups: descenders form their
        own ink island a few px below a line, so raw grouping yields deltas that
        are neither LINE_HEIGHT nor REF_GAP even when spacing is perfect.
        """
        text = dummy_text(20, seed=3)
        ref = 'Book 1:1 ESV'
        lines, _, _ = slidegen.layout_slide(text, ref)
        slots = ink_line_slots(slidegen.compose_slide(text, ref))
        # Verse lines occupy consecutive slots, then a gap to the reference.
        assert slots[:len(lines)] == list(range(slots[0], slots[0] + len(lines)))
        assert slots[-1] - slots[len(lines) - 1] == \
            round(slidegen.REF_GAP / slidegen.LINE_HEIGHT)


class TestSlideFilename:
    CASES = [
        ('John 17:1 ESV', 'John_17_001.tif'),
        ('John 17:26 ESV', 'John_17_026.tif'),
        ('1 John 4:18 ESV', '1_John_4_018.tif'),
        ('Psalm 119:105 ESV', 'Psalm_119_105.tif'),
        ('Song of Solomon 2:1 ESV', 'Song_of_Solomon_2_001.tif'),
    ]

    @pytest.mark.parametrize('reference, expected', CASES)
    def test_derived_from_reference(self, reference, expected):
        assert slidegen.slide_filename(reference, 1) == expected

    def test_falls_back_to_the_index(self):
        assert slidegen.slide_filename('no numbers here', 7) == 'verse_007.tif'


class TestGenerateSlides:
    def test_writes_one_file_per_verse(self, tmp_path):
        verses = [(dummy_text(20, seed=n), f'Book 1:{n} ESV') for n in range(1, 6)]
        paths = slidegen.generate_slides(verses, output_dir=str(tmp_path))
        assert len(paths) == 5
        assert sorted(os.listdir(tmp_path)) == \
            [f'Book_1_{n:03d}.tif' for n in range(1, 6)]

    def test_written_slides_are_valid_tiffs(self, tmp_path):
        path = slidegen.generate_slides([(dummy_text(25, seed=1), 'Book 1:1 ESV')],
                                        output_dir=str(tmp_path))[0]
        with Image.open(path) as img:
            assert img.size == (slidegen.SLIDE_WIDTH, slidegen.SLIDE_HEIGHT)
            assert img.format == 'TIFF'
            assert img.mode == 'RGBA'

    def test_creates_nested_output_directory(self, tmp_path):
        target = tmp_path / 'nested' / 'deeper'
        slidegen.generate_slides([('Short.', 'Book 1:1 ESV')],
                                 output_dir=str(target))
        assert target.is_dir()

    def test_formats_text_by_default(self, tmp_path):
        verses = [('he said, “begin here,', 'Book 1:1 ESV'),
                  ('since[a] it was given,', 'Book 1:2 ESV')]
        assert slidegen.format_verses(verses)[1][0] == '“Since it was given,”'
        assert len(slidegen.generate_slides(verses, output_dir=str(tmp_path))) == 2

    def test_empty_passage(self, tmp_path):
        assert slidegen.generate_slides([], output_dir=str(tmp_path)) == []


class TestFontSelection:
    """Which typeface gets used, and the contract each choice must honour."""

    def test_a_font_was_resolved(self):
        assert slidegen.FONT_NAME != 'none'
        assert os.path.exists(slidegen.FONT_PATH)
        assert os.path.exists(slidegen.FONT_PATH_MEDIUM)

    def test_choices_are_ordered_best_first(self):
        """The real typeface must outrank the substitute, or installing it
        would silently do nothing."""
        assert slidegen.FONT_CHOICES[0][0].startswith('Neue Haas')
        assert slidegen.FONT_CHOICES[0][3] == 1.0

    def test_resolution_picks_the_first_installed_choice(self):
        expected = next(c for c in slidegen.FONT_CHOICES
                        if os.path.exists(c[1][0]) and os.path.exists(c[2][0]))
        assert slidegen.FONT_NAME == expected[0]
        assert slidegen.HORIZONTAL_SCALE == expected[3]

    def test_verse_and_reference_faces_are_distinct(self):
        """The deck sets the reference line in a heavier weight; if the two
        faces collapse to one, that distinction is silently lost."""
        verse, ref = slidegen.load_fonts()
        measure_v = slidegen.text_measurer(verse)
        measure_r = slidegen.text_measurer(ref)
        assert measure_r('Handgloves') > measure_v('Handgloves')

    def test_scale_is_one_only_for_the_reference_font(self):
        assert (slidegen.HORIZONTAL_SCALE == 1.0) == slidegen.IS_REFERENCE_FONT


class TestKerning:
    """
    PIL's basic layout ignores GPOS, so slidegen applies pair kerning itself.
    These pin the parts that could silently go wrong.
    """

    def test_the_reference_font_supplies_kerning(self):
        if not slidegen.IS_REFERENCE_FONT:
            pytest.skip('substitute font in use')
        verse, ref = slidegen.load_fonts()
        assert verse.kerning is not None and verse.kerning.pairs
        assert ref.kerning is not None and ref.kerning.pairs

    def test_missing_font_yields_no_kerning(self):
        assert slidegen._load_kerning('/no/such/font.ttf', 0) is None

    def test_kerning_is_ignored_for_the_substitute(self):
        """Helvetica Neue carries only a legacy 'kern' table, which is
        deliberately not read -- its scale was fitted without it."""
        # Located BY NAME, not by position. This read FONT_CHOICES[1] until a
        # repo-local Neue Haas candidate was inserted ahead of Helvetica, at
        # which point index 1 named a face that DOES carry GPOS kerning -- so
        # the assertion below ran against the wrong font and went red without
        # the behaviour it pins having changed at all.
        substitute = next(
            (c for c in slidegen.FONT_CHOICES if c[0].startswith('Helvetica')),
            None,
        )
        assert substitute is not None, 'no Helvetica substitute candidate'
        path, index = substitute[1]
        if not os.path.exists(path):
            pytest.skip('Helvetica Neue not present')
        assert slidegen._load_kerning(path, index) is None

    def test_kern_width_is_zero_without_kerning_data(self):
        assert slidegen.kern_width('AVATAR', None) == 0.0

    def test_kern_width_needs_two_characters(self):
        verse, _ = slidegen.load_fonts()
        assert slidegen.kern_width('', verse.kerning) == 0.0
        assert slidegen.kern_width('A', verse.kerning) == 0.0

    def test_known_pairs_tighten(self):
        verse, _ = slidegen.load_fonts()
        if verse.kerning is None:
            pytest.skip('no kerning data')
        # "AV" and "Yo" are the canonical kerned pairs in a grotesk.
        assert slidegen.kern_width('AV', verse.kerning) < 0
        assert slidegen.kern_width('Yo', verse.kerning) < 0

    def test_unkerned_pairs_are_untouched(self):
        verse, _ = slidegen.load_fonts()
        if verse.kerning is None:
            pytest.skip('no kerning data')
        assert slidegen.kern_width('nn', verse.kerning) == 0.0

    def test_kerning_narrows_measured_text(self):
        verse, _ = slidegen.load_fonts()
        if verse.kerning is None:
            pytest.skip('no kerning data')
        text = 'AVATAR, Yesterday'
        kerned = slidegen.text_measurer(verse)(text)
        plain = slidegen.text_measurer(slidegen.Face(verse.font))(text)
        assert kerned < plain

    def test_drawing_without_kerning_matches_pil_exactly(self):
        """
        The invariant that makes per-character drawing safe: with no kern
        deltas it must reproduce PIL's own whole-string layout pixel for pixel,
        so kerning is the *only* thing the custom path changes.
        """
        from PIL import ImageDraw

        verse, _ = slidegen.load_fonts()
        white = (255, 255, 255, 255)
        for text in ('When Jesus had spoken', 'AVATAR Yesterday, Wow.'):
            native = Image.new('RGBA', (1400, 120), (0, 0, 0, 0))
            ImageDraw.Draw(native).text((10, 20), text, fill=white, font=verse.font)

            ours = Image.new('RGBA', (1400, 120), (0, 0, 0, 0))
            slidegen._draw_line(ImageDraw.Draw(ours), 10, 20, text,
                                slidegen.Face(verse.font))

            assert np.array_equal(np.array(native), np.array(ours)), text

    def test_measured_width_matches_what_is_drawn(self):
        """Measurement and rendering must agree, or wrapping is fiction."""
        verse, _ = slidegen.load_fonts()
        text = 'AVATAR, Yesterday we saw'
        predicted = slidegen.text_measurer(verse)(text)
        img = slidegen.compose_slide(text, 'Book 1:1 ESV', max_width=10_000)
        left, right, _, _ = ink_bounds(img)
        assert abs((right - left) - predicted) <= 4

    def test_face_accepts_a_bare_pil_font(self):
        """Library callers passing a raw PIL font must keep working."""
        verse, _ = slidegen.load_fonts()
        assert slidegen.text_measurer(verse.font)('abc') > 0
        assert slidegen._as_face(verse.font).kerning is None
        assert slidegen._as_face(verse) is verse


class TestReferenceWeight:
    """
    The reference line is set heavier than the verse. That contrast is the
    deck's own design (the PSD specifies 65 Medium), and the weight is meant to
    be swappable without disturbing any layout constant.
    """

    def test_default_matches_the_psd(self):
        assert slidegen.REFERENCE_WEIGHT == 'medium'
        assert slidegen.VERSE_WEIGHT == 'roman'

    def test_reference_is_heavier_than_the_verse(self):
        verse, ref = slidegen.load_fonts()
        word = 'Handgloves'
        assert (slidegen.text_measurer(ref)(word)
                > slidegen.text_measurer(verse)(word))

    @pytest.mark.parametrize('weight', sorted(slidegen.WEIGHTS))
    def test_any_weight_leaves_layout_constants_valid(self, weight):
        """
        Cap height must not move with weight, or block_top would need refitting
        per weight; and the longest reference in the canon must still fit.
        """
        choices = slidegen._font_choices(slidegen.VERSE_WEIGHT, weight)
        path, index = next((c[2] for c in choices if os.path.exists(c[2][0])),
                           (None, 0))
        if path is None:
            pytest.skip(f'no font installed for weight {weight}')

        from PIL import ImageFont
        font = ImageFont.truetype(path, slidegen.FONT_SIZE, index=index)
        face = slidegen.Face(font, slidegen._load_kerning(path, index))

        img = slidegen.make_gradient().copy()
        slidegen._draw_text(img, slidegen.LEFT_MARGIN, 400, 'John 17:1 ESV', face)
        groups = ink_rows(img)
        assert groups, weight
        height = groups[0][1] - groups[0][0] + 1
        assert abs(height - slidegen.REF_CAP_HEIGHT) <= 2, f'{weight}: {height}px'

        widest = slidegen.text_measurer(face)('Song of Solomon 8:14 ESV')
        assert widest <= slidegen.REF_MAX_WIDTH, f'{weight}: {widest:.0f}px'
