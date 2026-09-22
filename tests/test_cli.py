"""
The CLI's refusal messages.

--no-strict renders past what validation merely doubts, and leaves out a verse
too long for a slide. It cannot force content with nothing to render: offering
it for that sent the operator into a traceback (#20), so the CLI exits with a
reason instead.
"""

import os

import pytest

from conftest import (
    GREEK,
    OVERFLOW_WORDS,
    TOO_MANY_POINTS,
    CountingProvider,
    dummy_text,
    needs_greek_flagged,
)
from sermonflow import cli
from sermonflow.cli import build, build_points, validate_points


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


@needs_greek_flagged
class TestNoStrictStillRenders:
    """The other side: a problem the renderer can draw past is overridable."""

    def test_points(self, tmp_path):
        paths = build_points([GREEK], output_dir=str(tmp_path), strict=False)
        assert len(paths) == 1 and os.path.isfile(paths[0])

    def test_passage(self, tmp_path):
        provider = serving((GREEK, 'Book 1:1 ESV'))
        paths = build('Book 1', output_dir=str(tmp_path), strict=False, provider=provider)
        assert len(paths) == 1 and os.path.isfile(paths[0])

    def test_passage_with_an_overlong_verse_renders_the_rest(self, tmp_path):
        provider = serving(
            ('The first verse fits.', 'Book 1:1 ESV'),
            (dummy_text(OVERFLOW_WORDS), 'Book 1:2 ESV'),
        )
        paths = build('Book 1', output_dir=str(tmp_path), strict=False, provider=provider)
        assert [os.path.basename(path) for path in paths] == ['Book_1_001.tif']

    def test_strict_still_refuses_and_offers_no_strict(self, tmp_path):
        with pytest.raises(SystemExit) as exc:
            build_points([GREEK], output_dir=str(tmp_path))
        assert 'pass --no-strict' in str(exc.value)

    def test_strict_refuses_a_mixed_passage_and_offers_no_strict(self, tmp_path):
        provider = serving(
            ('The first verse fits.', 'Book 1:1 ESV'),
            (dummy_text(OVERFLOW_WORDS), 'Book 1:2 ESV'),
        )
        with pytest.raises(SystemExit) as exc:
            build('Book 1', output_dir=str(tmp_path), provider=provider)
        # Not "--no-strict will not help": the rest of the passage renders.
        assert 'pass --no-strict' in str(exc.value)
        # And the operator is told the override drops something.
        assert 'skipped' in str(exc.value)
        assert os.listdir(tmp_path) == []


class TestDryRun:
    def test_a_verse_too_long_does_not_hide_the_rest(self, capsys):
        provider = serving(
            ('The first verse fits.', 'Book 1:1 ESV'),
            (dummy_text(OVERFLOW_WORDS), 'Book 1:2 ESV'),
            ('The third verse fits.', 'Book 1:3 ESV'),
        )
        # Previews the verses that fit, and lists the overlong one on stderr.
        # Exits non-zero because the default-strict render would refuse: a dry
        # run has to predict the render for `-n && render` to mean anything.
        with pytest.raises(SystemExit) as exc:
            build('Book 1', dry_run=True, provider=provider)
        assert 'pass --no-strict' in str(exc.value)
        captured = capsys.readouterr()
        assert 'Book 1:1 ESV' in captured.out and 'Book 1:3 ESV' in captured.out
        assert 'Book 1:2 ESV' in captured.err

    def test_no_strict_dry_run_of_the_same_passage_exits_zero(self, capsys):
        provider = serving(
            ('The first verse fits.', 'Book 1:1 ESV'),
            (dummy_text(OVERFLOW_WORDS), 'Book 1:2 ESV'),
        )
        assert build('Book 1', dry_run=True, strict=False, provider=provider) == []
        assert 'Book 1:1 ESV' in capsys.readouterr().out

    def test_a_passage_where_nothing_fits_exits_non_zero(self):
        provider = serving((dummy_text(OVERFLOW_WORDS), 'Book 1:1 ESV'))
        with pytest.raises(SystemExit) as exc:
            build('Book 1', dry_run=True, provider=provider)
        assert exc.value.code not in (None, 0)

    def test_a_passage_with_no_verses_exits_non_zero(self):
        with pytest.raises(SystemExit) as exc:
            build('Book 1', dry_run=True, provider=serving())
        assert exc.value.code not in (None, 0)


class TestValidatePoints:
    def test_an_unexpected_planning_error_is_reported_not_raised(self, monkeypatch):
        # Validation's job is to report; a ValueError nobody anticipated still
        # comes back as a problem rather than a crash.
        def broken(points, style):
            raise ValueError('boom')

        monkeypatch.setattr(cli, 'plan_points', broken)
        assert validate_points(['One.']) == ['boom']
