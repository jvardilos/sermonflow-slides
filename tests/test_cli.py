"""
The CLI's refusal messages.

--no-strict can render past what validation merely doubts, not past content
that cannot be laid out. Offering it for the second sends the operator into a
traceback (#20), so for that case the CLI has to exit with a reason instead --
and for the first, --no-strict still has to render.
"""

import os

import pytest

from conftest import GREEK, OVERFLOW_WORDS, TOO_MANY_POINTS, CountingProvider, dummy_text
from sermonflow.cli import build, build_points


def serving(*verses):
    return CountingProvider(list(verses))


class TestContentThatCannotBeLaidOut:
    def test_points_exit_with_a_reason_even_without_strict(self, tmp_path):
        with pytest.raises(SystemExit) as exc:
            build_points(TOO_MANY_POINTS, output_dir=str(tmp_path), strict=False)
        assert 'will not help' in str(exc.value)

    def test_points_refusal_does_not_offer_no_strict(self, tmp_path):
        with pytest.raises(SystemExit) as exc:
            build_points(TOO_MANY_POINTS, output_dir=str(tmp_path))
        assert 'will not help' in str(exc.value)
        assert 'pass --no-strict' not in str(exc.value)
        assert os.listdir(tmp_path) == []

    def test_passage_exits_with_a_reason_even_without_strict(self, tmp_path):
        provider = serving((dummy_text(OVERFLOW_WORDS), 'Book 1:1 ESV'))
        with pytest.raises(SystemExit) as exc:
            build('Book 1', output_dir=str(tmp_path), strict=False, provider=provider)
        assert 'will not help' in str(exc.value)

    def test_passage_with_no_verses_exits(self, tmp_path):
        with pytest.raises(SystemExit):
            build('Book 1', output_dir=str(tmp_path), strict=False, provider=serving())
        assert os.listdir(tmp_path) == []


class TestNoStrictStillRenders:
    """The other side: a problem the renderer can draw past is overridable."""

    def test_points(self, tmp_path):
        paths = build_points([GREEK], output_dir=str(tmp_path), strict=False)
        assert len(paths) == 1 and os.path.isfile(paths[0])

    def test_passage(self, tmp_path):
        provider = serving((GREEK, 'Book 1:1 ESV'))
        paths = build('Book 1', output_dir=str(tmp_path), strict=False, provider=provider)
        assert len(paths) == 1 and os.path.isfile(paths[0])

    def test_strict_still_refuses_and_offers_no_strict(self, tmp_path):
        with pytest.raises(SystemExit) as exc:
            build_points([GREEK], output_dir=str(tmp_path))
        assert 'pass --no-strict' in str(exc.value)


class TestDryRun:
    def test_a_verse_too_long_does_not_hide_the_rest(self, capsys):
        provider = serving(
            ('The first verse fits.', 'Book 1:1 ESV'),
            (dummy_text(OVERFLOW_WORDS), 'Book 1:2 ESV'),
            ('The third verse fits.', 'Book 1:3 ESV'),
        )
        assert build('Book 1', dry_run=True, provider=provider) == []
        captured = capsys.readouterr()
        assert 'Book 1:1 ESV' in captured.out and 'Book 1:3 ESV' in captured.out
        assert 'Book 1:2 ESV' in captured.err
