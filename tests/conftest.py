"""
Shared test fixtures.

All prose here is synthetic. The formatter's rules are structural -- quote
carry, capitalization, wrapping, line counts -- so fixtures are written to
stress specific structures (long unbroken tokens, em-dashes, repetitive
clauses, ALL-CAPS emphasis, long proper nouns) rather than to be samples of
any real book. That keeps the suite offline, deterministic, and free of
third-party text.
"""

import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sermonflow as slidegen  # noqa: E402


def char_measure(text):
    """
    An exact, font-independent measure: 10 units per character.

    Lets wrap tests assert precise break positions without depending on which
    fonts happen to be installed.
    """
    return len(text) * 10


@pytest.fixture
def measure():
    """Real font metrics, for tests about how output actually looks."""
    verse_font, _ = slidegen.load_fonts()
    return slidegen.text_measurer(verse_font)


# Weighted toward short function words so generated text has roughly the
# word-length distribution of real prose (~5 words per line in the box). A pool
# of only long content words packs far fewer words per line than any real verse
# and makes length-based tests meaningless.
_FUNCTION_WORDS = ('the and of to a in that he it was for but not with you '
                   'from they me my so all we is as be him who').split()
_CONTENT_WORDS = ('light shines darkness word beginning made without life '
                  'people morning valley river stone bread water mountain '
                  'shepherd garden harvest threshold covenant remembered '
                  'wandered listened answered promise return kindness').split()
WORDS = _FUNCTION_WORDS * 3 + _CONTENT_WORDS

#: Word count that reliably exceeds the vertical envelope.
OVERFLOW_WORDS = 200

#: Largest word count that fits for *every* seed. Word count alone does not
#: determine line count -- which words are drawn matters -- so this is measured
#: as the largest count safe across seeds 0..60, not derived from 5 words/line.
MAX_FITTING_WORDS = 54


def dummy_text(word_count, seed=0):
    """
    Deterministic prose of an exact word count.

    One RNG stream per seed, so with a fixed seed dummy_text(n + 1) extends
    dummy_text(n) and line count rises monotonically with word count. Tests
    that depend on that monotonicity must pin the seed.
    """
    rng = random.Random(seed)
    words = [rng.choice(WORDS) for _ in range(word_count)]
    return ' '.join(words).capitalize() + '.'


#: Prose in varied registers, each chosen for a structure that could break the
#: formatter. Synthetic, not quotations.
PROSE_STYLES = {
    'epic_verse': 'Sing now of the anger that came upon the son of the '
                  'far-shooting lord, and of the ships drawn black upon the '
                  'shore of the wine-dark water.',
    'repetitive_clauses': 'And it came to pass that they journeyed, and it '
                          'came to pass that they built a city, and it came '
                          'to pass that they departed from that place.',
    'apologetic_questions': 'But is that claim actually true? And if it is '
                            'true, what follows from it; and if it is false, '
                            'why has it persuaded so many careful people?',
    'long_subordinate': 'The point is not that the argument fails, though it '
                        'may, but rather that the person making it has '
                        'already conceded the very thing which, had it been '
                        'granted at the start, would have settled the matter.',
    'declarative_emphasis': 'Let me be very clear. This is NOT acceptable. '
                            'Ninety-nine percent of working families know '
                            'exactly what is happening here.',
    'archaic_compounds': 'Beyond the grey-leaved wood the road ran on, past '
                         'the fallen door-stones of a hall whose '
                         'many-windowed towers had long since gone to grass.',
    'hyphenated_names': 'The record of Maher-shalal-hash-baz and of '
                        'Kiriath-jearim was set down beside the well of '
                        'Beer-lahai-roi.',
    'numbers_and_colons': 'The measure was 3 cubits by 12 cubits, recorded in '
                          'the 2nd year, at the 6th hour, before 40 witnesses.',
}


@pytest.fixture
def prose_corpus():
    """A spread of realistic paragraph lengths for wrap-quality checks."""
    return [dummy_text(n, seed=n) for n in range(8, MAX_FITTING_WORDS + 2, 6)]


@pytest.fixture
def prose_styles():
    """Varied real-world prose registers, keyed by the structure they stress."""
    return dict(PROSE_STYLES)
