"""
The MCP tools, called as plain functions.

Two properties matter here that the CLI tests cannot see. Over stdio the
server's stdout *is* the JSON-RPC stream, so a tool must never print to it.
And a tool result is read by a model that has no idea what the server's
working directory is, so the paths it reports have to stand on their own.
"""

import os

import pytest

from conftest import GREEK, OVERFLOW_WORDS, TOO_MANY_POINTS, CountingProvider, dummy_text
from sermonflow import cli, mcp_server

PASSAGE = [
    ('In the beginning was the word.', 'Book 1:1 ESV'),
    ('And the light shines in the darkness.', 'Book 1:2 ESV'),
]


def serve(monkeypatch, passage=PASSAGE):
    """Make `passage` what every fetch returns, and hand back the provider."""
    fake = CountingProvider(passage)
    monkeypatch.setattr(cli, 'get_default_provider', lambda: fake)
    return fake


@pytest.fixture
def provider(monkeypatch):
    return serve(monkeypatch)


class TestNothingOnStdout:
    def test_generate_slides(self, provider, tmp_path, capsys):
        result = mcp_server.generate_slides('Book 1', output_dir=str(tmp_path))
        assert result['rendered']
        assert capsys.readouterr().out == ''

    def test_generate_points(self, tmp_path, capsys):
        result = mcp_server.generate_points(['One.', 'Two.'], output_dir=str(tmp_path))
        assert result['rendered']
        assert capsys.readouterr().out == ''


class TestGenerateSlides:
    def test_fetches_the_passage_once(self, provider, tmp_path):
        mcp_server.generate_slides('Book 1', output_dir=str(tmp_path))
        assert provider.calls == 1

    def test_writes_a_slide_per_verse(self, provider, tmp_path):
        result = mcp_server.generate_slides('Book 1', output_dir=str(tmp_path))
        assert result['count'] == len(PASSAGE)
        assert all(os.path.isfile(path) for path in result['paths'])


class TestReportedPaths:
    """What comes back must locate the files without knowing the server's cwd."""

    def test_relative_output_dir_is_reported_absolute(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = mcp_server.generate_points(['One.'], output_dir='out')
        assert result['output_dir'] == str(tmp_path / 'out')
        assert all(os.path.isabs(path) for path in result['paths'])

    def test_home_is_expanded(self, tmp_path, monkeypatch):
        monkeypatch.setenv('HOME', str(tmp_path))
        result = mcp_server.generate_points(['One.'], output_dir='~/deck')
        assert result['output_dir'] == str(tmp_path / 'deck')
        assert os.path.isfile(result['paths'][0])


class TestStrictHint:
    """
    strict=false can draw past a doubtful character, but not past content that
    does not fit. A refusal has to say which of the two it is, or following its
    hint sends the model into an exception (#20).
    """

    def test_points_that_do_not_fit_are_refused_even_when_not_strict(self, tmp_path):
        result = mcp_server.generate_points(
            TOO_MANY_POINTS, output_dir=str(tmp_path), strict=False
        )
        assert not result['rendered']
        assert os.listdir(tmp_path) == []

    def test_no_strict_false_hint_for_points_that_do_not_fit(self, tmp_path):
        result = mcp_server.generate_points(TOO_MANY_POINTS, output_dir=str(tmp_path))
        assert 'strict=false' not in result['hint']
        assert os.listdir(tmp_path) == []

    def test_strict_false_hint_for_points_that_would_render(self, tmp_path):
        result = mcp_server.generate_points([GREEK], output_dir=str(tmp_path))
        assert not result['rendered']
        assert 'strict=false' in result['hint']
        forced = mcp_server.generate_points([GREEK], output_dir=str(tmp_path), strict=False)
        assert forced['rendered']

    def test_verse_that_does_not_fit_is_refused_even_when_not_strict(
        self, monkeypatch, tmp_path
    ):
        serve(monkeypatch, [(dummy_text(OVERFLOW_WORDS), 'Book 1:1 ESV')])
        result = mcp_server.generate_slides('Book 1', output_dir=str(tmp_path), strict=False)
        assert not result['rendered']
        assert 'strict=false' not in result['hint']
        # The ESV API ignores the translation, so suggesting one would be
        # another failing retry; the verses themselves can't be edited.
        assert 'translation' not in result['hint']
        assert 'tell the user' in result['hint']
        assert os.listdir(tmp_path) == []

    def test_passage_with_no_verses_is_refused(self, monkeypatch, tmp_path):
        # Nothing to validate is not the same as nothing wrong.
        serve(monkeypatch, [])
        result = mcp_server.generate_slides('Book 1', output_dir=str(tmp_path), strict=False)
        assert not result['rendered']
        assert result['problems']
        assert os.listdir(tmp_path) == []

    def test_unknown_style_is_named_even_when_every_point_is_blank(self, tmp_path):
        result = mcp_server.generate_points(['  ', ''], style='sideways', output_dir=str(tmp_path))
        assert any('sideways' in problem for problem in result['problems'])

    def test_strict_false_hint_for_a_passage_that_would_render(self, monkeypatch, tmp_path):
        serve(monkeypatch, [(GREEK, 'Book 1:1 ESV')])
        result = mcp_server.generate_slides('Book 1', output_dir=str(tmp_path))
        assert not result['rendered']
        assert 'strict=false' in result['hint']
        forced = mcp_server.generate_slides('Book 1', output_dir=str(tmp_path), strict=False)
        assert forced['rendered'] and forced['count'] == 1

    def test_passage_with_no_text_is_refused_even_when_not_strict(self, monkeypatch, tmp_path):
        # Every verse empty: rendering would "succeed" with zero slides.
        serve(monkeypatch, [('   ', 'Book 1:1 ESV'), ('', 'Book 1:2 ESV')])
        result = mcp_server.generate_slides('Book 1', output_dir=str(tmp_path), strict=False)
        assert not result['rendered']
        assert 'strict=false' not in result['hint']
        assert os.listdir(tmp_path) == []

    @pytest.mark.parametrize(
        'points,style',
        [(['  ', '\n'], 'stacked'), (['One.'], 'sideways')],
        ids=['no-text', 'unknown-style'],
    )
    def test_decks_that_cannot_plan_are_refused_even_when_not_strict(
        self, points, style, tmp_path
    ):
        result = mcp_server.generate_points(
            points, style=style, output_dir=str(tmp_path), strict=False
        )
        assert not result['rendered']
        assert 'strict=false' not in result['hint']


class TestPreviewSlides:
    def test_a_verse_too_long_is_reported_not_raised(self, monkeypatch):
        serve(monkeypatch, [(dummy_text(OVERFLOW_WORDS), 'Book 1:1 ESV')])
        result = mcp_server.preview_slides('Book 1')
        assert any('Book 1:1 ESV' in problem for problem in result['problems'])

    def test_the_verses_that_fit_are_still_previewed(self, monkeypatch):
        serve(monkeypatch, [
            PASSAGE[0],
            (dummy_text(OVERFLOW_WORDS), 'Book 1:2 ESV'),
            ('A third verse that fits.', 'Book 1:3 ESV'),
        ])
        result = mcp_server.preview_slides('Book 1')
        assert [slide['reference'] for slide in result['slides']] == [
            'Book 1:1 ESV', 'Book 1:3 ESV'
        ]
