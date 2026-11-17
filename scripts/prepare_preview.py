"""Snapshot allowed working-tree sources for local installation acceptance, without Git writes.

This does not produce a tagged release. package_release.py remains committed-tree only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.package_release import included, release_version


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args])


def sources(root):
    root = root.resolve()
    names = git(root, 'ls-files', '-z', '--cached', '--others', '--exclude-standard').decode('utf-8').split('\0')
    files, seen = {}, set()
    modes = {}
    for entry in git(root, 'ls-files', '-s', '-z').split(b'\0'):
        if entry:
            meta, name = entry.split(b'\t', 1)
            modes[name.decode('utf-8')] = meta.split()[0].decode()
    for name in sorted(set(names) - {''}):
        if not included(name):
            continue
        path = root / name
        if any(p.is_symlink() for p in [path, *path.parents] if p != root and p.is_relative_to(root)):
            raise ValueError('Preview sources cannot contain links: ' + name)
        if not path.exists():  # A local deletion is part of the preview.
            continue
        if name.casefold() in seen:
            raise ValueError('Case-insensitive preview path collision: ' + name)
        seen.add(name.casefold())
        if not path.resolve().is_relative_to(root) or any(p.is_symlink() for p in [path, *path.parents] if p != root and p.is_relative_to(root)):
            raise ValueError('Preview sources cannot contain links: ' + name)
        mode = modes.get(name, '100644')
        if mode not in ('100644', '100755') or not path.is_file():
            raise ValueError('Preview sources must be regular files: ' + name)
        files[name] = (mode, path.read_bytes())
    return files


def prepare(root, output):
    files = sources(root)
    version = release_version(files)
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('Preview output must be empty; existing evidence is never overwritten')
    records = [{'path': name, 'mode': mode, 'bytes': len(data), 'sha256': sha(data)}
               for name, (mode, data) in sorted(files.items())]
    source_sha = sha(''.join(f"{x['mode']} {x['sha256']}  {x['path']}\n" for x in records).encode())
    archive_name = 'QuantSandbox-local-preview-source.zip'
    with zipfile.ZipFile(output / archive_name, 'x', compression=zipfile.ZIP_STORED) as archive:
        for name, (mode, data) in sorted(files.items()):
            member = zipfile.ZipInfo('QuantSandbox-local-preview/' + name, (1980, 1, 1, 0, 0, 0))
            member.create_system = 3
            member.external_attr = (int(mode, 8)) << 16
            archive.writestr(member, data)
    manifest = {'schema': 'quantsandbox-local-preview-v1', 'official_release': False,
                'source': 'working_tree_including_uncommitted_files', 'version': version,
                'base_commit': git(root, 'rev-parse', 'HEAD').decode().strip(),
                'source_sha256': source_sha, 'archive': archive_name,
                'archive_sha256': sha((output / archive_name).read_bytes()), 'files': records}
    (output / 'preview-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    (output / 'SHA256SUMS').write_text(''.join(f'{sha((output / name).read_bytes())}  {name}\n'
        for name in [archive_name, 'preview-manifest.json']), encoding='ascii')
    return manifest


def verify(root, directory):
    manifest = json.loads((directory / 'preview-manifest.json').read_text(encoding='utf-8'))
    if manifest.get('official_release') is not False:
        raise ValueError('Expected a local preview manifest')
    if manifest.get('archive') != 'QuantSandbox-local-preview-source.zip':
        raise ValueError('Unexpected preview archive name')
    for line in (directory / 'SHA256SUMS').read_text(encoding='ascii').splitlines():
        expected_hash, name = line.split('  ', 1)
        if name not in (manifest['archive'], 'preview-manifest.json'):
            raise ValueError('Unexpected preview checksum member')
        if sha((directory / name).read_bytes()) != expected_hash:
            raise ValueError('Preview checksum differs: ' + name)
    if sha((directory / manifest['archive']).read_bytes()) != manifest['archive_sha256']:
        raise ValueError('Preview archive checksum differs')
    current = sources(root)
    actual = {name: sha(data) for name, (_, data) in current.items()}
    expected = {x['path']: x['sha256'] for x in manifest['files']}
    if actual != expected:
        changed = sorted(set(actual) ^ set(expected) | {name for name in actual.keys() & expected.keys() if actual[name] != expected[name]})
        raise ValueError('Working tree changed since preview: ' + ', '.join(changed))
    return {'matches_current_worktree': True, 'files': len(actual), 'source_sha256': manifest['source_sha256']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--output', type=Path)
    group.add_argument('--verify', type=Path)
    args = parser.parse_args()
    result = verify(ROOT, args.verify) if args.verify else prepare(ROOT, args.output)
    print(json.dumps({k: v for k, v in result.items() if k != 'files'} | {'file_count': len(result['files']) if isinstance(result.get('files'), list) else result.get('files')}, indent=2))


if __name__ == '__main__':
    main()
