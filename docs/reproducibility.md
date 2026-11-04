# Reproduce the offline example

QuantSandbox includes one canonical, fully synthetic baseline study that runs without a server, a browser, market-data downloads, research caches, or personal notes. It exercises the same research service, snapshot store, execution worker, evidence exporter, and evidence importer used by the application.

## Run from a tagged checkout

Use a separate checkout of release `v3.2.0`; record the tag and `git rev-parse HEAD` alongside any shared result. For another release, substitute its exact published tag. Python 3.12 or later is required. For release comparisons, use the same Python version and the checked-in dependency lock.

```powershell
git clone --branch v3.2.0 --depth 1 https://github.com/tail258/QuantSandbox.git QuantSandbox-reproduce
Set-Location QuantSandbox-reproduce
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe scripts/reproduce.py
.\.venv\Scripts\python.exe -m pytest tests/test_reproduce.py -q
```

On macOS or Linux, use `.venv/bin/python` in place of `.venv\Scripts\python.exe`. Dependency installation needs package access; the reproduction itself is offline. A frontend installation is unnecessary for this check. The full application frontend uses `frontend/package-lock.json` with `npm ci`.

The script prints a JSON report and returns exit code 0 only when the baseline matches the checked-in reference and evidence replay succeeds. Any calculation failure, replay mismatch, or reference mismatch produces a nonzero exit code, making this command suitable for CI and release validation.

To retain the public example artifacts:

```powershell
.\.venv\Scripts\python.exe scripts/reproduce.py --output-dir exports/repro-demo
```

The directory must be new or empty. Existing files are never overwritten. `evidence.json` is a complete importable evidence package; `report.json` contains the public configuration, metrics, implementation fingerprint, and replay verification. Without `--output-dir`, only the report is printed and temporary files are removed. The report and evidence contain no local absolute paths. The script always computes in fresh temporary baseline and replay stores, even if `QUANT_SANDBOX_DATA_DIR` is set. It does not open the workspace's existing data directory.

## Fixed study and expected values

The example uses `synthetic-regimes-v2`, security code `600036`, a 5/20 dual moving-average strategy, CNY 1,000,000 initial cash, a 30% per-security entry budget, 0.03% commission, CNY 5 minimum commission, 0.05% sell tax, and 5 bps slippage. The study runs from 2024-01-01 through 2024-06-28. Input history begins on 2023-10-02 to warm up the indicators.

These are synthetic prices and a synthetic control fixture, not historical security evidence. The fixture marks 2024-03-04 suspended and all other rows unsuspended. Both price-limit fields remain unknown (`null`); no exchange limits are inferred. Generated dates are weekdays and do not model exchange holidays. Signals execute no earlier than a later tradable open under the engine's documented execution rules.

| Check | Expected value |
| --- | --- |
| Account observations | 130 |
| Executed trades | 6 |
| Final equity (CNY) | 977742.85 |
| Total return (%) | -2.2257 |
| Maximum drawdown (%) | -5.8868 |
| Total fees (CNY) | 970.26 |
| Replay matched | `true` |
| Replay differing fields | `[]` |
| Execution controls | `is_suspended`, `limit_up`, `limit_down` |

The script asserts these deterministic reference fingerprints:

```text
snapshot_sha256 = 0afe8b3aff2f16a919b4c367ed5743942856e93b2abe17df6578dd2a853b4281
result_sha256   = 306799b615aa54232776557d621acaa6c1dd480b2ebd58979f09c678dbbe5648
```

The snapshot fingerprint includes normalized OHLCV and all execution-control fields. The result fingerprint hashes canonical JSON containing `metrics`, `series`, `trades`, and `decisions`. Replay independently compares metrics, account series, and fills through the supported evidence service; the script additionally checks decision equality and the imported snapshot fingerprint.

The full evidence package has its own integrity hash, covering its export timestamp and manifest metadata. That package hash changes between exports. Run identifiers, acquisition/export timestamps, Parquet file hashes, and implementation fingerprints are not substitutes for the stable numerical reference above. The implementation fingerprint records source bytes and can differ with a different checkout, source change, or line-ending conversion; retain it when comparing runs.

## Investigate a mismatch

First verify the release tag, clean working tree, Python version, and installation from `requirements-lock.txt`. Run `python -m pytest tests/test_reproduce.py -q` to check offline execution, data-root isolation, replay, execution-control tamper detection, and overwrite protection. Keep the failing report and compare configuration, snapshot hash, result hash, and engine fingerprint with a clean checkout of the same tag. A changed reference requires review of the data, ledger, and execution evidence; do not update expected hashes merely to make a check pass.

This example validates software reproducibility and evidence integrity. It is not an investment finding: synthetic inputs cannot establish a strategy's real-market performance, and the current engine does not account for dividends and other corporate actions.
