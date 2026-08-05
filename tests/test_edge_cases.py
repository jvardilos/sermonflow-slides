"""
Hostile and unusual input, and reference-name coverage.

Two things this file guards against, both of which were real bugs found by
writing it:

  1. Empty or whitespace-only text raised IndexError deep inside layout.
  2. A 150-character junk token was drawn ~5000px wide -- off a 1920px canvas,
     silently, with no error.

Plus: characters the substituted font has no glyph for render as tofu boxes,
which looks like output but is not. find_unrenderable exists to catch that
before anything reaches a screen.
"""

import pytest

import slidegen
from conftest import MAX_FITTING_WORDS, OVERFLOW_WORDS, dummy_text

REF = 'Book 1:1 ESV'

JUNK = 'asdffjieosw76sahd7df6d6fgdofishdf'


class TestEmptyAndBlank:
    BLANK = ['', ' ', '     ', '\t', '\n', ' \t\n ', '\r\n', ' ']

    @pytest.mark.parametrize('text', BLANK, ids=[repr(t) for t in BLANK])
    def test_layout_raises_empty_verse_error(self, text):
        with pytest.raises(slidegen.EmptyVerseError):
            slidegen.layout_slide(text, REF)

    def test_error_names_the_reference(self):
        with pytest.raises(slidegen.EmptyVerseError, match='Book 1:1 ESV'):
            slidegen.layout_slide('', REF)

    def test_generate_slides_skips_rather_than_crashing(self, tmp_path):
        verses = [
            ('Real text here.', 'Book 1:1 ESV'),
            ('', 'Book 1:2 ESV'),
            ('   ', 'Book 1:3 ESV'),
            ('More real text.', 'Book 1:4 ESV'),
        ]
        paths = slidegen.generate_slides(verses, output_dir=str(tmp_path))
        assert len(paths) == 2
        assert not any('002' in p or '003' in p for p in paths)

    def test_punctuation_only_is_not_treated_as_empty(self):
        lines, _, _ = slidegen.layout_slide('...---', REF)
        assert lines == ['...---']


class TestOversizedTokens:
    LONG = [
        (JUNK * 5, 'repeated junk, 165 chars'),
        ('a7f3c9e2b8d1' * 13, 'hex-ish hash, 156 chars'),
        ('x' * 150, 'single character repeated'),
        ('https://example.com/' + 'path/' * 30, 'url-like'),
        ('Supercali' + 'fragilistic' * 6, 'long compound'),
        ('-' * 200, 'punctuation run'),
    ]

    @pytest.mark.parametrize('text, why', LONG, ids=[c[1] for c in LONG])
    def test_never_renders_wider_than_the_box(self, text, why, measure):
        lines, _, _ = slidegen.layout_slide(text, REF)
        for line in lines:
            assert measure(line) <= slidegen.TEXT_BOX_WIDTH + 1, why

    @pytest.mark.parametrize('text, why', LONG, ids=[c[1] for c in LONG])
    def test_ink_stays_on_the_canvas(self, text, why):
        from test_render import ink_bounds
        left, right, top, bottom = ink_bounds(slidegen.compose_slide(text, REF))
        assert left >= 0 and right < slidegen.SLIDE_WIDTH, why
        assert top >= 0 and bottom < slidegen.SLIDE_HEIGHT, why

    def test_content_is_not_silently_dropped(self):
        lines, _, _ = slidegen.layout_slide(JUNK * 4, REF)
        assert ''.join(lines).replace(' ', '') == JUNK * 4

    def test_absurdly_long_token_overflows_vertically_instead(self):
        """Hard-breaking converts a width problem into a height problem, which
        the vertical guard already reports."""
        with pytest.raises(slidegen.SlideOverflowError):
            slidegen.layout_slide('x' * 4000, REF)


class TestUnicode:
    #: Covered by any Latin text face, so the verdict is the same
    #: whichever font choice is installed.
    RENDERABLE = [
        ('Café and naïve résumé', 'latin-1 accents'),
        ('áêĩõü combining forms', 'accented vowels'),
        ('“curly” and ‘nested’ quotes', 'typographic quotes'),
        ('em—dash and en–dash', 'dashes'),
        ('ellipsis… and bullet •', 'punctuation'),
        ('a b non-breaking space', 'nbsp'),
    ]

    #: Absent from every font this project will load.
    UNRENDERABLE = [
        ('太初有道，道與神同在', 'CJK'),
        ('בְּרֵאשִׁית בָּרָא', 'Hebrew'),
        ('Praise 🙏 the Lord 🎉', 'emoji'),
        ('family 👨‍👩‍👧‍👦 here', 'emoji with ZWJ'),
    ]

    #: Coverage differs between the reference font and the substitute, so
    #: the verdict is not hardcoded -- only the contract is checked.
    FONT_DEPENDENT = [
        ('Alpha βeta λambda', 'greek letters'),
        ('Ω μ π ∑ ∞ ≈', 'greek and maths symbols'),
    ]

    @pytest.mark.parametrize('text, why',
                             RENDERABLE, ids=[c[1] for c in RENDERABLE])
    def test_supported_scripts_render_and_report_clean(self, text, why):
        lines, _, _ = slidegen.layout_slide(text, REF)
        assert lines, why
        assert slidegen.find_unrenderable(text) == [], why

    @pytest.mark.parametrize('text, why',
                             UNRENDERABLE, ids=[c[1] for c in UNRENDERABLE])
    def test_unsupported_scripts_are_flagged_not_silently_tofued(self, text, why):
        # They must not crash...
        slidegen.layout_slide(text, REF)
        # ...but they must be reported, since tofu boxes look like real output.
        problems = slidegen.find_unrenderable(text)
        assert problems, why
        assert all(k == 'unrenderable-character' for k, _ in problems)

    @pytest.mark.parametrize('text, why',
                             FONT_DEPENDENT, ids=[c[1] for c in FONT_DEPENDENT])
    def test_report_matches_what_the_installed_font_covers(self, text, why):
        """
        Whatever the font covers, the report must agree exactly: no silent
        tofu, and no false alarm on a character that would have drawn fine.
        """
        slidegen.layout_slide(text, REF)
        covered = slidegen._font_charset()
        if covered is None:
            pytest.skip('font charset not inspectable')
        expected = {ch for ch in text
                    if not ch.isspace() and ord(ch) not in covered}
        reported = {detail.split(' U+')[0] for _, detail in
                    slidegen.find_unrenderable(text)}
        assert reported == {repr(ch) for ch in expected}, why

    def test_the_reference_font_has_no_greek(self):
        """
        Worth pinning: Neue Haas Grotesk Display Pro ships no Greek, so a verse
        or a point quoting a Greek word is refused rather than tofued. The
        substitute does cover it, which is why this is conditional.
        """
        if not slidegen.IS_REFERENCE_FONT:
            pytest.skip('substitute font in use')
        assert slidegen.find_unrenderable('the word λόγος here')

    def test_each_bad_character_reported_once(self):
        problems = slidegen.find_unrenderable('🙏🙏🙏🎉🎉')
        assert len(problems) == 2

    def test_control_characters_do_not_crash(self):
        for text in ['a\x00b', 'a\x0bb', 'a​b', '‮reversed']:
            slidegen.layout_slide(slidegen.strip_artifacts(text) or 'x', REF)

    def test_normalization_survives_unicode(self):
        assert slidegen.strip_artifacts('Café[a]  naïve') == 'Café naïve'
        assert slidegen.capitalize_first_letter('études') == 'Études'


class TestProseRegisters:
    """Real-world prose structures beyond generated filler."""

    def test_every_register_renders_within_bounds(self, prose_styles, measure):
        from test_render import ink_bounds
        for name, text in prose_styles.items():
            formatted = slidegen.format_verses([(text, REF)])[0][0]
            lines, _, _ = slidegen.layout_slide(formatted, REF)
            assert lines, name
            assert all(measure(l) <= slidegen.TEXT_BOX_WIDTH + 1 for l in lines), name
            left, right, top, bottom = ink_bounds(
                slidegen.compose_slide(formatted, REF))
            assert right < slidegen.SLIDE_WIDTH and bottom < slidegen.SLIDE_HEIGHT, name

    def test_registers_are_free_of_artifacts_after_formatting(self, prose_styles):
        for name, text in prose_styles.items():
            formatted = slidegen.format_verses([(text, REF)])[0][0]
            assert slidegen.find_artifacts(formatted) == [], name
            assert slidegen.find_unrenderable(formatted) == [], name

    def test_all_caps_emphasis_is_preserved(self, prose_styles):
        formatted = slidegen.format_verses(
            [(prose_styles['declarative_emphasis'], REF)])[0][0]
        assert 'NOT' in formatted

    def test_hyphenated_proper_nouns_are_not_mangled(self, prose_styles):
        formatted = slidegen.format_verses(
            [(prose_styles['hyphenated_names'], REF)])[0][0]
        for name in ('Maher-shalal-hash-baz', 'Kiriath-jearim', 'Beer-lahai-roi'):
            assert name in formatted


# ---------------------------------------------------------------------------
# Reference coverage
# ---------------------------------------------------------------------------

#: Every book of the Protestant canon, in order.
BIBLE_BOOKS = [
    'Genesis', 'Exodus', 'Leviticus', 'Numbers', 'Deuteronomy', 'Joshua',
    'Judges', 'Ruth', '1 Samuel', '2 Samuel', '1 Kings', '2 Kings',
    '1 Chronicles', '2 Chronicles', 'Ezra', 'Nehemiah', 'Esther', 'Job',
    'Psalm', 'Proverbs', 'Ecclesiastes', 'Song of Solomon', 'Isaiah',
    'Jeremiah', 'Lamentations', 'Ezekiel', 'Daniel', 'Hosea', 'Joel', 'Amos',
    'Obadiah', 'Jonah', 'Micah', 'Nahum', 'Habakkuk', 'Zephaniah', 'Haggai',
    'Zechariah', 'Malachi', 'Matthew', 'Mark', 'Luke', 'John', 'Acts',
    'Romans', '1 Corinthians', '2 Corinthians', 'Galatians', 'Ephesians',
    'Philippians', 'Colossians', '1 Thessalonians', '2 Thessalonians',
    '1 Timothy', '2 Timothy', 'Titus', 'Philemon', 'Hebrews', 'James',
    '1 Peter', '2 Peter', '1 John', '2 John', '3 John', 'Jude', 'Revelation',
]


class TestBibleBookReferences:
    def test_canon_is_complete(self):
        assert len(BIBLE_BOOKS) == 66

    def test_every_book_produces_a_sane_filename(self):
        for i, book in enumerate(BIBLE_BOOKS, 1):
            name = slidegen.slide_filename(f'{book} 3:16 ESV', i)
            assert name.endswith('_3_016.tif'), book
            assert name.startswith(book.replace(' ', '_')), book
            assert ' ' not in name, book
            assert not name.startswith('verse_'), book

    def test_numbered_books_keep_their_number(self):
        for book in ('1 John', '2 Peter', '3 John', '1 Samuel', '2 Chronicles'):
            name = slidegen.slide_filename(f'{book} 1:1 ESV', 1)
            assert name.startswith(book.replace(' ', '_') + '_'), book

    def test_multiword_books(self):
        assert slidegen.slide_filename('Song of Solomon 2:1 ESV', 1) == \
            'Song_of_Solomon_2_001.tif'

    def test_every_book_reference_fits_the_scrim(self):
        """
        The reference line is drawn on one line without wrapping, so every book
        name has to fit REF_MAX_WIDTH -- the scrim, not the narrower verse box.
        """
        too_wide = [
            (book, slidegen.find_overlong_reference(f'{book} 3:16 ESV'))
            for book in BIBLE_BOOKS
            if slidegen.find_overlong_reference(f'{book} 3:16 ESV')
        ]
        assert not too_wide, too_wide

    def test_longest_real_reference_in_the_canon_fits(self):
        """
        "Song of Solomon 8:14 ESV" is the longest reference in the canon. It
        overruns TEXT_BOX_WIDTH, which is why the reference line is budgeted
        against the scrim instead -- a real constraint, not a formality.
        """
        _, ref_font = slidegen.load_fonts()
        width = slidegen.text_measurer(ref_font)('Song of Solomon 8:14 ESV')
        assert width > slidegen.TEXT_BOX_WIDTH, 'the verse box would be enough'
        assert width <= slidegen.REF_MAX_WIDTH, f'{width:.0f}px'
        assert slidegen.find_overlong_reference('Song of Solomon 8:14 ESV') == []

    def test_an_absurd_reference_is_reported(self):
        """The check has to actually fire, or it is decoration."""
        problems = slidegen.find_overlong_reference(
            'The Second Epistle to the Thessalonians 3:16 ESV')
        assert problems and problems[0][0] == 'reference-too-wide'

    def test_high_chapter_and_verse_numbers(self):
        assert slidegen.slide_filename('Psalm 119:176 ESV', 1) == \
            'Psalm_119_176.tif'

    def test_filenames_sort_into_verse_order(self):
        names = [slidegen.slide_filename(f'John 17:{n} ESV', n)
                 for n in range(1, 27)]
        assert names == sorted(names)


class TestNonBibleReferences:
    """Other sources, since the tool is really a generic quote-slide renderer."""

    WITH_CHAPTER_VERSE = [
        ('Iliad 1:1', 'Iliad_1_001.tif'),
        ('1 Nephi 3:7', '1_Nephi_3_007.tif'),
        ('Enuma Elish 4:12', 'Enuma_Elish_4_012.tif'),
        ('Quran 2:255', 'Quran_2_255.tif'),
    ]

    @pytest.mark.parametrize('reference, expected', WITH_CHAPTER_VERSE)
    def test_chapter_verse_style_parses(self, reference, expected):
        assert slidegen.slide_filename(reference, 1) == expected

    WITHOUT_CHAPTER_VERSE = [
        'Mere Christianity, Book II',
        'The Fellowship of the Ring, ch. I',
        'Address to Congress',
        'no numbers at all',
        '',
    ]

    @pytest.mark.parametrize('reference', WITHOUT_CHAPTER_VERSE,
                             ids=[r[:20] or 'empty' for r in WITHOUT_CHAPTER_VERSE])
    def test_falls_back_to_the_index(self, reference):
        assert slidegen.slide_filename(reference, 7) == 'verse_007.tif'

    def test_fallback_names_still_sort(self):
        names = [slidegen.slide_filename('untitled', n) for n in range(1, 30)]
        assert names == sorted(names)

    def test_long_reference_lines_are_measurable(self, measure):
        """A reference too long for the box should be detectable, not silent."""
        _, ref_font = slidegen.load_fonts()
        width = slidegen.text_measurer(ref_font)(
            'The Fellowship of the Ring, Book II, Chapter IV')
        assert width > 0


class TestBulkMixedInput:
    """A whole batch of mixed-quality data must not abort partway."""

    def test_mixed_batch_renders_the_good_and_skips_the_blank(self, tmp_path):
        verses = [
            ('Ordinary verse text goes here.', 'Book 1:1 ESV'),
            ('', 'Book 1:2 ESV'),
            (JUNK * 3, 'Book 1:3 ESV'),
            ('Café and naïve résumé.', 'Book 1:4 ESV'),
            ('   ', 'Book 1:5 ESV'),
            (dummy_text(MAX_FITTING_WORDS, seed=1), 'Book 1:6 ESV'),
        ]
        paths = slidegen.generate_slides(verses, output_dir=str(tmp_path))
        assert len(paths) == 4

    def test_overflowing_verse_still_raises_in_a_batch(self, tmp_path):
        verses = [
            ('Fine.', 'Book 1:1 ESV'),
            (dummy_text(OVERFLOW_WORDS, seed=2), 'Book 1:2 ESV'),
        ]
        with pytest.raises(slidegen.SlideOverflowError, match='Book 1:2 ESV'):
            slidegen.generate_slides(verses, output_dir=str(tmp_path))
