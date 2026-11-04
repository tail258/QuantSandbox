# Contributing to QuantSandbox

Help make local investment research easier to inspect and reproduce. Small fixes, clear bug reports, tests, translations, and methodology improvements are welcome.

## Start here

Read [README.md](README.md) for installation and workflows, then [AGENTS.md](AGENTS.md) for repository boundaries and calculation rules. Use an issue to discuss a substantial feature or a change to financial, statistical, or execution assumptions before building it.

QuantSandbox is a local, read-only market research workbench. Contributions must preserve these boundaries:

- Keep brokerage connections, live accounts, and order placement outside the product.
- Keep fetching explicit and preserve the source, units, observation/report dates, known publication dates, fetch time, and failure reasons. Missing observations remain missing.
- Associate asynchronous results with the project that initiated them. Reuse the selected fixed snapshot when bridging research to a strategy experiment.
- Keep Obsidian optional: export by default; direct writes require a deliberate single action, preserve existing notes, and never scan a personal vault automatically.
- Keep user text, original documents, dataset values, and archived evidence intact when changing language or theme.

## Development on Windows

Use Python 3.12+, Node.js 22.12+, and PowerShell 7. From the repository root:

```powershell
pwsh -NoProfile -File scripts/setup.ps1
pwsh -NoProfile -File scripts/dev.ps1
```

The development frontend uses port 5174 and the API uses port 8000. Check for an existing service first; stop only processes belonging to your own workspace. Add `-MarketData` to setup only when you need the optional public market-data providers. API documentation is available at `/docs` on the running backend.

The main areas are `frontend/src`, `backend/workbench` (research), `backend/core` (backtesting), and `backend/integrations` (optional integrations). See [architecture](docs/ARCHITECTURE.md) and the [API contract](docs/API_CONTRACT.md).

## Make the result reproducible

Start a bug report with a small synthetic input whenever possible. Include exact steps, the version or commit, parameters, and expected versus observed behavior. For data-dependent issues, describe the source, units, dates, adjustment basis, and selected snapshot without uploading a personal cache.

For calculation changes, hold the input snapshot fixed and reconcile outputs, ledger entries, and evidence. Preserve unknown publication dates as unknown; currently revised financial statements are not point-in-time historical versions. Update the relevant [methodology documents](docs/methodology.md) when assumptions change.

Use regression tests that exercise the failure. Frontend tests should drive actual React interactions with jsdom and Testing Library, including project switches, late responses, blind replay, and invalidated note previews when affected. For UI changes, also check the real browser, English and Chinese, both themes, and a narrow viewport.

## Check and submit

Run the checks relevant to your edit, then the complete local check before submitting code:

```powershell
pwsh -NoProfile -File scripts/check.ps1
```

This runs backend pytest, frontend interaction tests, and the production build. CI runs backend checks on Windows and Linux, plus frontend tests and build. Report what you ran and any checks you could not complete; preserve calculation semantics when fixing a failing test.

Open a focused pull request describing the problem, resulting behavior, and validation. Include sanitized screenshots for visible changes and link the relevant issue. Review the staged diff for private content before submitting: `data/`, `exports/`, local company profiles, research records, notes, original attachments, vault settings, tokens, and machine-specific absolute paths belong outside public contributions. Replace sensitive material with a synthetic reproduction; `.gitignore` alone does not sanitize a file or screenshot.

For vulnerabilities, follow [SECURITY.md](SECURITY.md).
