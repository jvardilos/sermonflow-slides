"""
The MCP tools, called as plain functions.

Two properties matter here that the CLI tests cannot see. Over stdio the
server's stdout *is* the JSON-RPC stream, so a tool must never print to it.
And a tool result is read by a model that has no idea what the server's
working directory is, so the paths it reports have to stand on their own.
"""

import os

import pytest

from sermonflow import cli, mcp_server

PASSAGE = [
    ('In the beginning was the word.', 'Book 1:1 ESV'),
    ('And the light shines in the darkness.', 'Book 1:2 ESV'),
]


class CountingProvider:
    """A provider that serves PASSAGE and counts how often it is asked."""

    def __init__(self):
        self.calls = 0

    def fetch_chapter(self, reference, translation='ESV'):
        self.calls += 1
        return list(PASSAGE)


@pytest.fixture
def provider(monkeypatch):
    fake = CountingProvider()
    monkeypatch.setattr(cli, 'get_default_provider', lambda: fake)
    return fake


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
