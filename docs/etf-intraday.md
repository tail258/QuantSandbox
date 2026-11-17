# ETF intraday quotes and same-time turnover

[简体中文](etf-intraday.zh-CN.md)

The ETF flows page separates lightweight quotes from five-minute turnover history. Both use the same local Python calculations through the browser, API and CLI. They are market observations; neither identifies investors or measures ETF subscriptions/redemptions.

## Sources and units

|Series|Source|Normalized units and timing|
|---|---|---|
|Price, previous close, cumulative volume/turnover|Tencent public batch quotes|CNY/share; volume in lots converted to shares ×100; precise turnover from the amount component of field 35, in CNY; field 37 in CNY10,000 is a rounding cross-check|
|Five-minute bars|Eastmoney public unadjusted ETF kline endpoint|Reported interval turnover in CNY, volume lots ×100; Shanghai bar-end timestamps; no price × volume turnover estimate|
|Expected historical sessions|Existing ETF CSI 300 index snapshot|Select the preceding 20 distinct dated sessions, excluding the quote's date; expose incomplete or outdated calendar coverage|

Requests archive raw response bytes, URL, request start, response receipt and SHA256 under the scoped local research directory. Provider timestamps remain separate from acquisition times. These public third-party feeds can be delayed or revised; they are not an exchange tick archive. A timestamp after 15:00 is a provider update timestamp, not proof of a trade at that instant. Whether the first 09:35 bar includes opening auction turnover has not been independently established; the comparison retains the provider's aggregation.

The adapter's field mapping follows [AKShare's ETF implementation](https://github.com/akfamily/akshare/blob/main/akshare/fund/fund_etf_em.py). Local verification checked the implied average price `reported_amount / (reported_volume × 100)` against minute OHLC ranges. Tencent and Eastmoney totals can differ: one 510300 close sample differed by about 0.075%. Therefore Tencent's cumulative amount is displayed separately; it is **not** the numerator of an Eastmoney historical comparison.

## Same-time comparison

For a 10:43 provider quote, the latest completed five-minute boundary is 10:40. The comparison is:

`Eastmoney current-day turnover through 10:40 / mean(Eastmoney prior-session turnover through 10:40)`

The numerator and denominator use the same provider and bar aggregation. The live quote's cumulative turnover through 10:43 is a separate observation. Lunch freezes the boundary at 11:30; the closing comparison uses 15:00. Pre-open/auction periods, unknown or future timestamps, stale source dates and missing current-day bars do not yield a current comparison ratio.

- A historical day needs all 48 regular five-minute bar ends: 09:35–11:30 and 13:05–15:00. Invalid, duplicate or missing bars exclude that day. Missing values are not zero.
- Start with the previous 20 distinct index-calendar dates. Exclude incomplete dates without replacing them with older sessions. The current date and future dates never enter the denominator.
- If the index calendar predates newly observed sessions, its coverage is not accepted as complete. Observed source dates may provide an explicitly **unverified, provisional** reference.
- At least 5 eligible days are required for a provisional ratio. Fewer than 5 yield no ratio. Only 20 eligible dates with covered index-calendar sessions receive complete status. Sample counts, gaps and calendar status remain visible.
- A zero historical denominator yields no ratio. An observed zero numerator remains zero. A missing numerator remains missing.
- During trading, source age above 120 seconds is stale. Same-day lunch/closing snapshots retain their stated boundary; an earlier date stays stale. This does not imply the feed has exchange-grade real-time latency.

## Refresh and evidence

**Refresh lightweight quotes** requests a batch job; repeated requests reuse a 20-second server cache. **Update historical baseline** launches a separate minute-data job. Quote requests do not wait for slow historical downloads. Existing minute caches can refresh at a five-minute TTL; daily ETF refresh also starts a separate baseline warm-up after its daily result is saved. Historical downloading can take longer than a quote request.

Optional automatic quote polling runs every 20 seconds while the page is visible and its Shanghai-time trading session is eligible. It pauses for lunch, after close and when hidden; afternoon resumption and visibility restoration are checked separately. Historical data is not downloaded on every quote tick. The existing 15:30 daily schedule remains independently configurable.

Failures keep prior snapshots and persist errors. A new failed request cannot make old evidence fresh. Jobs are scoped to the local research directory and survive restart as completed/failed/interrupted records. Local archives, jobs and settings are excluded from Git. This module does not update past backtests or publish to external notes.

## API and CLI

- `GET /api/research/etf/intraday?codes=510300,159919`: cached observations, comparisons, source timestamps, source/quote/bar snapshot IDs, provenance, stale flags and errors. No network acquisition.
- `POST /api/research/etf/intraday/refresh` with `{codes:["510300"],history:false,force:false}`: lightweight quote job.
- The same endpoint with `history:true`: separate minute-history job. First-time consumers need both quote and history inputs.
- `GET /api/research/etf/intraday/jobs/{id}`: scoped job progress and errors. An ordinary quote job can report a separate `bar_job_id` for expired existing minute data.

```powershell
.\.venv\Scripts\python.exe -X utf8 -m backend.workbench.cli etf-intraday --codes 510300,159919
.\.venv\Scripts\python.exe -X utf8 -m backend.workbench.cli etf-intraday --codes 510300,159919 --refresh --history
```

The second command waits for both jobs and returns their status with the same dashboard. Acquisition errors remain visible and produce a failure exit code. Cached evidence has no historical point-in-time certification and should not be inserted into old model features as if it had been archived then.
