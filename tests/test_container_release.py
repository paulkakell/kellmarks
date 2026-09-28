from __future__ import annotations

import hashlib
import io
import json
import runpy
import subprocess
import tarfile
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
RELEASE = runpy.run_path(str(ROOT / 'scripts/publish_container.py'))
VERSION = (ROOT / 'VERSION').read_text().strip()
SHA = 'a' * 40
DIGEST = 'sha256:' + 'b' * 64
IMAGE = 'ghcr.io/paulkakell/kellmarks'


def test_pull_only_compose_keeps_the_source_deployment_contract():
    source = yaml.safe_load((ROOT / 'compose.yaml').read_text())
    registry = yaml.safe_load((ROOT / 'docker-compose.yml').read_text())
    assert source['name'] == registry['name'] == 'kellmarks'
    assert source['volumes'] == registry['volumes']
    expected = dict(source['services']['kellmarks'])
    assert expected.pop('build') == {'context': '.'}
    expected['image'] = '${KELLMARKS_IMAGE:-' + IMAGE + ':' + VERSION + '}'
    expected['pull_policy'] = 'missing'
    assert registry['services']['kellmarks'] == expected
    assert 'extends' not in registry['services']['kellmarks']
    assert 'env_file' not in registry['services']['kellmarks']
    assert 'include' not in registry


@pytest.mark.parametrize(('version', 'revision', 'repository'), [
    ('2.2.0', SHA, 'paulkakell/kellmarks'),
    ('02.02.00;echo unsafe', SHA, 'paulkakell/kellmarks'),
    (VERSION, 'main', 'paulkakell/kellmarks'),
    (VERSION, SHA, '../outside'),
    (VERSION, SHA, 'paulkakell/kellmarks\nother'),
])
def test_release_rejects_invalid_identity(version, revision, repository):
    with pytest.raises(ValueError):
        RELEASE['validate_identity'](version, revision, repository)


def test_release_accepts_version_and_commit():
    assert RELEASE['validate_identity'](VERSION, SHA, 'paulkakell/kellmarks') == IMAGE
    assert RELEASE['checked_digest'](DIGEST) == DIGEST
    with pytest.raises(ValueError):
        RELEASE['checked_digest']('latest')


@pytest.mark.parametrize('platforms', [[], ['amd64'], ['arm64']])
def test_release_requires_both_platforms(platforms):
    manifest = {'manifests': [{'platform': {'os': 'linux', 'architecture': arch}}
                              for arch in platforms]}
    with pytest.raises(ValueError):
        RELEASE['validate_platforms'](manifest)


def test_release_allows_attestations_in_multiarch_index():
    manifest = {'manifests': [{'platform': {'os': 'linux', 'architecture': arch}}
                              for arch in ['amd64', 'arm64']] + [
                                  {'platform': {'os': 'unknown', 'architecture': 'unknown'}}]}
    RELEASE['validate_platforms'](manifest)


@pytest.mark.parametrize(('error', 'missing'), [
    ('manifest unknown', True), ('image: not found', True),
    ('denied: not found', False), ('unauthorized', False),
    ('connection refused', False), ('TLS certificate verification failed', False),
])
def test_registry_error_handling_fails_closed(monkeypatch, error, missing):
    function = RELEASE['inspect_existing']
    runner = Mock(return_value=subprocess.CompletedProcess([], 1, '', error))
    monkeypatch.setitem(function.__globals__, 'run', runner)
    if missing:
        assert function(IMAGE, VERSION, VERSION, SHA) is None
    else:
        with pytest.raises(RuntimeError, match='registry inspection failed'):
            function(IMAGE, VERSION, VERSION, SHA)
    assert runner.call_count == 1


@pytest.mark.parametrize('revision', [SHA, 'c' * 40])
def test_existing_image_revision_is_verified(monkeypatch, revision):
    function = RELEASE['inspect_existing']
    image = [{'Config': {'Labels': {'org.opencontainers.image.version': VERSION,
                                   'org.opencontainers.image.revision': revision}},
              'RepoDigests': [IMAGE + '@' + DIGEST]}]
    responses = [subprocess.CompletedProcess([], 0, json.dumps({'digest': DIGEST}), ''),
                 subprocess.CompletedProcess([], 0, '', ''),
                 subprocess.CompletedProcess([], 0, json.dumps(image), '')]
    monkeypatch.setitem(function.__globals__, 'run', Mock(side_effect=responses))
    if revision == SHA:
        assert function(IMAGE, VERSION, VERSION, SHA) == DIGEST
    else:
        with pytest.raises(RuntimeError, match='refusing to overwrite'):
            function(IMAGE, VERSION, VERSION, SHA)


def test_release_assets_contain_only_public_installation_inputs(tmp_path):
    source = tmp_path / 'source'
    destination = tmp_path / 'dist'
    for name in ['docker-compose.yml', '.env.docker.example', 'compose.https.yaml',
                 'docker/Caddyfile', 'docs/GHCR_INSTALLATION.md', 'docs/INSTALLATION.md']:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('public example\n')
    (source / '.env').write_text('PRIVATE OPERATOR CREDENTIAL')
    (source / 'data.json').write_text('PRIVATE BOOKMARKS')
    RELEASE['write_assets'](source, destination, image=IMAGE, version=VERSION,
                            revision=SHA, digest=DIGEST, anonymous_pull=False)
    metadata = json.loads((destination / 'container.json').read_text())
    assert metadata['reference'] == IMAGE + '@' + DIGEST
    assert metadata['anonymousPullAvailable'] is False
    with tarfile.open(fileobj=io.BytesIO(
        (destination / f'kellmarks-{VERSION}-docker.tar.gz').read_bytes()), mode='r:gz') as archive:
        assert '.env' not in archive.getnames()
        assert 'data.json' not in archive.getnames()
        assert 'docker/Caddyfile' in archive.getnames()
        assert all(not name.startswith('/') and '..' not in Path(name).parts
                   for name in archive.getnames())
    for line in (destination / 'SHA256SUMS').read_text().splitlines():
        checksum, filename = line.split('  ', 1)
        assert hashlib.sha256((destination / filename).read_bytes()).hexdigest() == checksum


def test_release_gates_registry_writes_and_promotes_latest_last():
    workflow = yaml.safe_load((ROOT / '.github/workflows/release.yml').read_text())
    job = workflow['jobs']['publish']
    assert workflow['permissions']['contents'] == 'read'
    assert job['permissions']['packages'] == 'write'
    assert "github.event.workflow_run.event == 'push'" in job['if']
    assert 'head_repository.full_name == github.repository' in job['if']
    assert 'pull_request_target' not in (ROOT / '.github/workflows/release.yml').read_text()
    steps = job['steps']
    gate = next(i for i, step in enumerate(steps) if step.get('name') ==
                'Require successful checks for the exact commit')
    upload = next(i for i, step in enumerate(steps) if step.get('id') == 'container')
    release = next(i for i, step in enumerate(steps) if step.get('name') ==
                   'Publish immutable tag and GitHub release')
    latest = next(i for i, step in enumerate(steps) if step.get('name', '').startswith(
        'Promote latest only'))
    assert gate < upload < release < latest
    for name in ['Tests on Python 3.10', 'Tests on Python 3.13',
                 'Docker server (linux/amd64)', 'Docker server (linux/arm64)',
                 'Analyze python', 'Analyze javascript-typescript']:
        assert name in steps[gate]['run']
    assert 'main_sha' in steps[latest]['run']
    assert 'CONTAINER_ASSETS' in steps[release]['run']
