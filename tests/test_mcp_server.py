"""
The MCP tools, called as plain functions.

Two properties matter here that the CLI tests cannot see. Over stdio the
server's stdout *is* the JSON-RPC stream, so a tool must never print to it.
And a tool result is read by a model that has no idea what the server's
working directory is, so the paths it reports have to stand on their own.
"""

import os

import pytest

from conftest import OVERFLOW_WORDS, dummy_text
from sermonflow import cli, mcp_server

PASSAGE = [
    ('In the beginning was the word.', 'Book 1:1 ESV'),
    ('And the light shines in the darkness.', 'Book 1:2 ESV'),
]

#: Twelve one-line points: rolling runs past the safe area at this length.
TOO_MANY_POINTS = [f'Point number {i}.' for i in range(12)]

#: No glyph in the typeface, so validation objects -- but it still draws.
GREEK = 'Grace, χάρις, is a gift.'


class CountingProvider:
    """A provider that serves a fixed passage and counts how often it is asked."""

    def __init__(self, passage=PASSAGE):
        self.passage = passage
        self.calls = 0

    def fetch_chapter(self, reference, translation='ESV'):
        self.calls += 1
        return list(self.passage)


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
        assert os.listdir(tmp_path) == []

    def test_strict_false_hint_for_a_passage_that_would_render(self, monkeypatch, tmp_path):
        serve(monkeypatch, [(GREEK, 'Book 1:1 ESV')])
        result = mcp_server.generate_slides('Book 1', output_dir=str(tmp_path))
        assert not result['rendered']
        assert 'strict=false' in result['hint']
