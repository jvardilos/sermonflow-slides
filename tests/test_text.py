"""
Text normalization: artifact scrubbing, quote carry, capitalization.

The "light edits" from FORMATTING_NOTES.md sections 1 and 2, tested with no
font metrics or rendering involved. Table-driven: each table row is one
behaviour, so a failure names the case without needing a test per input.
"""

import pytest

from sermonflow import (
    CLOSE_QUOTE,
    OPEN_QUOTE,
    apply_quote_carry,
    capitalize_first_letter,
    find_artifacts,
    format_verses,
    normalize_quotes,
    strip_artifacts,
)


class TestNormalizeQuotes:
    CASES = [
        ('"hello"', '“hello”', 'both ends of a bare quote'),
        ('he said "go" then left', 'he said “go” then left', 'mid-sentence'),
        ('"go," he said', '“go,” he said', 'close after a comma'),
        ("I'm here", 'I’m here', 'contraction'),
        ("I've gone", 'I’ve gone', 'contraction'),
        ("don't", 'don’t', 'contraction'),
        ("the disciples' feet", 'the disciples’ feet', 'plural possessive'),
        ("'quoted'", '‘quoted’', 'single quotes'),
        ('nothing to do', 'nothing to do', 'no quotes at all'),
        ('“He said ‘go’ and I’m out.”', '“He said ‘go’ and I’m out.”',
         'already curly, untouched'),
    ]

    @pytest.mark.parametrize('raw, expected, why',
                             CASES, ids=[c[2] for c in CASES])
    def test_conversions(self, raw, expected, why):
        assert normalize_quotes(raw) == expected

    def test_no_straight_quotes_survive(self):
        out = normalize_quotes("""a "b" c 'd' don't "e",""")
        assert '"' not in out and "'" not in out


class TestStripArtifacts:
    CASES = [
        ('the life[a] was light', 'the life was light', 'footnote [a]'),
        ('the life[b] was light', 'the life was light', 'footnote [b]'),
        ('the life[12] was light', 'the life was light', 'numeric footnote'),
        ('the life[aa] was light', 'the life was light', 'two-letter footnote'),
        ('the life[ a ] was light', 'the life was light', 'padded footnote'),
        ('(A)In the beginning', 'In the beginning', 'crossref (A)'),
        ('(BZ)In the beginning', 'In the beginning', 'crossref (BZ)'),
        ('(CAA)In the beginning', 'In the beginning', 'crossref (CAA)'),
        ('16 They do not belong', 'They do not belong', 'leading verse number'),
        ('20 “I do not ask', '“I do not ask', 'verse number before quote'),
        ('  a   b\n\nc\td  ', 'a b c d', 'whitespace collapsed'),
        ('the word , and the life .', 'the word, and the life.',
         'space before punctuation'),
        ('he said “go ” then', 'he said “go” then', 'space before close quote'),
        ('a note (see also) here', 'a note (see also) here',
         'lowercase parenthetical kept'),
        ('option (a) applies', 'option (a) applies', 'lowercase (a) kept'),
        ('he fed them in 2 groups', 'he fed them in 2 groups',
         'interior number kept'),
        ('Matthew 10:45 is the reference', 'Matthew 10:45 is the reference',
         'chapter:verse kept'),
        ('"go," he said', '“go,” he said', 'quotes normalized too'),
        ('', '', 'empty'),
        ('   \n\t ', '', 'whitespace only'),
    ]

    @pytest.mark.parametrize('raw, expected, why',
                             CASES, ids=[c[2] for c in CASES])
    def test_cases(self, raw, expected, why):
        assert strip_artifacts(raw) == expected

    def test_many_artifacts_at_once(self):
        raw = '(A)In him[a] was life,[b] and (BZ)the life[c] was the light.'
        assert strip_artifacts(raw) == 'In him was life, and the life was the light.'

    def test_idempotent(self):
        once = strip_artifacts('(A)In him[a] was  life ,   and "the light" .')
        assert strip_artifacts(once) == once


class TestFindArtifacts:
    KINDS = [
        ('the life[a] was light', 'footnote-marker'),
        ('the life[12] was light', 'footnote-marker'),
        ('(A)In the beginning', 'crossref-marker'),
        ('16 They do not belong', 'leading-verse-number'),
        ('he said "go"', 'straight-double-quote'),
        ("don't stop", 'straight-single-quote'),
        ('two  spaces', 'double-space'),
        ('line\nbreak', 'newline'),
        ('tab\there', 'tab'),
        ('carriage\rreturn', 'carriage-return'),
        ('“a “b “c no closes', 'unbalanced-quotes'),
    ]

    @pytest.mark.parametrize('text, kind', KINDS, ids=[k[1] + ':' + k[0][:12]
                                                       for k in KINDS])
    def test_each_kind_detected(self, text, kind):
        assert kind in [k for k, _ in find_artifacts(text)]

    @pytest.mark.parametrize('text', [
        '“In the beginning was the Word.”',
        'He said, ‘go on,’ and I’m leaving.',
        '“a verse that keeps going',          # one carried quote is fine
    ])
    def test_clean_text_reports_nothing(self, text):
        assert find_artifacts(text) == []

    def test_reports_every_occurrence(self):
        found = [s for k, s in find_artifacts('a[a] b[b] c[c]')
                 if k == 'footnote-marker']
        assert found == ['[a]', '[b]', '[c]']

    def test_strip_artifacts_output_is_always_clean(self):
        dirty = '  (A)In him[a] was  life ,  and "the light" [b] .  '
        assert find_artifacts(strip_artifacts(dirty)) == []


class TestApplyQuoteCarry:
    """FORMATTING_NOTES.md section 1: every slide is quoted as if standalone."""

    def test_pure_narration_is_untouched(self):
        verses = ['He walked to the river.', 'The morning was cold.']
        assert apply_quote_carry(verses) == verses

    def test_self_contained_quote_is_untouched(self):
        verses = ['He said, “Wait here,” and then left.']
        assert apply_quote_carry(verses) == verses

    def test_opening_verse_gets_a_close(self):
        assert apply_quote_carry(['He said, “The hour has come,']) == \
            ['He said, “The hour has come,”']

    def test_bare_fragment_gets_both_marks(self):
        out = apply_quote_carry(['He said, “Begin,', 'since it was given,'])
        assert out[1] == '“since it was given,”'

    def test_paragraph_reopen_is_not_doubled(self):
        out = apply_quote_carry(['He said, “Begin,', '“I have made it known.'])
        assert out[1] == '“I have made it known.”'
        assert OPEN_QUOTE * 2 not in out[1]

    def test_final_close_gets_open_but_no_extra_close(self):
        out = apply_quote_carry(['He said, “Begin,', 'and I in them.”'])
        assert out[1] == '“and I in them.”'
        assert CLOSE_QUOTE * 2 not in out[1]

    def test_close_and_reopen_inside_one_verse(self):
        out = apply_quote_carry(['He said, “Wait,', 'stop,” he said, “go on.'])
        assert out[1] == '“stop,” he said, “go on.”'

    def test_nested_single_quotes_do_not_affect_depth(self):
        out = apply_quote_carry([
            'He said, “As written, ‘the stone is set,’ so it stands.”',
            'The morning was cold.',
        ])
        assert out[1] == 'The morning was cold.'

    def test_carry_persists_through_quoteless_verses(self):
        out = apply_quote_carry(['He said, “Begin,', 'a middle,',
                                 'another middle,', 'the end.”'])
        assert out[1:] == ['“a middle,”', '“another middle,”', '“the end.”']

    def test_stray_close_does_not_go_negative(self):
        out = apply_quote_carry(['A stray close.”', 'Plain narration.'])
        assert out[1] == 'Plain narration.'

    def test_reference_deck_shape(self):
        """Narration opening a quote, fragments, a reopen, then the close."""
        out = apply_quote_carry([
            'He looked up and said, “The hour has come,',
            'since authority was given,',
            'and this is the promise,',
            '“I have made it known,',
            'and I in them.”',
        ])
        assert out[0].endswith(CLOSE_QUOTE)
        for line in out[1:]:
            assert line.startswith(OPEN_QUOTE) and OPEN_QUOTE * 2 not in line
        assert out[-1].endswith(CLOSE_QUOTE) and CLOSE_QUOTE * 2 not in out[-1]

    def test_empty_input_and_no_mutation(self):
        assert apply_quote_carry([]) == []
        verses = ['He said, “Begin,', 'a fragment,']
        original = list(verses)
        apply_quote_carry(verses)
        assert verses == original


class TestCapitalizeFirstLetter:
    CASES = [
        ('since you have given', 'Since you have given', 'lowercase start'),
        ('“since you have given', '“Since you have given', 'after quote mark'),
        ('—wait here', '—Wait here', 'after em dash'),
        ('(see also) note', '(See also) note', 'after paren'),
        ('123 and then', '123 And then', 'after digits'),
        ('I’m here', 'I’m here', 'contraction untouched'),
        ("I'm here", "I'm here", 'straight contraction untouched'),
        ('ABBA said so', 'ABBA said so', 'all caps preserved'),
        ('mcDonald went', 'McDonald went', 'only first char changes'),
        ('When Jesus had spoken', 'When Jesus had spoken', 'already capital'),
        ('123 456', '123 456', 'no letters'),
        ('—', '—', 'punctuation only'),
        ('', '', 'empty'),
    ]

    @pytest.mark.parametrize('raw, expected, why',
                             CASES, ids=[c[2] for c in CASES])
    def test_cases(self, raw, expected, why):
        assert capitalize_first_letter(raw) == expected

    def test_rest_of_string_is_byte_identical(self):
        text = 'since YOU have GIVEN him'
        assert capitalize_first_letter(text)[1:] == text[1:]


class TestFormatVerses:
    def test_full_pipeline(self):
        out = format_verses([
            ('When he had spoken, he said, “The hour has come,', 'Book 1:1 ESV'),
            ('since[a] you have given him authority,', 'Book 1:2 ESV'),
        ])
        assert out[0][0].endswith('has come,”')
        # artifact stripped, quote prepended, then first letter raised
        assert out[1][0] == '“Since you have given him authority,”'

    def test_capitalization_happens_after_the_quote_is_added(self):
        out = format_verses([('He said, “Begin,', 'Book 1:1 ESV'),
                             ('since you were given,', 'Book 1:2 ESV')])
        assert out[1][0].startswith('“S')

    def test_references_and_order_preserved(self):
        refs = ['John 17:1 ESV', '1 John 4:18 ESV', 'Psalm 23:1 ESV']
        out = format_verses([('some text here', r) for r in refs])
        assert [r for _, r in out] == refs

    def test_output_is_free_of_artifacts(self):
        out = format_verses([
            ('(A)In him[a] was  life ,  and "the light" [b].', 'Book 1:1 ESV'),
            ('16 they do not belong', 'Book 1:2 ESV'),
        ])
        for text, ref in out:
            assert find_artifacts(text) == [], (ref, text)

    def test_idempotent(self):
        once = format_verses([('he said, “begin,', 'Book 1:1 ESV')])
        assert format_verses(once) == once

    def test_empty_input(self):
        assert format_verses([]) == []
