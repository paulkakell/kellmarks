"""Exercise the real Compose deployment using only disposable test data/volumes."""
from __future__ import annotations

import http.client
import io
import json
import os
import secrets
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'kellmarks:ci'


def main() -> None:
    project = f'kellmarks-test-{secrets.token_hex(5)}'
    token = secrets.token_urlsafe(32)
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith(('KELLMARKS_', 'COMPOSE_'))}

    def run(args: list[str], *, data: bytes | None = None, check: bool = True):
        return subprocess.run(args, cwd=ROOT, env=environment, input=data,
                              capture_output=True, check=check, timeout=180)

    with tempfile.TemporaryDirectory(prefix='kellmarks-docker-') as temporary:
        env_file = Path(temporary) / '.env'
        env_file.write_text(f'KELLMARKS_AUTH_TOKEN={token}\nKELLMARKS_IMAGE={IMAGE}\n'
                            'KELLMARKS_HTTP_PORT=0\nKELLMARKS_EXTERNAL_REQUESTS=0\n'
                            'KELLMARKS_TRUSTED_HOSTS=bookmarks.example.com\n'
                            'KELLMARKS_DOMAIN=bookmarks.example.com\n')
        env_file.chmod(0o600)
        compose = ['docker', 'compose', '--project-name', project,
                   '--env-file', str(env_file), '-f', str(ROOT / 'compose.yaml')]
        try:
            # Fail closed even if someone explicitly tries to disable auth.
            failed = run(['docker', 'run', '--rm', '-e', 'KELLMARKS_REQUIRE_AUTH=0', IMAGE],
                         check=False)
            assert failed.returncode != 0
            assert b'Docker requires KELLMARKS_AUTH_TOKEN' in failed.stderr
            overlay = run([*compose, '-f', str(ROOT / 'compose.https.yaml'),
                           'config', '--format', 'json'])
            config = json.loads(overlay.stdout)
            assert config['services']['kellmarks']['environment']['KELLMARKS_PUBLIC_ORIGIN'] == (
                'https://bookmarks.example.com'
            )
            assert 'caddy' in config['services']
            run([*compose, 'up', '-d', '--wait', '--wait-timeout', '90'])

            def request(method: str, path: str, payload: Any = None, *, auth: bool = True):
                address = run([*compose, 'port', 'kellmarks', '8787']).stdout.decode().strip()
                port = int(address.rsplit(':', 1)[1])
                connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
                headers = {'Host': 'bookmarks.example.com'}
                if auth:
                    headers['Authorization'] = f'Bearer {token}'
                body = None
                if payload is not None:
                    headers['Content-Type'] = 'application/json'
                    body = json.dumps(payload)
                try:
                    connection.request(method, path, body=body, headers=headers)
                    response = connection.getresponse()
                    return response.status, response.read()
                finally:
                    connection.close()

            assert request('GET', '/api/health', auth=False)[0] == 401
            assert request('GET', '/api/entries', auth=False)[0] == 401
            status, body = request('GET', '/api/health')
            assert status == 200 and json.loads(body)['ok'] is True
            assert json.loads(body)['externalRequestsAllowed'] is False
            assert request('GET', '/', auth=False)[0] == 200
            assert request('GET', '/assets/app.js', auth=False)[0] == 200
            for private in ['/assets/data.json', '/server/app.py', '/data/data.json']:
                assert request('GET', private)[0] == 404
            entry = {'title': 'Docker persistence test', 'url': 'https://example.com/docker',
                     'tags': ['docker/test']}
            status, body = request('POST', '/api/entries', entry)
            assert status == 201
            entry_id = json.loads(body)['id']
            container = run([*compose, 'ps', '-q', 'kellmarks']).stdout.decode().strip()
            inspection = json.loads(run(['docker', 'inspect', container]).stdout)[0]
            assert inspection['Config']['User'] == '10001:10001'
            assert inspection['HostConfig']['ReadonlyRootfs'] is True
            assert 'ALL' in inspection['HostConfig']['CapDrop']
            run([*compose, 'exec', '-T', 'kellmarks', 'python', '/app/docker/healthcheck.py'])
            run([*compose, 'up', '-d', '--force-recreate', '--wait', '--wait-timeout', '90'])
            status, body = request('GET', f'/api/entries/{entry_id}')
            assert status == 200 and json.loads(body)['title'] == entry['title']

            # Execute the exact stopped-volume backup/restore method in the guide.
            run([*compose, 'stop', 'kellmarks'])
            backup = run([*compose, 'run', '--rm', '--no-deps', '-T', '--entrypoint', 'tar',
                          'kellmarks', '-C', '/data', '-czf', '-', '.']).stdout
            with tarfile.open(fileobj=io.BytesIO(backup), mode='r:gz') as archive:
                assert './data.json' in archive.getnames()
            run([*compose, 'up', '-d', '--wait', '--wait-timeout', '90'])
            assert request('DELETE', f'/api/entries/{entry_id}')[0] in {200, 204}
            run([*compose, 'stop', 'kellmarks'])
            run([*compose, 'run', '--rm', '--no-deps', '-T', '--entrypoint', 'tar',
                 'kellmarks', '-C', '/data', '-xzf', '-'], data=backup)
            run([*compose, 'up', '-d', '--wait', '--wait-timeout', '90'])
            assert request('GET', f'/api/entries/{entry_id}')[0] == 200
            assert token.encode() not in run([*compose, 'logs', '--no-color']).stdout
            print('Docker smoke passed: authenticated UI/API, non-root/read-only runtime, '
                  'private storage, health, recreation persistence, backup and restore.')
        except (AssertionError, subprocess.SubprocessError):
            # Keep diagnostics useful without ever printing the test credential.
            logs = run([*compose, 'logs', '--no-color'], check=False)
            print(logs.stdout.decode(errors='replace').replace(token, '[REDACTED]'))
            raise
        finally:
            # This random project is created by this test; never remove operator volumes.
            run([*compose, 'down', '--volumes', '--remove-orphans'], check=False)


if __name__ == '__main__':
    main()
