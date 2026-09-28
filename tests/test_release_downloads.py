from __future__ import annotations

import runpy
import shutil
import tarfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WRITE = runpy.run_path(str(ROOT / 'scripts/publish_container.py'))['write_assets']
VERIFY = runpy.run_path(str(ROOT / 'scripts/verify_release_assets.py'))['verify_assets']
VERSION = (ROOT / 'VERSION').read_text().strip()


@pytest.fixture
def prepared(tmp_path):
    destination = tmp_path / 'prepared'
    WRITE(ROOT, destination, image='ghcr.io/paulkakell/kellmarks', version=VERSION,
          revision='a' * 40, digest='sha256:' + 'b' * 64, anonymous_pull=True)
    return destination


def test_public_asset_name_and_archive_template_are_consistent(prepared):
    assert (prepared / 'env.docker.example').read_bytes() == (ROOT / '.env.docker.example').read_bytes()
    assert not any(p.name.startswith('.') for p in prepared.iterdir())
    with tarfile.open(prepared / f'kellmarks-{VERSION}-docker.tar.gz') as archive:
        assert '.env.docker.example' in archive.getnames()
        template = archive.extractfile('.env.docker.example')
        assert template is not None
        assert template.read() == (prepared / 'env.docker.example').read_bytes()
    assert '  env.docker.example\n' in (prepared / 'SHA256SUMS').read_text()
    assert '  .env.docker.example\n' not in (prepared / 'SHA256SUMS').read_text()


def test_download_examples_use_actual_asset_names():
    guide = (ROOT / 'docs/GHCR_INSTALLATION.md').read_text()
    assert guide.count(f'/v{VERSION}/env.docker.example') == 2
    assert f'/v{VERSION}/.env.docker.example' not in guide
    assert '--output .env.docker.example' in guide
    assert '-OutFile .env.docker.example' in guide


def test_downloaded_assets_verify(prepared, tmp_path):
    downloaded = tmp_path / 'downloaded'
    shutil.copytree(prepared, downloaded)
    assert VERIFY(prepared, downloaded) == 9


@pytest.mark.parametrize('change', ['rename', 'missing', 'extra', 'content', 'size', 'directory', 'symlink'])
def test_changed_downloads_fail(prepared, tmp_path, change):
    downloaded = tmp_path / 'downloaded'
    shutil.copytree(prepared, downloaded)
    target = downloaded / 'env.docker.example'
    if change == 'rename':
        target.rename(downloaded / 'default.env.docker.example')
    elif change == 'missing':
        target.unlink()
    elif change == 'extra':
        (downloaded / 'unexpected').write_text('extra')
    elif change == 'content':
        content = target.read_bytes()
        target.write_bytes(bytes([content[0] ^ 1]) + content[1:])
    elif change == 'size':
        target.write_bytes(target.read_bytes() + b'x')
    elif change == 'directory':
        target.unlink()
        target.mkdir()
    else:
        target.unlink()
        target.symlink_to(prepared / 'env.docker.example')
    with pytest.raises(ValueError):
        VERIFY(prepared, downloaded)


def test_download_verification_precedes_latest_promotion():
    source = (ROOT / '.github/workflows/release.yml').read_text()
    assert '$CONTAINER_ASSETS/.env.docker.example' not in source
    steps = yaml.safe_load(source)['jobs']['publish']['steps']
    verification = next(i for i, step in enumerate(steps)
                        if step.get('name', '').startswith('Verify downloaded'))
    latest = next(i for i, step in enumerate(steps)
                  if step.get('name', '').startswith('Promote latest'))
    assert verification < latest
    assert 'gh release download' in steps[verification]['run']
    assert 'scripts/verify_release_assets.py' in steps[verification]['run']
