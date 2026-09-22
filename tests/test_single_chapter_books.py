"""
Single-chapter books: Jude, Philemon, Obadiah, 2 and 3 John.

Both backends label verses from whatever the source calls the passage, and for
these five books that label is a bare book name -- BibleGateway's heading for
Jude is "Jude", not "Jude 1". Pasting ":verse" onto it put "Jude:1 ESV" on
screen, which is how this file came to exist.

Everything here is offline: the citation helper and the filename derivation are
both pure string work, which is the whole reason they were pulled out of the
providers.
"""

import pytest

import sermonflow as slidegen
from sermonflow.providers.base import format_citation, split_label


class TestLabelParsing:
    @pytest.mark.parametrize(
        "label,expected",
        [
            ("John 17", ("John", 17)),
            ("Psalm 119", ("Psalm", 119)),
            ("1 John 4", ("1 John", 4)),
            ("Song of Solomon 8", ("Song of Solomon", 8)),
            ("John 17:1-26", ("John", 17)),          # verse tail dropped
        ],
    )
    def test_ordinary_labels(self, label, expected):
        assert split_label(label) == expected

    @pytest.mark.parametrize(
        "label,expected",
        [
            ("Jude", ("Jude", 1)),                   # BibleGateway's heading
            ("Jude 1-25", ("Jude", 1)),              # the ESV API's canonical
            ("Jude 1–25", ("Jude", 1)),         # ... with an en dash
            ("Philemon", ("Philemon", 1)),
            ("Obadiah", ("Obadiah", 1)),
            ("2 John", ("2 John", 1)),
            ("3 John 1-15", ("3 John", 1)),
        ],
    )
    def test_single_chapter_labels_resolve_to_chapter_one(self, label, expected):
        assert split_label(label) == expected

    def test_a_range_is_verses_not_chapters(self):
        # "Jude 1-25" is verses 1-25 of a one-chapter book, not chapters 1-25.
        # Reading that "1" as the chapter is right by luck; reading the range
        # as chapters would put "Jude 1-25:3" on a slide, which is what the
        # ESV API path used to do.
        assert split_label("Jude 1-25") == ("Jude", 1)

    def test_a_leading_numeral_belongs_to_the_book(self):
        # "3 John" starts with a digit, but that digit is part of the name.
        assert split_label("3 John") == ("3 John", 1)
        assert split_label("3 John 1") == ("3 John", 1)

    def test_unparseable_label_degrades_instead_of_raising(self):
        # Wrong on a screen, but a service is not the place to crash.
        book, chapter = split_label("???")
        assert book == "???" and chapter == 1


class TestCitationFormat:
    @pytest.mark.parametrize(
        "label,verse,expected",
        [
            ("John 17", 1, "John 17:1 ESV"),
            ("Song of Solomon 8", 14, "Song of Solomon 8:14 ESV"),
            ("1 John 4", 18, "1 John 4:18 ESV"),
            ("Psalm 119", 105, "Psalm 119:105 ESV"),
        ],
    )
    def test_ordinary_books_keep_chapter_and_verse(self, label, verse, expected):
        assert format_citation(label, verse) == expected

    @pytest.mark.parametrize(
        "label,verse,expected",
        [
            ("Jude", 3, "Jude 1:3 ESV"),
            ("Jude 1-25", 3, "Jude 1:3 ESV"),
            ("Philemon", 6, "Philemon 1:6 ESV"),
            ("Obadiah", 1, "Obadiah 1:1 ESV"),
            ("2 John", 4, "2 John 1:4 ESV"),
            ("3 John", 1, "3 John 1:1 ESV"),
        ],
    )
    def test_single_chapter_books_get_an_explicit_chapter(
        self, label, verse, expected
    ):
        # The redundant "1:" is the convention on screen, and it keeps every
        # slide in a deck labelled the same way.
        assert format_citation(label, verse) == expected

    def test_both_backends_agree_on_the_same_passage(self):
        # The whole point: BibleGateway says "Jude", the ESV API says
        # "Jude 1-25", and the slide must not depend on which one answered.
        assert format_citation("Jude", 3) == format_citation("Jude 1-25", 3)

    def test_never_emits_a_bare_colon(self):
        # The original bug: "Jude:1 ESV" reached a rendered slide.
        for label in ("Jude", "Philemon", "Obadiah", "2 John", "3 John"):
            assert f"{label}:" not in format_citation(label, 1)

    def test_always_book_chapter_colon_verse(self):
        # The shape providers/base.py promises, for every label a source gives.
        import re

        for label in ("John 17", "Jude", "Jude 1-25", "3 John", "1 John 4"):
            assert re.fullmatch(r".+ \d+:\d+ ESV", format_citation(label, 7))

    def test_translation_is_carried_through(self):
        assert format_citation("Jude", 3, "NIV") == "Jude 1:3 NIV"


class TestFilenameStem:
    @pytest.mark.parametrize(
        "reference,expected",
        [
            ("John 17:1 ESV", "John_17_001"),
            ("1 John 4:18 ESV", "1_John_4_018"),
            ("Jude 1:3 ESV", "Jude_1_003"),
            ("Philemon 1:6 ESV", "Philemon_1_006"),
            ("3 John 1:1 ESV", "3_John_1_001"),
        ],
    )
    def test_stem_is_derived_from_the_reference(self, reference, expected):
        assert slidegen.slide_stem(reference, 1) == expected

    def test_unparseable_reference_falls_back_to_the_sequence(self):
        assert slidegen.slide_stem("no numbers here", 7) == "verse_007"

    def test_a_verse_only_reference_still_names_a_file(self):
        # No provider emits this shape any more, but a library caller passing
        # their own references can, and it must not collapse to verse_001.
        assert slidegen.slide_stem("Jude 3 ESV", 1) == "Jude_003"
        assert slidegen.slide_stem("3 John 1 ESV", 1) == "3_John_001"

    def test_single_chapter_stems_sort_into_verse_order(self):
        stems = [slidegen.slide_stem(f"Jude 1:{n} ESV", n) for n in range(1, 26)]
        assert stems == sorted(stems)
        assert stems[0] == "Jude_1_001" and stems[-1] == "Jude_1_025"
