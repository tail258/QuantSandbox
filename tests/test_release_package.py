"""Release files come from a tagged tree, never local research or build output."""
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from scripts.package_release import included, package_release, safe_path


def command(repo: Path, *args: str) -> str:
    return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repository(tmp_path):
    repo = tmp_path / 'source'
    repo.mkdir()
    command(repo, 'init')
    command(repo, 'config', 'user.name', 'Release test')
    command(repo, 'config', 'user.email', 'release@example.invalid')
    files = {
        'pyproject.toml': '[project]\nname="quantsandbox"\nversion="3.2.0"\n',
        'backend/version.py': 'VERSION = "3.2.0"\n',
        'backend/main.py': 'print("original source")\n',
        'README.md': '# QuantSandbox\n',
        'requirements-lock.txt': 'pytest==9.1.1\n',
        'requirements.txt': 'fastapi==0.141.1\n',
        'requirements-dev.txt': '-r requirements-market.txt\npytest==9.1.1\n',
        'requirements-market.txt': '-r requirements.txt\n',
        'data/.local/obsidian.json': 'private-vault-path',
        'data/workbench/workbench.sqlite': 'private research',
        'exports/note.md': 'private note',
        'frontend/dist/index.html': 'build output',
        'frontend/node_modules/vendor/index.js': 'dependency',
        'backend/__pycache__/main.pyc': 'bytecode',
        'frontend/.env.local': 'SECRET=value',
        'not-allowlisted.txt': 'unreviewed root file',
    }
    for name in ('package.json', 'frontend/package.json', 'package-lock.json', 'frontend/package-lock.json'):
        files[name] = json.dumps({'version': '3.2.0', 'packages': {'': {'version': '3.2.0'}}})
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    command(repo, 'add', '.')
    command(repo, 'commit', '-m', 'Fixture')
    command(repo, 'tag', 'v3.2.0')
    return repo


def test_reproducible_archive_uses_exact_ref_and_excludes_private_artifacts(repository, tmp_path):
    (repository / 'backend/main.py').write_text('dirty working tree', encoding='utf-8')
    (repository / 'backend/untracked.py').write_text('untracked', encoding='utf-8')
    first, second = tmp_path / 'first', tmp_path / 'second'
    manifest = package_release(repository, 'v3.2.0', first)
    package_release(repository, 'v3.2.0', second)
    assert sorted(path.name for path in first.iterdir()) == ['QuantSandbox-v3.2.0-source.zip', 'SHA256SUMS', 'release-manifest.json']
    for path in first.iterdir():
        assert path.read_bytes() == (second / path.name).read_bytes()
    with zipfile.ZipFile(first / manifest['archive']) as archive:
        names = archive.namelist()
        assert names == sorted(names)
        assert archive.read('QuantSandbox-v3.2.0/backend/main.py') == b'print("original source")\n'
        assert not any(any(part in name for part in ('data/', 'exports/', 'node_modules/', 'dist/', '.env', '__pycache__', 'untracked', 'not-allowlisted')) for name in names)
        assert all(member.date_time == (1980, 1, 1, 0, 0, 0) for member in archive.infolist())
        assert all(member.external_attr >> 16 == 0o100644 for member in archive.infolist())
        assert all(member.compress_type == zipfile.ZIP_STORED for member in archive.infolist())
    assert manifest['commit'] == command(repository, 'rev-parse', 'v3.2.0^{commit}')
    assert manifest['tag'] == 'v3.2.0'
    assert manifest['dependency_sha256']['requirements-lock.txt'] == hashlib.sha256(b'pytest==9.1.1\n').hexdigest()
    assert str(repository) not in (first / 'release-manifest.json').read_text()
    for line in (first / 'SHA256SUMS').read_text().splitlines():
        expected, filename = line.split('  ', 1)
        assert hashlib.sha256((first / filename).read_bytes()).hexdigest() == expected
    with pytest.raises(FileExistsError):
        package_release(repository, 'v3.2.0', first)


@pytest.mark.parametrize('name', ['../escape', '/absolute', 'backend/../../escape', 'C:/file', 'backend\\file.py', 'backend/./file.py', 'backend//file.py', 'backend/line\nbreak', 'backend/CON.py', 'backend/file.py.', 'backend/file?.py'])
def test_rejects_unsafe_archive_paths(name):
    assert not safe_path(name)
    with pytest.raises(ValueError):
        included(name)


def test_rejects_version_mismatch(repository, tmp_path):
    command(repository, 'tag', 'v9.0.0')
    with pytest.raises(ValueError, match='does not match'):
        package_release(repository, 'v9.0.0', tmp_path / 'bad-tag')
    (repository / 'backend/version.py').write_text('VERSION="0.0.0"\n', encoding='utf-8')
    command(repository, 'add', '.')
    command(repository, 'commit', '-m', 'Mismatch')
    with pytest.raises(ValueError, match='do not agree'):
        package_release(repository, 'HEAD', tmp_path / 'bad-version')


def test_rejects_tracked_symlinks(repository, tmp_path):
    object_id = command(repository, 'rev-parse', 'HEAD:README.md')
    command(repository, 'update-index', '--add', '--cacheinfo', f'120000,{object_id},backend/link.py')
    command(repository, 'commit', '-m', 'Unsafe link')
    with pytest.raises(ValueError, match='links or submodules'):
        package_release(repository, 'HEAD', tmp_path / 'link')



def test_preserves_tracked_executable_mode(repository, tmp_path):
    command(repository, 'update-index', '--chmod=+x', 'backend/main.py')
    command(repository, 'commit', '-m', 'Executable entry')
    manifest = package_release(repository, 'HEAD', tmp_path / 'executable')
    with zipfile.ZipFile(tmp_path / 'executable' / manifest['archive']) as archive:
        member = archive.getinfo('QuantSandbox-v3.2.0/backend/main.py')
        assert member.external_attr >> 16 == 0o100755
