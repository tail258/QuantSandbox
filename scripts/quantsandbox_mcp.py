"""Local MCP tools for the QuantSandbox research workflow."""
from datetime import date
from pathlib import Path
import http.client
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from urllib.parse import urlencode

WORKSPACE = Path(__file__).resolve().parents[1]
PORT = 8766
PROTOCOLS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
BASE_PATH = "/api"
RESPONSE_LIMIT = 32 * 1024 * 1024
LIST_LIMIT = 25
ID = {"type": "string", "pattern": "^[0-9a-f]{32}$"}
SNAPSHOT_ID = {"type": "string", "pattern": "^[0-9a-f]{20}$"}
WINDOW = {"type": "integer", "minimum": 2, "maximum": 60}
TICKER = {"type": "string", "pattern": "^[0-9]{6}$"}
DAY = {"type": "string", "format": "date", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"}
NAME = {"type": "string", "minLength": 1, "maxLength": 100}
PLAN_ID = {"type": "string", "pattern": "^[a-f0-9]{64}$"}
PAGE = {"type": "integer", "minimum": 0}


class ToolError(Exception):
    pass


class ServiceUnavailable(ToolError):
    pass


def api(path, body=None, *, method=None, timeout=20):
    connection = http.client.HTTPConnection("127.0.0.1", PORT, timeout=timeout)
    try:
        connection.request(
            method or ("GET" if body is None else "POST"),
            BASE_PATH + path,
            body=None if body is None else json.dumps(body).encode("utf-8"),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        response = connection.getresponse()
        raw = response.read(RESPONSE_LIMIT + 1)
        if len(raw) > RESPONSE_LIMIT:
            raise ToolError("The result is too large. Open this record in the workbench.")
        if response.status >= 300:
            detail = json.loads(raw).get("detail") if response.status < 500 else None
            raise ToolError(f"QuantSandbox HTTP {response.status}: {detail or response.reason}")
        return json.loads(raw)
    except ConnectionRefusedError as exc:
        raise ServiceUnavailable("QuantSandbox is not running.") from exc
    except (OSError, http.client.HTTPException) as exc:
        raise ToolError("No response from QuantSandbox. Check its service before retrying a write.") from exc
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ToolError("The local service did not return valid QuantSandbox JSON.") from exc
    finally:
        connection.close()


def ready():
    try:
        health = api("/health", timeout=3)
    except ServiceUnavailable:
        if os.name != "nt":
            raise ToolError("Start this workspace's QuantSandbox service on port 8766 first.") from None
        pwsh = shutil.which("pwsh")
        if not pwsh:
            raise ToolError("Open QuantSandbox using its desktop shortcut, then retry.") from None
        try:
            launched = subprocess.run(
                [pwsh, "-NoProfile", "-Sta", "-File", str(WORKSPACE / "start.ps1"), "-FromCodex", "-Port", str(PORT)],
                cwd=WORKSPACE, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=8, creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ToolError("QuantSandbox did not start. Check the local launcher logs.") from exc
        if launched.returncode:
            raise ToolError("Automatic launch was unavailable. Open QuantSandbox from the desktop and retry.")
        deadline = time.monotonic() + 25
        while True:
            try:
                health = api("/health", timeout=3)
                break
            except ServiceUnavailable:
                if time.monotonic() >= deadline:
                    raise ToolError("QuantSandbox did not start. Check the desktop launcher.") from None
                time.sleep(0.5)
    if (health.get("app") != "QuantSandbox" or health.get("status") != "ok"
            or Path(health.get("workspace", "")).resolve() != WORKSPACE):
        raise ToolError("Port 8766 belongs to another workspace. Use this workspace's service.")
    return health


def page_link(page, **fields):
    return f"http://127.0.0.1:{PORT}/#{page}?{urlencode(fields)}"


def select(record, fields):
    return {key: record[key] for key in fields.split() if key in record}


def limited(key, records, offset=0):
    next_offset = offset + LIST_LIMIT
    return {key: records[offset:next_offset], "total": len(records),
            "next_offset": next_offset if next_offset < len(records) else None}


def workspace_status(health):
    status = api("/research/status")
    return {
        **select(health, "status app version engine storage"),
        **{f"{key}_count": len(status[key]) for key in ("datasets", "series", "events")},
    }


def list_projects(_, offset=0, query=None):
    projects = api("/projects")["projects"]
    if query:
        term = query.strip().casefold()
        projects = [item for item in projects if term in item["name"].casefold()
                    or any(term in symbol.casefold() for symbol in item["symbols"])]
    return limited("projects", [select(item, "id name symbols updated_at") for item in projects], offset)


def get_project(_, project_id):
    return {**api(f"/projects/{project_id}"), "url": page_link("projects", project=project_id)}


def create_project(_, name, question="", symbols=None):
    project = api("/projects", {"name": name, "question": question, "symbols": symbols or []})
    return {**project, "url": page_link("projects", project=project["id"])}


def save_project_conclusion(_, project_id, expected_updated_at, conclusion):
    project = api(f"/projects/{project_id}", {
        "conclusion": conclusion, "expected_updated_at": expected_updated_at,
    }, method="PATCH")
    return {**select(project, "id name conclusion updated_at"), "url": page_link("projects", project=project_id)}


def list_strategy_runs(_, limit=15, project_id=None):
    if project_id is None:
        runs = api(f"/runs?limit={limit}")["runs"]
    else:
        runs = api(f"/projects/{project_id}/strategy-runs?limit={limit}")["runs"]
    return {"runs": [
        {**select(run, "id name status kind updated_at synthetic metrics error"),
         "url": page_link("simulation", project=project_id, run=run["id"]) if project_id else page_link("simulation", run=run["id"])}
        for run in runs
    ]}


def get_strategy_run(_, run_id, wait_seconds=0):
    deadline = time.monotonic() + wait_seconds
    while True:
        run = api(f"/runs/{run_id}")
        if run["status"] not in ("queued", "running") or time.monotonic() >= deadline:
            break
        time.sleep(min(1, max(0, deadline - time.monotonic())))
    result = run.pop("result", None)
    if result is not None:
        summary = select(result, "metrics assumptions data_provenance engine engine_version parameter best_value notice interpretation training_days test_days selection_objective replay_verification")
        for key in ("scenarios", "variants", "folds"):
            if key in result:
                summary[key] = [
                    {k: v for k, v in item.items() if k not in ("trials", "series")}
                    for item in result[key][:LIST_LIMIT]
                ]
                summary[f"{key}_count"] = len(result[key])
        run["result_summary"] = summary
    run["url"] = page_link("simulation", run=run_id)
    if run["status"] == "completed":
        run["evidence_url"] = f"http://127.0.0.1:{PORT}/api/runs/{run_id}/export"
    return run


def list_chan_snapshots(_, project_id, symbol=None, offset=0):
    records = api(f"/projects/{project_id}/chan/snapshots")["snapshots"]
    return limited("snapshots", [item for item in records if symbol is None or item["symbol"] == symbol], offset)


def list_cached_research(_, project_id, offset=0):
    symbols = set(api(f"/projects/{project_id}")["symbols"])
    status = api("/research/status")
    return {
        **limited("datasets", [select(row, "id kind symbol name source source_url fetched_at start end count unit method request")
                               for row in status["datasets"] if row.get("symbol") in symbols], offset),
        "series": [select(row, "id name snapshot_id source unit count start end")
                   for row in status["series"] if row.get("symbol") in symbols][:LIST_LIMIT],
    }


def get_research_record(_, project_id, record_id):
    project = api(f"/projects/{project_id}")
    if not any(link["kind"] == "research" and link["run_id"] == record_id for link in project["links"]):
        raise ToolError("The research record is not linked to this project.")
    record = api(f"/research/runs/{record_id}")
    result = record.pop("result", None)
    if result is not None:
        encoded = json.dumps(result, ensure_ascii=False)
        if len(encoded) <= 32000:
            record["result"] = result
        else:
            record["result_omitted"] = True
    return {**record, "url": page_link("runs", project=project_id, run=record_id)}


def fetch_daily_snapshot(_, project_id, symbol, start_date, end_date):
    project = api(f"/projects/{project_id}")
    if symbol not in project["symbols"]:
        raise ToolError("The requested security is not part of this project.")
    if end_date < start_date or date.fromisoformat(end_date) > date.today():
        raise ToolError("Choose ordered dates ending no later than today.")
    snapshot = api("/research/fetch", {
        "kind": "quotes", "symbol": symbol, "start": start_date, "end": end_date, "adjust": "3",
    }, timeout=65)
    dates = sorted(row["date"] for row in snapshot["rows"] if row.get("date"))
    return {**select(snapshot, "id symbol source source_url fetched_at method unit request cache_status warning"),
            "observations": len(dates), "first_observed_date": dates[0] if dates else None,
            "last_observed_date": dates[-1] if dates else None}


def _decision_result(payload, symbol, project_id, snapshot_id=None, as_of=None):
    view = {key: value for key, value in (("symbol", symbol), ("project", project_id), ("snapshot", snapshot_id), ("as_of", as_of)) if value}
    return {**select(payload, "symbol project_id status refresh_status instrument input warning plan factors structure_observations"),
            "weekly_context": (payload.get("weekly") or {}).get("context"), "url": page_link("stock", **view)}


def get_stock_decision(_, symbol, project_id=None, snapshot_id=None, as_of=None):
    params = {key: value for key, value in (("project_id", project_id), ("snapshot_id", snapshot_id), ("as_of", as_of)) if value}
    payload = api(f"/decision/{symbol}?{urlencode(params)}")
    result = _decision_result(payload, symbol, project_id, snapshot_id, as_of)
    result["factor_selection"] = api(f"/decision/{symbol}/factors?" + urlencode({"project_id": project_id} if project_id else {}))
    return result


def refresh_stock_decision(_, symbol, project_id=None):
    query = urlencode({"project_id": project_id} if project_id else {})
    payload = api(f"/decision/{symbol}/refresh?{query}", method="POST", timeout=120)
    return _decision_result(payload, symbol, project_id)


def evaluate_stock_decision(_, symbol, snapshot_id, project_id=None, as_of=None, holding_sessions=5):
    params = {"snapshot_id": snapshot_id, "holding_sessions": holding_sessions}
    if project_id:
        params["project_id"] = project_id
    if as_of:
        params["as_of"] = as_of
    payload = api(f"/decision/{symbol}/evaluation?{urlencode(params)}", timeout=90)
    payload.pop("observation_exclusions", None)
    for scenario in payload["scenarios"]:
        scenario.pop("observations", None)
        scenario.pop("unscored", None)
    return payload


def save_stock_factors(_, symbol, selected, project_id=None):
    query = urlencode({"project_id": project_id} if project_id else {})
    return api(f"/decision/{symbol}/factors?{query}", {"selected": selected}, method="PUT")


def get_strategy_catalog(_):
    catalog = api("/catalog")
    return {"strategies": catalog["strategies"], "account_defaults": catalog["defaults"]["account"]}


def preview_fixed_backtest(_, project_id, snapshot_ids, config):
    plan = api("/bridge/backtests/preview", {
        "project_id": project_id, "snapshot_ids": snapshot_ids, "config": {**config, "source": "snapshot"},
    })
    plan["submission"] = {
        "project_id": project_id, "snapshot_ids": snapshot_ids, "config": plan.pop("config"),
        "plan_id": plan.pop("plan_id"),
    }
    return plan


def submit_fixed_backtest(_, submission):
    run = api("/bridge/backtests", submission)
    return {**select(run, "id status progress error kind config synthetic manifest"),
            "project_id": submission["project_id"],
            "url": page_link("simulation", project=submission["project_id"], run=run["id"])}


def analyze_chan_snapshot(_, project_id, snapshot_id):
    analysis = api(f"/projects/{project_id}/chan/analyze", {"snapshot_id": snapshot_id})
    result = analysis["result"]
    return {
        "input": analysis["input"],
        "algorithm": result["algorithm"],
        "structure_counts": {layer: len(items) for layer, items in result["structures"].items()},
        "recent_structures": {layer: items[-5:] for layer, items in result["structures"].items()},
        "result_sha256": json.loads(analysis["evidence"])["result_sha256"],
    }


def run_strategy_demo(_, fast_period=5, slow_period=20):
    if fast_period >= slow_period:
        raise ToolError("fast_period must be smaller than slow_period.")
    run = api("/demo/strategy/run", {"fast_period": fast_period, "slow_period": slow_period})
    replay = api("/demo/strategy/replay", {"evidence": run["evidence"]})
    return {
        **select(run, "synthetic snapshot parameters period account metrics result_sha256"),
        "trade_count": len(run["trades"]),
        "replay": select(replay, "matched compared_fields different_fields result_sha256"),
    }


TOOLS = {}


def object_schema(properties, required=()):
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


def register(function, description, properties=None, required=(), *, read_only=True, destructive=False, idempotent=False):
    TOOLS[function.__name__] = (function, {
        "name": function.__name__,
        "description": description,
        "inputSchema": object_schema(properties or {}, required),
        "annotations": {"readOnlyHint": read_only, "destructiveHint": destructive,
                        "idempotentHint": idempotent, "openWorldHint": function in (fetch_daily_snapshot, refresh_stock_decision)},
    })


TEXT = {"type": "string", "maxLength": 20000}
REVISION = {"type": "string", "minLength": 1, "maxLength": 48}
SYMBOL = {"type": "string", "pattern": "^(?:[0-9]{6}|US:[A-Z][A-Z0-9]{0,9}(?:[.-][A-Z0-9]{1,3})?)$"}
SNAPSHOTS = {"type": "array", "items": SNAPSHOT_ID, "minItems": 1, "maxItems": 10, "uniqueItems": True}
STRATEGY = object_schema({
    "name": {"type": "string", "enum": ["dual_ma", "dual_ma_volume", "dual_ma_volatility",
                                        "buy_and_hold", "rsi_reversal", "momentum", "bollinger_bands"]},
    "parameters": {"type": "object", "additionalProperties": {"type": "number"}},
}, ("name",))
ACCOUNT = object_schema({key: {"type": "number"} for key in (
    "initial_cash", "commission_rate", "tax_rate", "min_commission", "slippage_bps", "position_size",
)})
CONFIG = object_schema({
    "name": NAME, "start_date": DAY, "end_date": DAY, "strategy": STRATEGY, "account": ACCOUNT,
    "tickers": {"type": "array", "items": TICKER, "minItems": 1, "maxItems": 10, "uniqueItems": True},
    "source": {"type": "string", "enum": ["snapshot"]},
}, ("name", "tickers", "start_date", "end_date", "strategy"))
PREVIEW = {"project_id": ID, "snapshot_ids": SNAPSHOTS, "config": CONFIG}

register(workspace_status, "Check the running local QuantSandbox version and counts of cached research datasets, series, and events.")
register(list_projects, "Find research projects by name or security. List up to 25 projects per page, most recently updated first. Use next_offset to continue.",
         {"offset": PAGE, "query": NAME})
register(get_project, "Read a specific project's research question, current conclusion, securities, and linked records.",
         {"project_id": ID}, ("project_id",))
register(create_project, "Create a local research project when the user wants a new one. First look for an existing project.",
         {"name": NAME, "question": TEXT, "symbols": {"type": "array", "items": SYMBOL, "maxItems": 40, "uniqueItems": True}},
         ("name",), read_only=False)
register(save_project_conclusion, "Save the requested conclusion in the local project. Read the project first; pass its updated_at as expected_updated_at. Preserve relevant prior text and cite record IDs. If it changed, reread it.",
         {"project_id": ID, "expected_updated_at": REVISION, "conclusion": {**TEXT, "minLength": 1}},
         ("project_id", "expected_updated_at", "conclusion"), read_only=False, destructive=True)
register(list_strategy_runs, "List recent strategy runs with statuses, synthetic-data flags, and metrics. Supply project_id to scope results to that project.",
         {"project_id": ID, "limit": {"type": "integer", "minimum": 1, "maximum": 50}})
register(get_strategy_run, "Read an existing strategy run's inputs, snapshot provenance, status and results. Optionally wait up to 20 seconds. A completed run includes a local evidence download URL.",
         {"run_id": ID, "wait_seconds": {"type": "integer", "minimum": 0, "maximum": 20}}, ("run_id",))
register(list_chan_snapshots, "List fixed, unadjusted daily price snapshots for this project's backtesting or Chan analysis. Inspect actual coverage; dates here are observations.",
         {"project_id": ID, "symbol": TICKER, "offset": PAGE}, ("project_id",))
register(list_cached_research, "List locally cached research datasets and series for the project's securities; includes source, observations and IDs. Does not contact a provider.",
         {"project_id": ID, "offset": PAGE}, ("project_id",))
register(get_research_record, "Read a saved non-strategy research or statistics record linked to this project.",
         {"project_id": ID, "record_id": {"type": "string", "pattern": "^[0-9a-f]{16}$"}}, ("project_id", "record_id"))
register(fetch_daily_snapshot, "Fetch public, unadjusted A-share daily prices when existing snapshots cannot answer the user's task. Reuses matching cache when available and records source, actual dates, and provider warnings. Use earlier dates for warmup.",
         {"project_id": ID, "symbol": TICKER, "start_date": DAY, "end_date": DAY},
         ("project_id", "symbol", "start_date", "end_date"), read_only=False)
register(get_stock_decision, "Read cached Shanghai/Shenzhen stock or ETF conditions, price evidence, factor values and selection. An optional snapshot/cutoff is historical only. Does not contact a provider.",
         {"symbol": TICKER, "project_id": ID, "snapshot_id": SNAPSHOT_ID, "as_of": DAY}, ("symbol",))
register(refresh_stock_decision, "Get completed daily bars for this public Shanghai/Shenzhen instrument when the user requests fresh research. Saves a fixed local snapshot and returns data checks and conditional observations.",
         {"symbol": TICKER, "project_id": ID}, ("symbol",), read_only=False)
register(evaluate_stock_decision, "Read a retrospective event study on a fixed stock/ETF snapshot. Compare same-rule triggered and untriggered dates with explicit reference-price and cost limits. This does not verify execution or a trading edge.",
         {"symbol": TICKER, "project_id": ID, "snapshot_id": SNAPSHOT_ID, "as_of": DAY,
          "holding_sessions": {"type": "integer", "minimum": 1, "maximum": 20}}, ("symbol", "snapshot_id"))
register(save_stock_factors, "Replace the saved daily factor choices for one instrument and optional project when the user wants that choice saved. Read current options and selection with get_stock_decision.",
         {"symbol": TICKER, "project_id": ID, "selected": {"type": "array", "uniqueItems": True, "maxItems": 5,
          "items": {"type": "string", "enum": ["sma20", "sma60", "rsi14", "bollinger20", "relative_volume20"]}}},
         ("symbol", "selected"), read_only=False)
register(get_strategy_catalog, "Read supported strategies, parameter definitions and default simulation fees, slippage, and position sizes.")
register(preview_fixed_backtest, "Validate project, fixed snapshots, observed coverage, warmup and simulation configuration without creating a run. For submission pass its returned submission object unchanged.",
         PREVIEW, PREVIEW)
register(submit_fixed_backtest, "Run and save a historical simulation from preview_fixed_backtest. Automatically links the result to its project. An identical plan returns the same run. Never fetches prices or places trades.",
         {"submission": object_schema({**PREVIEW, "plan_id": PLAN_ID}, (*PREVIEW, "plan_id"))},
         ("submission",), read_only=False, idempotent=True)
register(analyze_chan_snapshot, "Calculate daily Chan structure on an existing project snapshot. Returns structure counts, recent structures, source, coverage, and hashes without fetching or saving data.",
         {"project_id": ID, "snapshot_id": SNAPSHOT_ID}, ("project_id", "snapshot_id"))
register(run_strategy_demo, "Run and replay a moving-average strategy on fixed synthetic prices in temporary storage. Does not fetch data or create a project or strategy record.",
         {"fast_period": WINDOW, "slow_period": WINDOW})


def validate(value, schema, path="arguments"):
    def invalid():
        raise ToolError(f"Invalid {path}. See the tool's argument schema.")

    kind = schema["type"]
    if kind == "object":
        if not isinstance(value, dict) or set(schema.get("required", ())) - value.keys():
            invalid()
        properties = schema.get("properties", {})
        for key, item in value.items():
            field = properties.get(key, schema.get("additionalProperties"))
            if not field:
                invalid()
            validate(item, field, f"{path}.{key}")
    elif kind == "array":
        if not isinstance(value, list) or not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", sys.maxsize):
            invalid()
        for item in value:
            validate(item, schema["items"], f"{path}[]")
        if schema.get("uniqueItems") and len(set(value)) != len(value):
            invalid()
    elif kind == "string":
        if (not isinstance(value, str) or not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", sys.maxsize)
                or ("pattern" in schema and not re.fullmatch(schema["pattern"], value))
                or ("enum" in schema and value not in schema["enum"])):
            invalid()
        if schema.get("format") == "date":
            try:
                date.fromisoformat(value)
            except ValueError:
                invalid()
    elif kind == "integer":
        if (type(value) is not int or not schema.get("minimum", value) <= value <= schema.get("maximum", value)):
            invalid()
    elif kind == "number":
        if type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)):
            invalid()


def call_tool(params):
    try:
        name = params.get("name")
        if not isinstance(name, str) or name not in TOOLS:
            raise ToolError("Unknown QuantSandbox tool.")
        function, spec = TOOLS[name]
        args = params.get("arguments", {})
        validate(args, spec["inputSchema"])
        data = function(ready(), **args)
        return {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}]}
    except ToolError as exc:
        return {"isError": True, "content": [{"type": "text", "text": str(exc)}]}


def dispatch(message):
    method = message.get("method")
    params = message.get("params", {})
    if method == "initialize":
        version = params.get("protocolVersion")
        return {
            "protocolVersion": version if version in PROTOCOLS else PROTOCOLS[0],
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "quantsandbox", "version": "2.0.0"},
            "instructions": (
                "Identify the project and security, then reuse fixed snapshots. Fetch public prices only "
                "when needed. Preview a fixed backtest before submitting; report actual dates, missing "
                "observations and warmup, and use the returned submission unchanged. Follow the user's "
                "request when creating runs or saving conclusions. Keep the run ID, evidence link, "
                "source and assumptions. Never treat paper results as real trades or synthetic data as market evidence."
            ),
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": [spec for _, spec in TOOLS.values()]}
    if method == "tools/call":
        return call_tool(params)
    raise NotImplementedError


def response(message):
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid request"}}
    if "id" not in message:
        return None
    reply = {"jsonrpc": "2.0", "id": message["id"]}
    try:
        if not isinstance(message.get("params", {}), dict):
            reply["error"] = {"code": -32602, "message": "Invalid params"}
        else:
            reply["result"] = dispatch(message)
    except NotImplementedError:
        reply["error"] = {"code": -32601, "message": "Method not found"}
    except Exception as exc:
        print(f"QuantSandbox MCP: {type(exc).__name__}", file=sys.stderr, flush=True)
        reply["error"] = {"code": -32603, "message": "Unexpected local QuantSandbox response"}
    return reply


def main():
    for line in sys.stdin.buffer:
        try:
            reply = response(json.loads(line.decode("utf-8")))
        except (UnicodeError, json.JSONDecodeError):
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        if reply is not None:
            sys.stdout.buffer.write(json.dumps(reply, ensure_ascii=False).encode("utf-8") + b"\n")
            sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
