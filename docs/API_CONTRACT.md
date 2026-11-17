# QuantSandbox API contract

Request validation lives in `backend/api/schemas.py`; response models live in
`backend/api/responses.py`. The running service exposes OpenAPI at `/openapi.json`
and interactive documentation at `/docs`. Responses distinguish each research
kind; a queued/running/failed/cancelled run may have a null result. List items use
`RunSummary` without a result payload.

Base `/api`. All dates `YYYY-MM-DD`, amounts CNY, rates in metrics are percentages (12.5 means 12.5%), account fee rates are fractions. API errors use `{detail: string | validationErrors, code?: string}`. For direct strategy runs the default source is **demo, synthetic prices**; no implicit source fallback. JSON request and response.

## Catalog and data

- `GET /health` → `{status:'ok',version:'3.2.0',engine:'event-driven',storage:'sqlite',worker:'process'}`
- `GET /catalog` → `{tickers:[{ticker,name,sector,demo_name}],strategies:[{name,label,description,parameters:[{key,label,default,min,max,step}]}],sources:[{id,name,available,synthetic,notice,start_date?,end_date?}],defaults:config,capabilities:[...]}`
- `GET /data/status` → `{datasets:[{ticker,source,synthetic,sha256,file_sha256,rows,start_date,end_date,created_at,version,price_basis,volume_unit,notice}],sources:[...],snapshot_count}`

## Runs (persistent asynchronous tasks)

`POST /runs` → HTTP 202 `Run` (poll `GET /runs/{id}` until completed/failed/cancelled).

```json
{"name":"双均线 · 基线","tickers":["000858","601318","600036"],"start_date":"2024-01-01","end_date":"2025-12-31","source":"demo","strategy":{"name":"dual_ma","parameters":{"fast_period":5,"slow_period":20}},"account":{"initial_cash":1000000,"commission_rate":0.0003,"tax_rate":0.0005,"min_commission":5,"slippage_bps":5,"position_size":0.3}}
```

`Run` shape:

```js
{id,name,status:'queued'|'running'|'completed'|'failed'|'cancelled',progress:0..100,
 created_at,updated_at,config,kind:'backtest'|'branch'|'pressure'|'parameter'|'walk_forward',
 parent_id:null|string,branch:null|object,manifest:[],result:null|object,
 error:null|{code,message},synthetic:boolean}
```

- `GET /runs` → `{runs:[RunSummary]}` newest first; summaries omit result and include `metrics: result?.metrics`.
- `GET /runs/{id}` → `Run`.
- `POST /runs/{id}/cancel` → `Run`.
- `POST /runs/{id}/branch` → HTTP 202 `Run`; body `{name?,fork_date,strategy?:{name,parameters},account?:{position_size}}`. Parent must be complete backtest/branch. Parent snapshot reused; nested fork history preserved. A child fork cannot precede its parent fork date; maximum depth 20.
- `POST /runs/{id}/experiments` → HTTP 202 `Run`; body `{kind:'pressure'|'parameter'|'walk_forward', parameter?:'fast_period', values?:[3,5,8,10], training_days?:120,test_days?:40}`. Parent snapshot reused. Engine adds experiment shape below. Run experiments on a baseline; branch experiments explicitly return 422. Omitted parameter/value options generate valid nearby periods for the current strategy.

Backtest/branch `result`:

```js
{metrics:{...},series:[{date,equity,cash,...}],bars:{ticker:[{date,open,high,low,close,volume,...}]},
 trades:[{date,ticker,action:'buy'|'sell',shares,price,fee,reason,signal_date,evidence,realized_pnl}],
 decisions:[{date,ticker,...}],checkpoints:[{date,cash,positions,pending_orders,equity}],assumptions:[],config:{...}}
```

Exact engine metric/decision fields are supplied by the research implementation. `pressure` result `{baseline:metrics,scenarios:[{id,name,metrics,delta_return,...}]}`. `parameter` result `{parameter,baseline:metrics,variants:[{value,metrics}],best_value}`. `walk_forward` result `{folds,series,metrics,...}`. Never interpret parameter best-value as out-of-sample evidence.

Canonical strategies: `dual_ma` (`fast_period`, `slow_period`), `bollinger_bands` (`window`, `std_dev`), `rsi_reversal` (`window`, `buy_threshold`, `sell_threshold`), `momentum` (`window`, `threshold` as fraction). Legacy `sma_cross`/`rsi_reversion` names and short parameter aliases are normalized on input.

Series fields: `date,equity,cash,drawdown,benchmark,daily_return,positions`; `positions` is ticker-keyed with `shares,cost_basis,market_value,unrealized_pnl,entry_date`. Decisions include `id,date,ticker,action,status,reason,evidence`; status is `queued,observed,deferred,rejected,pending`. Metrics include `initial_cash,final_equity,total_return,annualized_return,max_drawdown,benchmark_return,excess_return,sharpe_ratio,win_rate,trade_count,round_trip_count,total_fees,realized_pnl,profit_factor,pnl_ratio`. Null risk/trade ratios mean undefined, never zero.

## Blind replay (server-side projection)

- `POST /runs/{id}/sessions` body `{cursor?:0}` → session below. Only completed backtest or branch accepted.
- `GET /sessions/{id}` → session.
- `POST /sessions/{id}/advance` body `{steps:1}` (1..60) → session.
- `POST /sessions/{id}/reveal` → session. Persists `revealed_at` permanently and expands to the end.

```js
{id,run_id,cursor,date,total_steps,revealed,revealed_at,source,synthetic,
 result:{metrics,series,bars,trades,decisions,checkpoints}}
```

All records and metrics in a blind response are filtered/recomputed through `date`. No full-run config, final metrics, future orders, future prices or run result is included. `total_steps` only describes the replay horizon. Sessions persist on restart; blind advance cannot rewind. Normal research replay can use the complete run data locally.

## Evidence and notes

- `GET /runs/{id}/export` → JSON file (`quantsandbox-evidence-v2`) with config, result, source/engine metadata, manifests and OHLCV data; integrity hash.
- `POST /import` body **original export file text** with `Content-Type: application/json` → HTTP 202 replay Run. Upload the text without a JavaScript parse/stringify round trip: JavaScript would normalize `5.0` to `5` and invalidate this version's checksum. Validates payload/data SHA256, then replays using imported snapshots and reports comparison in `result.replay_verification`.
- `GET /notes?run_id=...` → `{notes:[{id,run_id,title,body,created_at,updated_at}]}`.
- `POST /notes` body `{run_id?:string,title:string,body:string}` → note.
- `PUT /notes/{id}` same body → note.
- `DELETE /notes/{id}` → `{deleted:true}`.
- `PATCH /runs/{id}/notes` body `{title?,body}` creates/updates the latest run note.
- `POST /assistant/plan` body `{prompt,base_config?}` → `{mode:'local_rules',label,recognized,config,changes,experiment,warnings,explanation}`. Deterministic local command parser, not an LLM; returns validated draft without executing it.

Evidence records `result.engine` at execution time, hashing engine, strategies and research code. The export uses that stored fingerprint. SHA256 establishes content integrity, not an authenticated publisher. Import verifies required result fields and data manifests before recomputing the experiment; `result.replay_verification` reports actual equality/differences, not an assertion that the imported conclusions are true.

The service binds localhost. Default data path `data/`; override with `QUANT_SANDBOX_DATA_DIR` for isolated testing. Interrupted active jobs become failed on process restart and remain visible; submit a rerun explicitly.


## Unified investment research (v3)

All research endpoints share the same local server and use `/api/research`: `/status`, `/fetch`, `/series/{id}`, `/snapshot/{id}`, `/finance`, `/profile/{symbol}`, `/import`, `/analyze`, `/save-finance`, `/runs`, `/runs/{id}`, `/export/{id}`, `/research`, `/etf/*`, `/national/*`. Their run IDs and payloads remain independent of strategy runs. Research CLI: `python -m backend.workbench.cli`.

ETF refresh controls use the same research data store:

- `GET /api/research/etf/refresh-settings`: local schedule, `enabled`, `time` (`HH:MM`), `timezone` (`Asia/Shanghai`), `next_run`, `last_job_id`, `last_attempt`, and job `status`.
- `PATCH /api/research/etf/refresh-settings`: accepts only `enabled` (boolean) and `time` (`HH:MM`). Defaults to enabled at 15:30 Shanghai time. Settings stay in the local research directory.
- `POST /api/research/etf/refresh-now`: starts or returns the active refresh job; poll `GET /api/research/etf/jobs/{id}`. It refreshes recent data while retaining prior evidence. A completed job can contain upstream warnings; inspect actual source coverage and dates.
- `POST /api/research/etf/refresh`: retains explicit historical range and force controls.

Scheduling runs only while this workspace service is running, once per local calendar day. An overdue current-day attempt runs after service resumes; missed past days are not replayed as scheduled jobs. Manual retry remains available after failure. `create_app(..., run_jobs=False)` disables automatic scheduling for isolated API tests. This schedule does not access external notebooks.

ETF intraday uses separate quote/history jobs and cached reads: `GET /api/research/etf/intraday?codes=510300,159919`, `POST /api/research/etf/intraday/refresh` with `{codes,history,force}`, and `GET /api/research/etf/intraday/jobs/{id}`. `history:false` refreshes lightweight quotes; `history:true` refreshes minute bars. The dashboard returns individual quote and comparison times, sample counts, snapshot IDs, provenance, stale flags and errors. See the [intraday contract and methodology](etf-intraday.md) for units, bar boundaries, provisional samples, concurrency and CLI behavior.

`GET /api/health` includes `app: QuantSandbox`, `version: 3.1.0`, and the local workspace path for launcher identity. API localhost host/origin rules apply to all modules.

### Sourced execution history and daily paper account

`POST /api/research/execution-history` imports an unadjusted daily OHLCV snapshot with volume in shares. Use the same JSON with `python -m backend.workbench.cli import-execution-history FILE`. Include the price source and acquisition time, the exchange session list, optional explicit suspension/limit fields with their sources, and issuer cash dividend events with their announcement, record, ex-dividend and payment dates. For rule-derived price limits, provide the exchange rule URLs. A `base_snapshot_id` adds evidence to exactly the same historical OHLCV and keeps the old snapshot available. Import returns the new snapshot ID and gap counts. Strategy runs reference that ID through the fixed bridge. Dividend evidence follows the rows and origin in the exported bundle.

Set both `calendar.start_date` and `calendar.end_date` when the source verifies the complete inclusive calendar span, including any non-trading days at its edges. Both dates must lie within the declared history range and contain all listed sessions. With a session list alone, coverage starts at the first listed session and ends at the last. Gap counts are null when the calendar covers only part of the requested interval.

`GET /api/projects/{project_id}/daily-paper` lists the local paper record. `POST` on that path with `{"snapshot_id":"…","as_of":"YYYY-MM-DD"}` seeds a single-security 5/20-day strategy in cash. `POST /api/projects/{project_id}/daily-paper/{account_id}/advance` takes the same payload and reconciles one verified next session after close. The new snapshot must preserve the prior rows and carry the eligible session's own prices, controls, dividend review and next exchange session. Each plan must be saved before that next session opens. Repeating an already accepted observation with the same snapshot does not add a second receipt. The project overview displays and advances the paper account. Collection and advancement are manual. The daily receipt uses the observed opening price with simulated matching after the full daily bar is acquired.

### Offline strategy demo

- `POST /api/demo/strategy/run` accepts `{"fast_period":5,"slow_period":20}` (both defaults). The windows are integer days with `2 ≤ fast < slow ≤ 60`. All runs use the same fixed synthetic daily snapshot and fixed account assumptions. Results include `synthetic`, `snapshot`, `period`, `parameters`, `account`, `metrics`, `series`, `trades`, `result_sha256` and an `evidence` string.
- `POST /api/demo/strategy/replay` accepts `{"evidence":"<original string returned by run>"}`. Preserve the string rather than parsing and serializing its inner JSON in the browser. The server accepts only the fixed demonstration input/configuration, recalculates in a separate temporary store, and returns `matched`, `compared_fields`, `different_fields`, `snapshot_sha256` and `result_sha256`.

Neither endpoint uses market providers or persists data in the research workspace. Demo evidence covers a synthetic example only; replay compares metrics, account series, trades and decisions on that input.

## Instrument decision research

Supports verified Shanghai/Shenzhen listed stocks and ETFs. Optional `project_id` enforces project membership. Session dates use Asia/Shanghai.

- `GET /api/decision/{symbol}` reads cached data. A `snapshot_id` pins an immutable historical-only view. Optional `as_of` truncates the snapshot and requires its ID.
- `POST /api/decision/{symbol}/refresh` updates only this instrument; on refresh failure any prior snapshot remains visible, with current conditions withdrawn. The result includes input provenance and omissions, daily and weekly structures, the plan, descriptive factors and a short tail of causal structure observations.
- `GET /api/decision/{symbol}/factors` reads locally saved choices for the symbol or project/symbol pair. `PUT` with `{"selected":["sma20","relative_volume20"]}` replaces the choices. Supported keys: `sma20`, `sma60`, `rsi14`, `bollinger20`, `relative_volume20`. An empty selection is valid.
- `GET /api/decision/{symbol}/evaluation?snapshot_id=...` computes a retrospective event study on up to 252 sessions; optional `as_of` pins the end date and `holding_sessions` defaults to 5. The result includes verified date coverage, scored and excluded events, an eligible-but-not-triggered comparator, and cost assumptions. Returns are fractional opening-price references, not fills. This endpoint neither writes runs nor refreshes prices.

### Daily Chan structure and replay

- `GET /api/projects/{id}/chan/snapshots` lists fixed unadjusted daily quote snapshots for the project's securities.
- `POST /api/projects/{id}/chan/analyze` takes `{"snapshot_id":"…"}`. It returns `input` (snapshot, source, hashes, dates, coverage and price basis), `bars`, `result` and a raw JSON `evidence` string. Known suspended rows are excluded. Missing verified sessions and unknown suspension counts remain visible. No missing bars are synthesized.
- `POST /api/chan/demo` returns the same shape with fixed synthetic bars and no project. `POST /api/chan/replay` accepts the original evidence bytes as its JSON body, up to 2,000,000 bytes. It recomputes the structure timeline on the bundled bars, checks hashes, and adds `verified: true`.

The input limit is 4,000 observations. `result.frames` identifies which events belong to each observation using end-exclusive slices of `result.events`. Apply those events in order (upsert on create, revise or confirm, remove on removal) to reconstruct each observation. `result.structures` contains the final state. Structural dates and confirmation dates serve different purposes, and neither records when a data provider actually published a historical bar. See the [daily replay guide](chan-replay.zh-CN.md).

### Projects

- `GET /api/projects` -> `{projects:[{id,name,question,symbols,created_at,updated_at,links}]}`.
- `POST /api/projects` body `{name,question?,symbols?:[six-digit-code]}` -> HTTP201 project.
- `GET /api/projects/{id}` -> project.
- `GET /api/projects/{id}/strategy-runs?limit=25` -> `{runs:[RunSummary]}` for that project's linked simulations only.
- `POST /api/projects/{id}/links` body `{kind:'research'|'simulation',run_id}` -> project. Target records are validated; existing links are idempotent.

### Frozen research-price bridge

`POST /api/bridge/backtests` -> HTTP202 strategy Run.

```json
{"snapshot_ids":["20-character-research-snapshot-id"],"project_id":"optional-project-id","config":{"name":"Frozen-price baseline","source":"snapshot","tickers":["600519"],"start_date":"2024-01-01","end_date":"2025-12-31","strategy":{"name":"dual_ma","parameters":{"fast_period":5,"slow_period":20}}}}
```

Provide one immutable quote snapshot per ticker. Each must explicitly declare unadjusted prices and shares-volume units, with source request coverage containing the research interval. All validation precedes scheduling. The bridge retains available pre-start bars for indicator warmup and truncates future bars after the end date. It does not fetch missing data; select a sufficiently long source snapshot first.

For a Codex-driven run, send the same body to `POST /api/bridge/backtests/preview` first. It requires a project, verifies ticker membership and original input integrity, and returns normalized `config`, per-input observations and warmup, warnings, and a `plan_id`. The response gives each calendar's coverage dates and returns a null missing-session count when that coverage cannot verify the whole requested interval. Warmup counts target the final close before the run. An input may need an extra price for returns or an extra eligible volume bar for comparison with prior volume. The preview is read-only. Submit the normalized inputs with `plan_id` to `POST /api/bridge/backtests`. Changed parameters, fixed inputs or engine versions give HTTP 409. Retrying a current plan returns the existing linked run. The browser can submit without a plan.

Strategy manifests add `source:snapshot` and `origin` containing research snapshot ID/hash, original provider URL, fetch time, request, units and transformation. `GET /api/data/status` exposes snapshot availability. Direct `/api/runs` source=snapshot is rejected: fixed data must enter through the bridge or validated evidence import. Snapshot evidence remains in the existing evidence-v2 envelope and preserves origin metadata on replay.

### Optional Obsidian module

See [Obsidian contract](obsidian.md). Defaults disabled; portable export requires no vault configuration. API `/api/obsidian/config` GET/PUT; `/preview`, `/export`, `/publish` POST. Publish requires the exact current preview token and creates new files only.


## Project workspace and execution controls (v3.1)

- Projects include conclusion (empty by default). Existing project tables gain this field without replacing IDs, questions or links.
- PATCH /api/projects/{id}: partial {name?,question?,symbols?,conclusion?,expected_updated_at?}; unknown changes, null field changes and invalid symbols are rejected. Empty text explicitly clears a conclusion. Supply the last read `updated_at` as `expected_updated_at` to reject concurrent changes with HTTP 409.
- Page routes preserve project=<id> independently from run/kind. Project switching changes new research defaults; archived simulations retain their original inputs and source.
- Optional daily execution columns is_suspended (boolean/0/1/null), limit_up and limit_down (positive finite price/null) survive normalization, Parquet, evidence export and replay. Their values participate in content hashes; unknowns remain null. OHLCV-only fingerprints preserve the v2/v3.0 representation.
- Snapshot manifests expose data_schema (ohlcv-v1 or market-daily-v2) and execution_fields; no controls are inferred when absent upstream.

## US company research

These endpoints use base `/api/research/us` and are separate from strategy datasets and runs. US prices are USD; the CNY convention above applies to the existing A-share engine, not these research responses.

- `GET /catalog`: supported company catalog (initially MCD).
- `GET /company/{symbol}`: cached company research; does not implicitly fetch SEC data.
- `POST /company/{symbol}/refresh`: explicitly refresh SEC annual facts and filing references. Requires locally configured `QUANTSANDBOX_SEC_USER_AGENT` identifying the application and real contact.
- `POST /company/{symbol}/prices` with `{ "text": "date,open,high,low,close,volume\n...", "source_url": "https://original-provider.example/data" }`: import user-supplied unadjusted USD daily OHLCV with provenance.
- `POST /company/{symbol}/save` with `{ "project_id": "optional-project-id", "snapshot_ids": ["displayed-sec-snapshot-id", "displayed-price-snapshot-id"] }`: save evidence from the explicitly supplied immutable snapshots (one or two IDs required), optionally linked to the specified project. Async clients must retain the initiating project ID across project switches.

Annual SEC facts may be revised and do not establish historical point-in-time availability. Filing references, report periods, retrieval times, source URLs, units and snapshot identities must accompany interpretation. No US backtest endpoint is provided. See [US company research](us-equities.md) and the running OpenAPI for current response schemas and validation.
