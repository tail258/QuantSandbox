<p align="center">
  <img src="docs/images/readme-header.svg" alt="QuantSandbox — research, test, reproduce" width="100%" />
</p>

<h1 align="center">QuantSandbox</h1>
<p align="center"><strong>Investment research you can trace, test, and reproduce.</strong></p>
<p align="center">A local workbench to research markets, test strategies, and replay results from the same evidence.</p>

<p align="center">
  <a href="https://github.com/tail258/QuantSandbox/actions/workflows/check.yml"><img src="https://github.com/tail258/QuantSandbox/actions/workflows/check.yml/badge.svg" alt="Checks" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-959DA7?style=flat-square" alt="MIT license" /></a>
  <img src="https://img.shields.io/badge/Python-3.12%2B-3776AB?style=flat-square" alt="Python 3.12 or newer" />
  <img src="https://img.shields.io/badge/React-19-61DAFB?style=flat-square" alt="React 19" />
  <img src="https://img.shields.io/badge/markets-read--only-F5C542?style=flat-square" alt="Read-only market access" />
</p>

<p align="center">
  <strong>English</strong> · <a href="README.zh-CN.md">简体中文</a><br />
  <a href="#workbench-preview">Workbench preview</a> · <a href="#quick-start">Quick start</a> · <a href="#reproduce-an-experiment">Reproduce an experiment</a> · <a href="CONTRIBUTING.md">Contribute</a> · <a href="https://github.com/tail258/QuantSandbox/releases">Releases</a>
</p>

---

## Workbench preview

![Financial terminal showing a synthetic moving-average backtest with a price chart, trade evidence, and replay controls](docs/images/replay-synthetic-en.png)

*Strategy replay in the Financial terminal theme. The example uses synthetic prices, even where the interface shows a real ticker. It illustrates the workflow, not investment performance.*

Start with [the offline example](#reproduce-an-experiment) to generate and verify the same evidence without a live-data account.

## One workspace, from question to evidence

QuantSandbox connects a research question to its data, assumptions, experiments, and saved conclusions. The browser, CLI, and API share the same Python calculations. Data and research records stay in your local workspace. Fetch public market data on demand; ETF flows also supports a local daily refresh schedule.

<table>
  <tr>
    <td width="50%"><strong>01 · Research</strong><br />Compare quarterly financials and peers using company-specific templates. Track industry indicators, ETF flows, and disclosed institutional holdings.</td>
    <td width="50%"><strong>02 · Test</strong><br />Explore correlation, lags, and conditional probabilities. Inspect execution, fees, cash, and positions through backtests and historical replay.</td>
  </tr>
  <tr>
    <td><strong>03 · Reproduce</strong><br />Keep fixed snapshots, saved parameters, source metadata, and execution fingerprints. Export an evidence bundle and recompute it.</td>
    <td><strong>04 · Keep your workflow</strong><br />English or Chinese. Classic light or Financial terminal. Download Markdown, SVG charts, and attachments; Obsidian integration is optional.</td>
  </tr>
</table>

The workbench focuses on mainland China's A-share market. Its daily strategies include dual moving averages, Bollinger bands, RSI reversal, and momentum. You can compare the dual moving-average rule with volume confirmation or volatility-based entry sizing, and use budgeted buy and hold as a control. Experiments include historical forks, cost stress, parameter sensitivity, rolling out-of-sample evaluation, and blind replay.

## US company research · initial scope

A separate US research module starts with **McDonald’s (NYSE: MCD)**: explicitly refresh public SEC annual financial facts and filing references, import USD unadjusted daily OHLCV CSV with a source URL, and save research evidence to a local project. English/Chinese UI is supported. US prices do not enter the A-share backtest engine. SEC access needs a user-configured identifying User-Agent; no paid data subscription is required for SEC data or manual imports. See the [US research guide](docs/us-equities.md) for setup, provenance and limits.

## Quick start

**Choose a source:** Use the commands below for the current public main branch, or download the [tagged source release](https://github.com/tail258/QuantSandbox/releases/tag/v3.2.0) for a fixed version. Use main for the latest instrument research, daily Chan replay, and strategy updates described here.

**Windows:** Python **3.12+**, Node.js **22.12+**, and PowerShell **7+**. Python 3.12 and Node 22 are used by CI. Installation needs internet access for dependencies; the synthetic example runs offline after installation.

```powershell
git clone https://github.com/tail258/QuantSandbox.git QuantSandbox
Set-Location QuantSandbox
.\setup.cmd
.\start.cmd
```

Open **http://127.0.0.1:8766**. The service listens on your computer only. On later visits, run `start.cmd`; stop this workspace with `pwsh -NoProfile -File stop.ps1`.

Windows setup also configures the project-local QuantSandbox MCP server. Codex can find research projects, reuse frozen data, preview and submit backtests, read evidence, and save conclusions. If already installed, run `pwsh -File scripts/enable-codex.ps1` to configure MCP. See the [Codex workflow (Chinese)](docs/codex-workflow.zh-CN.md).

The interface starts in **English**. Use the top-bar language and **Appearance** selectors to switch to Chinese or the dark Financial terminal theme. Preferences stay in the current browser. Company names, user notes, source documents, and archived evidence retain their original text.

**ETF refresh:** use **Refresh now** on ETF flows, or let the workspace fetch daily at **15:30 Asia/Shanghai** by default. You can change the time or disable automatic fetching. The service must be running; source dates and warnings show whether the latest shares and NAVs have actually been published. See the [ETF methodology](docs/etf-methodology.md).

ETF flows also offers lightweight batch quotes and same-time turnover comparisons using completed five-minute bars. Quote polling and historical baseline updates run separately; source times, eligible samples and missing data stay visible. See the [intraday guide](docs/etf-intraday.md).

<details>
<summary><strong>Preview the offline synthetic ETF example</strong></summary>

![Synthetic ETF example: fixed artificial inputs, source precision, 20 samples and a 1.5 turnover ratio](docs/images/etf-demo-en.png)

Open **ETF flows → View synthetic demo**. The example uses artificial data and a fixed clock; it does not download prices or replace your research data.

</details>

<details>
<summary><strong>Manual setup, including Linux/macOS</strong></summary>

The backend and frontend are tested on Linux; the convenience launchers target Windows. From the repository root, create and activate a Python virtual environment using your platform's commands, then run:

```sh
python -m pip install -r requirements-dev.txt -c requirements-lock.txt
npm ci --prefix frontend
npm run build --prefix frontend
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8766
```

For production-only Python dependencies, use `requirements.txt`; add `requirements-market.txt` for live providers. The offline reproduction tool requires the development dependencies. The lock file constrains Python dependency versions, and `npm ci` uses the committed package lock.

</details>

On the **Projects** home page, choose **Open offline strategy demo**. Start with a daily moving-average question, run the baseline, change the windows on the same synthetic snapshot, and replay the evidence. The demo needs the local service and leaves your research projects, runs, and caches untouched.

Use **Chan structure** in a research project to inspect daily fractals, strokes, segments, and centers on a fixed snapshot or in the offline example. Step through when each structure appears and is confirmed, then download and verify the original replay evidence. See the [daily replay guide (Chinese)](docs/chan-replay.zh-CN.md) and the [project handoff (Chinese)](HANDOFF.md).

Read the [first-run guide](docs/getting-started.md) for the strategy and ETF demos, refresh controls, and a first saved research project. Maintainers can follow the [release readiness checklist](docs/release-readiness.md).

## Reproduce an experiment

Run a complete synthetic example without starting a server or downloading market data:

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/reproduce.py
```

The command creates isolated temporary stores, runs a backtest, exports its evidence, imports the original JSON into a second store, and verifies the replay against fixed expectations. It exits with a failure if verification fails. To open the example shown above in the workbench, first keep the evidence file in a new, empty directory:

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/reproduce.py --output exports/repro-demo
```

Open **Validation → Strategies & replay**, choose **Record actions → Import evidence package**, and select the original `exports/repro-demo/evidence.json` file.

This example is explicitly synthetic. Your existing datasets, research projects, and notes are not used. See the [reproducibility guide](docs/reproducibility.md) for the fixture, checks, and tagged-release instructions, and the [release guide](docs/releases.md) for archive checksums and rebuilding from source.

## A practical research loop

1. **Choose a question.** Create a project and select its securities, company template, peers, and research focus.
2. **Check the inputs.** Reuse cached data or fetch/import a snapshot. Read each series' actual coverage, source, unit, reporting period, and availability date.
3. **Compare and test.** Analyze quarterly financials and industry series, then bridge a specific unadjusted-price snapshot into strategy experiments.
4. **Inspect the path.** Review signals, next-session execution, fees, positions, and the account ledger. Compare alternative assumptions on the same inputs.
5. **Save the evidence.** Link analyses and experiments to the project, save a conclusion, and choose what to export.

## Data and calculation boundaries

| Topic | What the workbench preserves |
| --- | --- |
| Missing data | Missing values remain missing. Provider failures stay visible; live-data failures never silently become synthetic prices. |
| Financial statements | Income and cash-flow cumulative amounts are split into quarters; balance-sheet balances are not differenced. Ratios are recomputed. Currently revised statements are not a complete historical point-in-time archive. |
| Statistics | Transform, alignment, frequency, lag direction, sample count, baseline, and interval accompany the result. Correlation and repeated parameter searches need separate validation. |
| Execution | Daily closing signals execute no earlier than the next tradable session's open. Suspension, price limits, and sourced gross cash dividends survive snapshots and replay. Cash dividends are credited after the payment-date opening match. Dividend tax, non-cash actions, and complete delisting returns are outside the model. |
| Market proxies | ETF subscriptions/redemptions and margin data cannot identify a specific trading entity. State-backed holdings require original disclosure evidence. RU0 is a vendor continuous series, not a directly tradable total-return contract. |
| Evidence | Content hashes check integrity. Import replays the saved inputs with the current engine and reports differences. A hash is not third-party certification. |

Method details: [backtesting](docs/RESEARCH_NOTES.md) · [financials and statistics](docs/methodology.md) · [ETF flows](docs/etf-methodology.md) · [institutional disclosures](docs/national-methodology.md). These detailed methodology documents are currently in Chinese; the [API contract](docs/API_CONTRACT.md), [architecture](docs/ARCHITECTURE.md), and reproduction guide are in English.

## Local data and optional notes

The strategy store lives under `data/`; company research uses `data/workbench/`. Local data, exports, attachments, company profiles, environment settings, dependencies, and build output are excluded from Git and release packages. Back up `data/` and `exports/` separately when the service is stopped.

Markdown and attachment downloads work without a notebook configuration. Direct Obsidian writing is an explicit, previewed action that creates new files and refuses to overwrite existing notes. There is no vault scan, background sync, or scheduled publishing. See the [integration contract](docs/obsidian.md) (Chinese).

## Develop and contribute

```powershell
pwsh -NoProfile -File scripts/dev.ps1
pwsh -NoProfile -File scripts/check.ps1
```

Development uses frontend port **5174** and API port **8000**. Production uses **8766**. Interactive API documentation is at `/docs`; the research CLI starts with `python -m backend.workbench.cli status`.

Start with [CONTRIBUTING.md](CONTRIBUTING.md). Report a reproducible problem using the [bug form](https://github.com/tail258/QuantSandbox/issues/new?template=bug_report.yml), propose an improvement using the [feature form](https://github.com/tail258/QuantSandbox/issues/new?template=feature_request.yml), and follow [SECURITY.md](SECURITY.md) for sensitive reports. The [roadmap](docs/ROADMAP.md) separates current capabilities from planned work. Changes are recorded in the [changelog](CHANGELOG.md).

Licensed under [MIT](LICENSE). Market-data providers have their own terms; the software license does not grant redistribution rights to third-party datasets.
