"""
Line breaking and "blockiness".

FORMATTING_NOTES.md section 3: greedy wrap packs every line full and strands
the remainder on a near-empty last line. balance_wrap fixes that without
costing a line.

Precise break assertions use conftest.char_measure (10 units per character) so
they are exact and font-independent. Quality assertions use real font metrics.
"""

import pytest

from conftest import char_measure, dummy_text
from slidegen import balance_wrap, break_long_word, greedy_wrap, raggedness

#: Enough paragraphs to make aggregate quality claims meaningful.
CORPUS_SEEDS = range(40)


class TestGreedyWrap:
    CASES = [
        ('abc def', 200, ['abc def'], 'fits on one line'),
        ('aaa bbb ccc', 70, ['aaa bbb', 'ccc'], 'breaks at the width'),
        ('a b c d e f', 50, ['a b c', 'd e f'], 'fills before moving on'),
        ('', 500, [], 'empty text'),
        ('   ', 500, [], 'whitespace only'),
    ]

    @pytest.mark.parametrize('text, width, expected, why',
                             CASES, ids=[c[3] for c in CASES])
    def test_cases(self, text, width, expected, why):
        assert greedy_wrap(text, char_measure, width) == expected

    def test_words_preserved_in_order(self):
        text = dummy_text(50, seed=4)
        assert ' '.join(greedy_wrap(text, char_measure, 250)).split() == text.split()

    def test_no_line_exceeds_the_width(self):
        for seed in range(6):
            text = dummy_text(60, seed=seed)
            for line in greedy_wrap(text, char_measure, 300):
                assert char_measure(line) <= 300

    def test_narrower_width_never_yields_fewer_lines(self):
        text = dummy_text(70, seed=5)
        counts = [len(greedy_wrap(text, char_measure, w))
                  for w in range(200, 800, 25)]
        assert counts == sorted(counts, reverse=True)


class TestBreakLongWord:
    """Oversized tokens are hard-broken so nothing is drawn off the canvas."""

    def test_splits_into_box_width_chunks(self):
        chunks = break_long_word('x' * 25, char_measure, 100)
        assert chunks == ['x' * 10, 'x' * 10, 'x' * 5]

    def test_short_word_is_returned_whole(self):
        assert break_long_word('abc', char_measure, 100) == ['abc']

    def test_single_character_wider_than_the_box_still_progresses(self):
        assert break_long_word('abc', char_measure, 5) == ['a', 'b', 'c']

    def test_chunks_rejoin_to_the_original(self):
        word = 'asdffjieosw76sahd7df6d6fgdofishdf' * 5
        assert ''.join(break_long_word(word, char_measure, 300)) == word

    def test_greedy_wrap_hard_breaks_instead_of_overflowing(self):
        long_word = 'x' * 100
        lines = greedy_wrap(f'a {long_word} b', char_measure, 200)
        assert all(char_measure(line) <= 200 for line in lines)
        assert ''.join(lines).replace(' ', '') == f'a{long_word}b'


class TestBalanceWrap:
    def test_single_line_short_circuits(self):
        assert balance_wrap('abc def', char_measure, 500) == ['abc def']

    def test_empty_text(self):
        assert balance_wrap('', char_measure, 500) == []

    def test_words_preserved_in_order(self):
        text = dummy_text(50, seed=6)
        assert ' '.join(balance_wrap(text, char_measure, 250)).split() == text.split()

    def test_long_unbreakable_token_terminates(self):
        """The binary-search floor is what stops this spinning forever."""
        long_word = 'x' * 200
        lines = balance_wrap(f'a {long_word} b', char_measure, 300)
        assert all(char_measure(line) <= 300 for line in lines)

    def test_text_that_is_only_one_long_token(self):
        lines = balance_wrap('x' * 200, char_measure, 100)
        assert ''.join(lines) == 'x' * 200

    # -- the two invariants balance_wrap actually guarantees ----------------

    def test_never_adds_a_line(self):
        for seed in CORPUS_SEEDS:
            text = dummy_text(45, seed=seed)
            assert len(balance_wrap(text, char_measure, 400)) <= \
                len(greedy_wrap(text, char_measure, 400))

    def test_never_widens_the_longest_line(self):
        for seed in CORPUS_SEEDS:
            text = dummy_text(45, seed=seed)
            widest = max(map(char_measure, balance_wrap(text, char_measure, 400)))
            assert widest <= max(map(char_measure,
                                     greedy_wrap(text, char_measure, 400)))

    def test_line_count_matches_greedy_across_widths(self, measure):
        text = dummy_text(60, seed=7)
        for width in range(300, 900, 50):
            assert len(balance_wrap(text, measure, width)) == \
                len(greedy_wrap(text, measure, width))


class TestRaggedness:
    CASES = [
        (['aaa', 'aaa', 'aaa'], 0.0, 'equal lines score zero'),
        ([], 0.0, 'no lines'),
        (['aaa'], 0.0, 'one line'),
    ]

    @pytest.mark.parametrize('lines, expected, why',
                             CASES, ids=[c[2] for c in CASES])
    def test_zero_cases(self, lines, expected, why):
        assert raggedness(lines, char_measure) == expected

    def test_final_short_line_does_count(self):
        # Counting it is the point: a stranded last line is the defect.
        assert raggedness(['aaa', 'aaa', 'a'], char_measure) > 0.0

    def test_grows_as_lines_get_more_uneven(self):
        tight = raggedness(['aaaa', 'aaa', 'aaaa'], char_measure)
        loose = raggedness(['aaaaaaaaaa', 'a', 'aaaaa'], char_measure)
        assert loose > tight


class TestBlockiness:
    """
    The subjective "looks like a box" quality, made measurable.

    Balancing is a heuristic, not a theorem: it wins decisively in aggregate
    but can lose marginally on an individual paragraph. Thresholds below are
    calibrated to measured behaviour (mean raggedness ~107px -> ~62px over a
    40-paragraph corpus, 30 wins / 1 marginal loss / 9 ties) rather than
    asserting an invariant that does not hold.
    """

    @staticmethod
    def _pairs(measure, width=678, words=45):
        for seed in CORPUS_SEEDS:
            text = dummy_text(words, seed=seed)
            yield (balance_wrap(text, measure, width),
                   greedy_wrap(text, measure, width))

    def test_mean_raggedness_improves_substantially(self, measure):
        balanced, greedy = zip(*self._pairs(measure))
        mean_b = sum(raggedness(l, measure) for l in balanced) / len(balanced)
        mean_g = sum(raggedness(l, measure) for l in greedy) / len(greedy)
        assert mean_b < 0.8 * mean_g

    def test_wins_on_the_clear_majority(self, measure):
        better = worse = 0
        for balanced, greedy in self._pairs(measure):
            delta = raggedness(balanced, measure) - raggedness(greedy, measure)
            better += delta < -1e-9
            worse += delta > 1e-9
        assert better > worse * 5
        assert better > len(CORPUS_SEEDS) / 2

    def test_no_paragraph_regresses_badly(self, measure):
        for balanced, greedy in self._pairs(measure):
            assert raggedness(balanced, measure) - \
                raggedness(greedy, measure) < 50

    def test_stranded_final_line_is_much_less_likely(self, measure):
        def worst_ratio(wraps):
            return min(min(measure(x) for x in lines) / max(measure(x) for x in lines)
                       for lines in wraps)

        balanced, greedy = zip(*self._pairs(measure))
        assert worst_ratio(balanced) > 2 * worst_ratio(greedy)

    def test_typical_paragraph_is_reasonably_even(self, prose_corpus, measure):
        ratios = []
        for text in prose_corpus:
            lines = balance_wrap(text, measure, 678)
            if len(lines) > 1:
                widths = [measure(line) for line in lines]
                ratios.append(min(widths) / max(widths))
        assert sum(ratios) / len(ratios) > 0.65

    def test_varied_prose_registers_all_wrap_evenly(self, prose_styles, measure):
        """
        Structures beyond generated filler: dashes, caps, long names.

        The evenness bound here is loose (0.25) on purpose. Text full of long
        hyphenated compounds has fewer legal break points, so balancing has less
        room to work and a genuinely short final line is unavoidable. This is a
        smoke test that nothing pathological happens, not a quality claim -- the
        quality claims are the aggregate tests above.
        """
        for name, text in prose_styles.items():
            lines = balance_wrap(text, measure, 678)
            assert lines, name
            assert all(measure(line) <= 678 for line in lines), name
            widths = [measure(line) for line in lines]
            assert min(widths) / max(widths) > 0.25, name
