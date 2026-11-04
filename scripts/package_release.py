"""Build deterministic, source-only releases from immutable tracked Git blobs."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tomllib
import zipfile
from pathlib import Path, PurePosixPath

ROOT_FILES = {
    '.gitignore', 'AGENTS.md', 'LICENSE', 'README.md', 'README.zh-CN.md',
    'README.en.md', 'CONTRIBUTING.md', 'SECURITY.md', 'CHANGELOG.md',
    'config.yaml', 'pyproject.toml', 'package.json', 'package-lock.json',
    'requirements.txt', 'requirements-market.txt', 'requirements-dev.txt',
    'requirements-lock.txt', 'setup.cmd', 'start.cmd', 'start.ps1', 'stop.ps1',
}
SOURCE_DIRS = {'backend', 'frontend', 'scripts', 'tests', 'docs', '.github'}
EXCLUDED_PARTS = {
    'data', 'exports', 'node_modules', 'dist', 'build', '.local', '.venv', 'venv',
    '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', '.git',
    'coverage', '.coverage', 'htmlcov', '.vite', '.cache', 'research_archives',
}
DEPENDENCY_FILES = (
    'requirements.txt', 'requirements-market.txt', 'requirements-dev.txt',
    'requirements-lock.txt', 'package-lock.json', 'frontend/package-lock.json',
)
WINDOWS_RESERVED = {'CON', 'PRN', 'AUX', 'NUL'} | {f'{prefix}{n}' for prefix in ('COM', 'LPT') for n in range(1, 10)}
VERSION_PATTERN = r'\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?'


def git(repo: Path, *args: str) -> bytes:
    return subprocess.run(['git', '-C', str(repo), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def safe_path(name: str) -> bool:
    """Reject paths unsafe on either POSIX or Windows, before creating ZIP members."""
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and '\\' not in name and ':' not in name and all(
        part not in {'', '.', '..'} and not part.endswith((' ', '.')) and part.split('.')[0].upper() not in WINDOWS_RESERVED for part in name.split('/')
    ) and not any(ord(character) < 32 or character in '<>\"|?*' for character in name)


def included(name: str) -> bool:
    if not safe_path(name):
        raise ValueError(f'Unsafe tracked path: {name!r}')
    parts = PurePosixPath(name).parts
    if any(part.lower() in EXCLUDED_PARTS or part.lower().startswith('.env') for part in parts):
        return False
    if name.lower().endswith(('.pyc', '.pyo', '.tsbuildinfo', '.sqlite', '.sqlite3', '.db', '.log', '.zip')):
        return False
    return name in ROOT_FILES or len(parts) > 1 and parts[0] in SOURCE_DIRS


def tracked_files(repo: Path, commit: str) -> dict[str, tuple[str, bytes]]:
    files = {}
    portable_names = set()
    for entry in git(repo, 'ls-tree', '-rz', '--full-tree', commit).split(b'\0'):
        if not entry:
            continue
        metadata, encoded_name = entry.split(b'\t', 1)
        mode, kind, object_id = metadata.decode('ascii').split()
        name = encoded_name.decode('utf-8')
        if included(name):
            if name.casefold() in portable_names:
                raise ValueError(f'Case-insensitive archive path collision: {name}')
            portable_names.add(name.casefold())
            if kind != 'blob' or mode not in {'100644', '100755'}:
                raise ValueError(f'Release sources cannot contain links or submodules: {name}')
            files[name] = (mode, git(repo, 'cat-file', 'blob', object_id))
    return files


def release_version(files: dict[str, tuple[str, bytes]]) -> str:
    def content(name: str) -> bytes:
        if name not in files:
            raise ValueError(f'Missing release metadata: {name}')
        return files[name][1]
    versions = {'pyproject.toml': tomllib.loads(content('pyproject.toml').decode())['project']['version']}
    match = re.search(r'^VERSION\s*=\s*[\'"]([^\'"]+)[\'"]', content('backend/version.py').decode(), re.M)
    if not match:
        raise ValueError('Missing backend VERSION')
    versions['backend/version.py'] = match.group(1)
    for name in ('package.json', 'frontend/package.json', 'package-lock.json', 'frontend/package-lock.json'):
        metadata = json.loads(content(name))
        versions[name] = metadata['version']
        if 'packages' in metadata:
            versions[name + ':root'] = metadata['packages']['']['version']
    version = versions['pyproject.toml']
    if not re.fullmatch(VERSION_PATTERN, version) or set(versions.values()) != {version}:
        raise ValueError(f'Release versions do not agree: {versions}')
    return version


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def package_release(repo: Path, ref: str, output: Path) -> dict:
    commit = git(repo, 'rev-parse', '--verify', '--end-of-options', ref + '^{commit}').decode().strip()
    files = tracked_files(repo, commit)
    version = release_version(files)
    for name in DEPENDENCY_FILES:
        if name not in files:
            raise ValueError(f'Missing dependency metadata: {name}')
    tag = 'v' + version
    if ref.startswith('v') and ref != tag:
        raise ValueError(f'Tag {ref!r} does not match source version {tag!r}')
    output.mkdir(parents=True, exist_ok=True)
    archive_name = f'QuantSandbox-{tag}-source.zip'
    targets = [output / archive_name, output / 'release-manifest.json', output / 'SHA256SUMS']
    if any(path.exists() for path in targets):
        raise FileExistsError('Release output already exists; choose an empty output directory')
    with zipfile.ZipFile(targets[0], 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, (mode, data) in sorted(files.items()):
            member = zipfile.ZipInfo(f'QuantSandbox-{tag}/{name}', date_time=(1980, 1, 1, 0, 0, 0))
            member.create_system = 3
            member.external_attr = (0o100755 if mode == '100755' else 0o100644) << 16
            member.compress_type = zipfile.ZIP_STORED
            archive.writestr(member, data)
    manifest = {
        'schema_version': 1, 'application': 'QuantSandbox', 'version': version,
        'ref': ref, 'commit': commit, 'tag': tag if ref == tag else None,
        'archive': archive_name, 'archive_sha256': digest(targets[0].read_bytes()),
        'file_count': len(files), 'format': 'ZIP_STORED',
        'source_sha256': digest(''.join(f'{mode} {digest(data)}  {name}\n' for name, (mode, data) in sorted(files.items())).encode()),
        'dependency_sha256': {name: digest(files[name][1]) for name in DEPENDENCY_FILES if name in files},
    }
    targets[1].write_bytes((json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode('utf-8'))
    targets[2].write_bytes(''.join(f'{digest(path.read_bytes())}  {path.name}\n' for path in targets[:2]).encode('ascii'))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref', required=True, help='Exact Git tag or commit to package')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = package_release(Path(__file__).resolve().parents[1], args.ref, args.output)
    print(f"Packaged {manifest['archive']} at commit {manifest['commit']}")


if __name__ == '__main__':
    main()
