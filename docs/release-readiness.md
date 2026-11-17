# Release readiness

[简体中文](release-readiness.zh-CN.md) · [Packaging](releases.md) · [First run](getting-started.md)

Record each check as **passed**, **pending confirmation**, or **release blocker**, with the tested source digest, command, actual result and evidence location. Local preview checks cover the preview manifest's exact contents. A synthetic clock or test fixture verifies modeled behavior; real trading-day acceptance requires observations captured at the actual time.

## Build and installation gates

| Gate | Reproduce and acceptable result | Status |
| --- | --- | --- |
| Backend, React interactions and build | `pwsh -NoProfile -File scripts/check.ps1`; all required checks pass | Passed locally; candidate-specific receipt required |
| Offline evidence round trip | `python -X utf8 scripts/reproduce.py`; successful verification without market requests | Passed locally; candidate-specific receipt required |
| Synthetic ETF demo | `python -X utf8 -m backend.workbench.cli etf-intraday-demo`; synthetic marker, 20 samples, 10:30 boundary, ratio 1.5 | Passed locally: CLI exit 0, 2026-11-06 |
| Clean installation | Extract the local preview into a new empty directory; run `setup.cmd`, then `start.cmd`; open the local UI, inspect empty stores and run the offline demos | Passed locally; candidate-specific receipt required |
| Packaging isolation | Inspect ZIP members and manifest; source allowlist only, no data/exports, notes, secrets, dependencies, build output or machine paths | Passed locally; candidate-specific receipt required |
| Real browser | Exercise English/Chinese, themes, narrow viewport, refresh controls and project switching; no stale cross-project result | Passed locally; candidate-specific receipt required |

Failed required gates are release blockers. Keep a clean-install record with OS/runtime versions, source manifest digest, exact commands, exit codes and expected/observed outcomes. Record temporary acceptance locations privately; share repository-relative artifact names and sanitized evidence.

## Real trading-day acceptance still required

Every row below is **pending confirmation** until actual live observations are recorded. Unresolved behavior that presents wrong dates, sources, freshness, amounts or ratios blocks claims of validated live intraday behavior. Offline or preview availability can be documented separately with these limits visible.

| Actual Shanghai-time observation | Steps and acceptable result | Evidence to retain |
| --- | --- | --- |
| 09:25 / 09:30 | Refresh before and at open; auction/pre-open has no current completed-bar ratio; do not fabricate the first 09:35 bar | Provider and receipt times, job and snapshot IDs, phase and missing reason |
| 11:30 | Observe the last morning bar and lunch; boundary freezes at 11:30 and automatic quote polling pauses | Raw responses, comparison boundary, browser request timeline |
| 13:00 | Keep page visible across afternoon resumption; polling resumes, no invented 13:00 completed bar; first regular afternoon bar ends 13:05 | Source clock, bar ends, polling timeline |
| 15:00 | Observe final bar arrival and close; ratio uses available Eastmoney bars through 15:00; later source timestamps remain provider updates | Raw close bars, quote update time, comparison snapshot |
| Overnight / holiday | Reopen next morning and on a known exchange holiday; yesterday's quote retains its date and stale status; no false current session | Exchange calendar reference, source dates, stale flags |
| Delays / gaps / failure | Observe a delayed feed or retained failing request; missing bars exclude affected samples, errors remain visible, old snapshots do not become fresh | Request/receipt times, original errors, sample exclusions |
| Intraday cross-source timing | At an actual intraday cutoff, record Tencent update timing versus Eastmoney completed-bar arrival; preserve discrepancies instead of assuming synchronous or equal totals | Original source fields, units, cutoffs, arrival times and discrepancy |

For each row record observation date, operator, source digest, actual provider dates, acquisition times, IDs, result and remaining question. Retain raw evidence locally. A post-close snapshot alone cannot verify opening/lunch polling behavior. Auction inclusion in the provider's first five-minute bar remains a separate source-methodology question.

Post-close unit checks and cross-source total discrepancies can be inspected outside trading hours; these do not need to wait for the live-session table. Fault-injection tests and actual isolated-process recovery likewise belong to local acceptance. The pending rows above specifically concern actual provider behavior and arrival timing during a market session.

Synthetic demo input SHA-256 observed in the CLI check: `2e40db2dcceefb65040652ae002af26fbb064b5608edc0755d1952e3a7626001`. This identifies the demo input only; build and clean-install evidence remain separate.

## Local acceptance evidence

Local Windows acceptance on 2026-11-06 used a new source extraction, a newly created Python environment (no system site packages), fresh npm installation, locked dependency wheels, the actual setup launcher, offline replay, synthetic demo and browser flows. Process-recovery acceptance actually terminated and restarted an owned isolated server, using a deliberately blocked synthetic provider and cache. This proves process recovery, not live market availability. The temporary-source installation failure caused by an incomplete offline wheel cache and the first mobile overflow observation are retained in local logs; the wheel cache and responsive demo have been corrected.

Keep exact commands, runtime versions, source/archive SHA256, results, screenshots and failures in the local acceptance receipt under .local/release-convergence/. Re-run acceptance for the final preview: this checklist is not a substitute for its receipt. The real-session table above remains pending, as does a new remote CI run until publication is authorized.
