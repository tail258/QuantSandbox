# QuantSandbox V2 API contract

Base `/api`. All dates `YYYY-MM-DD`, amounts CNY, rates in metrics are percentages (12.5 means 12.5%), account fee rates are fractions. API errors use `{detail: string | validationErrors, code?: string}`. Default source is **demo, synthetic prices**; no implicit source fallback. JSON request and response.

## Catalog and data

- `GET /health` → `{status:'ok',version:'2.0.0',engine:'event-driven',storage:'sqlite',worker:'process'}`
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
