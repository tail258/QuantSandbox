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
