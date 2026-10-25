from unittest.mock import Mock, patch
import pytest
import requests
from sermonflow.providers.esv_api import EsvApiProvider, parse_passage_text
from sermonflow import mcp_server


def test_daniel_range_request():
    response = Mock()
    response.json.return_value = {
        'canonical': 'Daniel 2:24–49',
        'passages': [' '.join(f'[{n}] Verse {n}.' for n in range(24, 50))],
    }
    with patch('sermonflow.providers.esv_api.requests.get', return_value=response) as get:
        verses = EsvApiProvider('secret').fetch_chapter('Daniel 2:24-49')
    assert len(verses) == 26
    assert verses[0][1] == 'Daniel 2:24 ESV'
    assert verses[-1][1] == 'Daniel 2:49 ESV'
    assert get.call_args.kwargs['params']['q'] == 'Daniel 2:24-49'
    assert get.call_args.kwargs['headers'] == {'Authorization': 'Token secret'}


@pytest.mark.parametrize('status, message', [(401, 'authentication'), (403, 'access denied'), (429, 'rate limit'), (500, 'request failed')])
def test_http_errors_are_actionable_and_redacted(status, message):
    response = Mock(status_code=status)
    response.raise_for_status.side_effect = requests.HTTPError('secret', response=response)
    with patch('sermonflow.providers.esv_api.requests.get', return_value=response):
        with pytest.raises(ValueError, match=message) as error:
            EsvApiProvider('secret').fetch_chapter('Daniel 2')
    assert 'secret' not in str(error.value)


@pytest.mark.parametrize('error, message', [(requests.Timeout(), 'timed out'), (requests.ConnectionError(), 'network access')])
def test_network_errors(error, message):
    with patch('sermonflow.providers.esv_api.requests.get', side_effect=error):
        with pytest.raises(ValueError, match=message):
            EsvApiProvider('secret').fetch_chapter('Daniel 2')


def test_does_not_mislabel_other_translation():
    with pytest.raises(ValueError, match='ESV only'):
        EsvApiProvider('secret').fetch_chapter('Daniel 2', 'NIV')


def test_cross_chapter_markers():
    assert parse_passage_text('[2:49] Last. [3:1] First.', 'Daniel 2:49–3:1') == [
        ('Last.', 'Daniel 2:49 ESV'), ('First.', 'Daniel 3:1 ESV')]


def test_mcp_returns_setup_problem(monkeypatch):
    monkeypatch.delenv('ESV_API_KEY', raising=False)
    for tool in (mcp_server.preview_slides, mcp_server.generate_slides):
        result = tool('Daniel 2:24-49')
        assert result['rendered'] is False
        assert 'ESV_API_KEY' in result['problems'][0]
