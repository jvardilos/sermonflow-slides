"""
The CLI's refusal messages.

--no-strict can render past what validation merely doubts, not past content
that cannot be laid out. Offering it for the second sends the operator into a
traceback (#20), so for that case the CLI has to exit with a reason instead.
"""

import pytest

from conftest import OVERFLOW_WORDS, dummy_text
from sermonflow.cli import build, build_points

TOO_MANY_POINTS = [f'Point number {i}.' for i in range(12)]


class LongVerseProvider:
    def fetch_chapter(self, reference, translation='ESV'):
        return [(dummy_text(OVERFLOW_WORDS), 'Book 1:1 ESV')]


class TestContentThatCannotBeLaidOut:
    def test_points_exit_with_a_reason_even_without_strict(self, tmp_path):
        with pytest.raises(SystemExit) as exc:
            build_points(TOO_MANY_POINTS, output_dir=str(tmp_path), strict=False)
        assert 'will not help' in str(exc.value)

    def test_points_refusal_does_not_offer_no_strict(self, tmp_path):
        with pytest.raises(SystemExit) as exc:
            build_points(TOO_MANY_POINTS, output_dir=str(tmp_path))
        assert 'pass --no-strict' not in str(exc.value)

    def test_passage_exits_with_a_reason_even_without_strict(self, tmp_path):
        with pytest.raises(SystemExit) as exc:
            build(
                'Book 1',
                output_dir=str(tmp_path),
                strict=False,
                provider=LongVerseProvider(),
            )
        assert 'will not help' in str(exc.value)
