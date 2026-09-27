from __future__ import annotations

import http.client
import json
import runpy
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'docker' / 'gunicorn.conf.py'
HEALTH = ROOT / 'docker' / 'healthcheck.py'


@pytest.mark.parametrize('token', ['', 'short', 'x' * 31, 'x' * 32 + ' ', '\n' + 'x' * 32,
                                  'x' * 32 + '\x01', 'x' * 32 + '\x7f', 'é' * 32])
def test_container_requires_safe_token(monkeypatch, token):
    monkeypatch.setenv('KELLMARKS_AUTH_TOKEN', token)
    with pytest.raises(RuntimeError, match='Docker requires KELLMARKS_AUTH_TOKEN'):
        runpy.run_path(str(CONFIG))


def test_container_forces_authentication_and_single_worker(monkeypatch):
    monkeypatch.setenv('KELLMARKS_AUTH_TOKEN', 'x' * 43)
    monkeypatch.setenv('KELLMARKS_REQUIRE_AUTH', '0')
    config = runpy.run_path(str(CONFIG))
    assert config['os'].environ['KELLMARKS_REQUIRE_AUTH'] == '1'
    assert config['workers'] == 1
    assert config['threads'] == 4
    assert config['worker_class'] == 'gthread'
    assert config['accesslog'] is None
    assert config['forwarded_allow_ips'] == ''
    assert config['secure_scheme_headers'] == {}
    assert config['umask'] == 0o077


@pytest.mark.parametrize(('status', 'body', 'expected'), [
    (200, b'{"ok":true}', 0),
    (401, b'{"error":"authentication required"}', 1),
    (200, b'{"ok":false}', 1),
    (200, b'{"ok":1}', 1),
    (200, b'[]', 1),
    (200, b'<html>not an API</html>', 1),
    (200, b'x' * 8193, 1),
])
def test_healthcheck_authenticates_and_checks_json(monkeypatch, status, body, expected):
    token = 'x' * 43
    monkeypatch.setenv('KELLMARKS_AUTH_TOKEN', token)
    # The healthcheck must work even when loopback isn't a trusted Host.
    monkeypatch.setenv('KELLMARKS_TRUSTED_HOSTS', 'bookmarks.example.com,localhost')
    connection = MagicMock()
    connection.getresponse.return_value.status = status
    connection.getresponse.return_value.read.return_value = body
    constructor = MagicMock(return_value=connection)
    monkeypatch.setattr(http.client, 'HTTPConnection', constructor)
    health = runpy.run_path(str(HEALTH))
    assert health['main']() == expected
    constructor.assert_called_once_with('127.0.0.1', 8787, timeout=3)
    connection.request.assert_called_once_with('GET', '/api/health', headers={
        'Authorization': f'Bearer {token}', 'Host': 'bookmarks.example.com',
    })
    connection.getresponse.return_value.read.assert_called_once_with(8193)
    connection.close.assert_called_once()


def test_healthcheck_fails_without_token(monkeypatch):
    monkeypatch.delenv('KELLMARKS_AUTH_TOKEN', raising=False)
    assert runpy.run_path(str(HEALTH))['main']() == 1


def test_healthcheck_connection_failure_is_quiet(monkeypatch, capsys):
    monkeypatch.setenv('KELLMARKS_AUTH_TOKEN', 'x' * 43)
    connection = MagicMock()
    connection.request.side_effect = OSError('connection refused')
    monkeypatch.setattr(http.client, 'HTTPConnection', MagicMock(return_value=connection))
    assert runpy.run_path(str(HEALTH))['main']() == 1
    assert capsys.readouterr().out == ''
    connection.close.assert_called_once()


def test_docker_does_not_change_application_version_or_schema():
    sample = json.loads((ROOT / 'docs/assets/sample-data.json').read_text())
    assert sample['version'] == 2
    assert 'COPY VERSION LICENSE /app/' in (ROOT / 'Dockerfile').read_text()
    assert 'COPY . ' not in (ROOT / 'Dockerfile').read_text()
