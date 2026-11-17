# Reproducible source releases

QuantSandbox releases contain source code, dependency locks, tests and documentation. They do not contain an installed Python environment, `node_modules`, a prebuilt frontend, cached market data, research projects, notes, Obsidian settings or exports. Build the frontend locally after installing dependencies.

Each version has three assets:

- `QuantSandbox-v3.2.0-source.zip` (with the version substituted for later releases).
- `release-manifest.json`, recording the exact Git commit and tag, source digest, archive digest, file count and dependency-file SHA-256 hashes.
- `SHA256SUMS`, covering the archive and manifest.

The manifest contains repository-relative names only. It contains no workstation paths or generation time. Source releases use an explicit root-file and source-directory allowlist, read committed Git blobs rather than the working tree, and exclude local data, environments, dependencies and build output even if those files were accidentally tracked. Included symbolic links and submodules are rejected.

## Verify a downloaded release

Keep all three assets together. On Linux or macOS with `sha256sum`:

```sh
sha256sum --check SHA256SUMS
```

This portable Python command also works on Windows from the asset directory:

```sh
python -c "import hashlib,pathlib; rows=[line.split('  ',1) for line in pathlib.Path('SHA256SUMS').read_text().splitlines()]; assert all(hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest()==expected for expected,name in rows), 'Checksum mismatch'; print('Checksums match')"
```

Compare the manifest's `commit` with the release tag in the repository. Checksums detect changed files; their provenance comes from the release and Git reference you obtained them from.

## Run the offline reproduction

Use Python 3.12+ and Node.js 22.12+. From an extracted source directory, create and activate a Python virtual environment, then install the locked backend dependencies:

```sh
python -m pip install -r requirements-dev.txt -c requirements-lock.txt
python scripts/reproduce.py
python -m pytest
npm ci --prefix frontend
npm test --prefix frontend
npm run build --prefix frontend
```

Dependency installation requires network access unless the packages are already available locally. The reproduction command itself uses synthetic fixed inputs, runs without a server and does not fetch market data or access an external note vault. Its results demonstrate reproducible computation; they are not investment performance claims.

## Rebuild the release assets

Packaging requires Git and Python 3.12+, with no third-party Python dependencies. Clone the repository, fetch the desired tag and run:

```sh
git checkout --detach v3.2.0
python scripts/package_release.py --ref v3.2.0 --output release-assets
python scripts/package_release.py --ref v3.2.0 --output release-repeat
```

Both directories must be new or contain no output files with the release asset names. The packager refuses to replace existing assets. Compare the two `SHA256SUMS` files: the archive and manifest should be byte-identical. Local edits and untracked files do not affect the result because packaging reads the tagged tree. The tag must match the version in `pyproject.toml`, backend metadata, both npm package manifests and both npm lockfiles.

ZIP members use sorted paths, a fixed 1980 timestamp, normalized Git executable permissions and uncompressed storage. Uncompressed ZIP avoids compression-library differences across hosts. The ZIP contains one `QuantSandbox-vVERSION/` directory and no parent-relative or absolute members. The manifest is kept beside the archive so its archive checksum has no circular dependency.

## Maintainer publication

Update all version metadata together, run the full checks and offline reproduction, commit the reviewed source, then create and push the matching `vVERSION` tag. Never include local research data or environment files in that commit.

The `Source release` GitHub Actions workflow runs on `v*` tags. It validates the tag against the checked-out commit, checks all version metadata, builds the source assets twice, verifies checksums, runs backend tests and the offline reproduction, and tests/builds the frontend. A separate job receives repository write permission only after every gate passes. It creates the GitHub release and uploads the three validated assets, or adds them to an existing release without replacing existing files. A retry with duplicate asset names fails instead of silently overwriting published evidence.

The regular `Checks` workflow additionally exercises backend tests on Windows and Linux. Release automation builds and tests on Linux. The downloadable asset is a source distribution; users install the locked dependencies and build for their own machine.

## Local preview before committing

A local preview makes the current reviewed working tree available for clean-install acceptance before committing. It is **not an official release**. Use `python scripts/prepare_preview.py --help` for the exact supported options, then generate into a new local output directory. Keep previews and their manifests local; do not upload personal data or acceptance artifacts to GitHub.

```powershell
python scripts/prepare_preview.py --output .local/release-preview
python scripts/prepare_preview.py --verify .local/release-preview
```

The output contains `QuantSandbox-local-preview-source.zip`, `preview-manifest.json` and `SHA256SUMS`. Generate into a new or empty directory. Verification checks the asset checksums and compares included files with the current working tree; subsequent source changes require a new preview and acceptance record. Installed dependencies, build output and acceptance logs never become preview inputs.

The preview uses a source allowlist and records the base HEAD plus content hashes for included working-tree files, including local changes. Its manifest identifies what was actually tested. Inspect the member list before extracting it into a new empty directory, install dependencies there, and follow the [readiness checklist](release-readiness.md). Acceptance of a preview applies only to those recorded contents.

Official `package_release.py` continues to read committed Git blobs from the selected tag. Uncommitted changes never enter an official package. After review, official release checks must run against the final committed source and matching tag; a passing preview does not publish or certify that tag.

本地预览用于在提交前对当前工作树做干净安装验收，**不是正式发行**。用 `python scripts/prepare_preview.py --help` 查看实际参数，在新的本机目录生成；允许列表与 manifest 记录基础 HEAD 及纳入文件的实际内容哈希。先检查包内容，再解压安装；验收结论仅对应这些内容。正式 `package_release.py` 仍只读取选定标签的已提交 Git blob，未提交修改不会进入正式源码包。预览、个人数据及验收产物均留在本机。真实交易日待验项见[清单](release-readiness.zh-CN.md)。
