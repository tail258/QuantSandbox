"""QuantSandbox local research API. Start with uvicorn backend.main:app."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
from contextlib import asynccontextmanager
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from backend.api.schemas import (AdvanceRequest, AssistantRequest, BranchRequest,
                                 ExperimentRequest, NoteRequest, RunConfig, SessionRequest, StrategyConfig)
from backend.core.data_center import (DEMO_NOTICE, UNIVERSE, DataCenter, DataUnavailable, canonical_json,
                                      data_root, frame_hash, frame_records, utc_now, validate_frame)
from backend.services.runner import JobRunner
from backend.services.store import Store

VERSION = "2.0.0"


def public_run(run: dict) -> dict:
    return {key: value for key, value in run.items() if key not in {"expected_result", "experiment"}}


def create_app(root: str | Path | None = None, *, run_jobs: bool = True) -> FastAPI:
    selected_root = Path(root) if root else data_root()

    @asynccontextmanager
    async def lifespan(application):
        store = Store(selected_root)
        runner = JobRunner(store) if run_jobs else None
        application.state.store = store
        application.state.runner = runner
        application.state.center = DataCenter(root=selected_root)
        if runner:
            runner.start()
        yield
        if runner:
            runner.close()

    application = FastAPI(title="QuantSandbox Research API", version=VERSION, lifespan=lifespan)
    application.add_middleware(CORSMiddleware,
                               allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                                              "http://localhost:4173", "http://127.0.0.1:4173"],
                               allow_credentials=False, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                               allow_headers=["Content-Type"])

    @application.exception_handler(DataUnavailable)
    async def unavailable_handler(request, exception):
        return JSONResponse(status_code=503, content={"detail": str(exception), "code": "data_unavailable"})

    @application.exception_handler(RequestValidationError)
    async def validation_handler(request, exception):
        # Pydantic's error input can itself contain NaN/Infinity, which cannot
        # be serialized in a strict JSON response. Return useful field paths
        # and messages without echoing the invalid request values.
        errors = [{"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
                  for error in exception.errors()]
        return JSONResponse(status_code=422, content={"detail": errors, "code": "invalid_request"})

    def store() -> Store:
        return application.state.store

    def center() -> DataCenter:
        return application.state.center

    def require_run(identifier: str, completed=False, simulation=False) -> dict:
        run = store().get_run(identifier)
        if run is None:
            raise HTTPException(404, "研究记录不存在")
        if completed and run["status"] != "completed":
            raise HTTPException(409, "研究尚未完成")
        if simulation and run["kind"] not in {"backtest", "branch"}:
            raise HTTPException(422, "此操作需要普通回测或历史分叉结果")
        return run

    def schedule(config, **kwargs):
        if store().active_count() >= 20:
            raise HTTPException(429, "已有 20 个研究排队，请等待任务完成或取消任务")
        run = store().create_run(config, **kwargs)
        if application.state.runner:
            application.state.runner.notify()
        return public_run(run)

    def session_view(identifier: str) -> dict:
        from backend.research import calculate_metrics

        session = store().get_session(identifier)
        if session is None:
            raise HTTPException(404, "推演会话不存在")
        run = require_run(session["run_id"], completed=True, simulation=True)
        result = run["result"]
        series = result["series"]
        cursor = min(session["cursor"], len(series) - 1)
        cutoff = series[cursor]["date"]
        visible_series = [row for row in series if row["date"] <= cutoff]
        visible_trades = [row for row in result["trades"] if row["date"] <= cutoff]
        visible = {"series": visible_series, "trades": visible_trades,
                   "metrics": calculate_metrics(visible_series, visible_trades, run["config"]["account"]["initial_cash"]),
                   "bars": {ticker: [row for row in rows if row["date"] <= cutoff] for ticker, rows in result["bars"].items()},
                   "decisions": [row for row in result["decisions"] if row["date"] <= cutoff],
                   "checkpoints": [row for row in result["checkpoints"] if row["date"] <= cutoff]}
        return {"id": identifier, "run_id": run["id"], "cursor": cursor, "date": cutoff,
                "total_steps": len(series), "revealed": bool(session["revealed"]),
                "revealed_at": session["revealed_at"], "source": run["config"]["source"],
                "synthetic": run["synthetic"], "result": visible}

    @application.get("/api/health")
    def health():
        return {"status": "ok", "version": VERSION, "engine": "event-driven", "storage": "sqlite", "worker": "process"}

    @application.get("/api/catalog")
    def catalog():
        def parameter(key, label, default, minimum, maximum, step=1):
            return {"key": key, "label": label, "default": default, "min": minimum, "max": maximum, "step": step}
        return {"tickers": UNIVERSE, "strategies": [
            {"name": "dual_ma", "label": "双均线趋势", "description": "短期均线高于长期均线时持有，反向退出。",
             "parameters": [parameter("fast_period", "快线周期", 5, 2, 200), parameter("slow_period", "慢线周期", 20, 3, 500)]},
            {"name": "bollinger_bands", "label": "布林带回归", "description": "跌破下轨时买入，突破上轨时退出。",
             "parameters": [parameter("window", "窗口周期", 20, 2, 500), parameter("std_dev", "标准差倍数", 2, .1, 10, .1)]},
            {"name": "rsi_reversal", "label": "RSI 反转", "description": "超卖时买入，超买时退出。",
             "parameters": [parameter("window", "RSI 周期", 14, 2, 500), parameter("buy_threshold", "超卖阈值", 30, 1, 99),
                            parameter("sell_threshold", "超买阈值", 70, 1, 99)]},
            {"name": "momentum", "label": "动量跟随", "description": "区间收益突破阈值时持有，负向突破时退出。",
             "parameters": [parameter("window", "观察周期", 20, 2, 500), parameter("threshold", "收益阈值（小数）", .02, 0, .9, .01)]},
        ], "sources": center().status()["sources"], "defaults": RunConfig().model_dump(mode="json"),
                "capabilities": ["portfolio", "branch", "blind_replay", "pressure", "parameter", "walk_forward",
                                 "evidence_export", "evidence_replay", "notes", "local_research_commands"]}

    @application.get("/api/data/status")
    def data_status():
        return center().status()

    @application.post("/api/runs", status_code=202)
    def create_run(config: RunConfig):
        if config.source == "akshare" and importlib.util.find_spec("akshare") is None:
            raise DataUnavailable("AKShare 尚未安装，请先安装 requirements-market.txt。当前请求没有改用演示数据。")
        if config.source == "demo" and set(config.tickers) - {item["ticker"] for item in UNIVERSE}:
            raise HTTPException(422, "演示行情仅支持目录中列出的示例股票")
        return schedule(config.model_dump(mode="json"))

    @application.get("/api/runs")
    def list_runs(limit: int = Query(default=100, ge=1, le=200)):
        return {"runs": store().list_runs(limit)}

    @application.get("/api/runs/{identifier}")
    def get_run(identifier: str):
        return public_run(require_run(identifier))

    @application.post("/api/runs/{identifier}/cancel")
    def cancel_run(identifier: str):
        run = require_run(identifier)
        if run["status"] not in {"queued", "running"}:
            return public_run(run)
        if application.state.runner:
            application.state.runner.cancel(identifier)
        else:
            store().patch_run(identifier, unless_terminal=True, status="cancelled")
        return public_run(require_run(identifier))

    @application.post("/api/runs/{identifier}/branch", status_code=202)
    def create_branch(identifier: str, request: BranchRequest):
        parent = require_run(identifier, completed=True, simulation=True)
        fork_date = request.fork_date.isoformat()
        if fork_date not in {item["date"] for item in parent["result"]["series"]}:
            raise HTTPException(422, "分叉日期必须为当前研究范围内可见的交易日")
        config = copy.deepcopy(parent["config"])
        config["name"] = request.name or f"{parent['name'][:60]} · {fork_date} 分叉"
        branch = request.model_dump(mode="json", exclude_none=True)
        branch.pop("history", None)
        if parent["branch"]:
            previous = parent["branch"]
            if fork_date < previous["fork_date"]:
                raise HTTPException(422, "子分支不能早于父分支的分叉日期")
            branch["history"] = [*previous.get("history", []), {key: value for key, value in previous.items() if key != "history"}]
            if len(branch["history"]) > 20:
                raise HTTPException(422, "单条研究路径最多支持 20 次分叉")
        return schedule(config, kind="branch", parent_id=identifier, branch=branch, manifest=parent["manifest"])

    @application.post("/api/runs/{identifier}/experiments", status_code=202)
    def create_experiment(identifier: str, request: ExperimentRequest):
        parent = require_run(identifier, completed=True, simulation=True)
        if parent["kind"] == "branch":
            raise HTTPException(422, "请从基线运行实验；分支实验尚未支持。")
        options = request.model_dump(mode="json")
        if request.kind == "parameter":
            options["parameter"] = request.parameter or ("fast_period" if parent["config"]["strategy"]["name"] == "dual_ma" else "window")
            if request.values:
                options["values"] = request.values
            else:
                current = parent["config"]["strategy"]["parameters"].get(options["parameter"], 20)
                candidates = sorted(set(max(2, round(current * scale)) for scale in [.5, .75, 1, 1.25, 1.5]))
                if options["parameter"] == "fast_period":
                    candidates = [value for value in candidates if value < parent["config"]["strategy"]["parameters"].get("slow_period", 20)]
                options["values"] = candidates
            for value in options["values"]:
                strategy = copy.deepcopy(parent["config"]["strategy"])
                strategy["parameters"][options["parameter"]] = value
                try:
                    StrategyConfig.model_validate(strategy)
                except ValidationError as exc:
                    raise HTTPException(422, str(exc)) from exc
        if request.kind == "walk_forward" and len(parent["result"]["series"]) <= request.training_days + request.test_days:
            raise HTTPException(422, "研究时间不足一个完整的训练窗口和样本外窗口，请扩大日期范围。")
        config = copy.deepcopy(parent["config"])
        label = {"pressure": "压力实验", "parameter": "参数实验", "walk_forward": "滚动样本外"}[request.kind]
        config["name"] = f"{parent['name'][:70]} · {label}"
        return schedule(config, kind=request.kind, parent_id=identifier, manifest=parent["manifest"],
                        experiment=options)

    @application.post("/api/runs/{identifier}/sessions")
    def create_session(identifier: str, request: SessionRequest):
        run = require_run(identifier, completed=True, simulation=True)
        if request.cursor >= len(run["result"]["series"]):
            raise HTTPException(422, "推演起点超出研究时间范围")
        session = store().create_session(identifier, request.cursor)
        return session_view(session["id"])

    @application.get("/api/sessions/{identifier}")
    def get_session(identifier: str):
        return session_view(identifier)

    @application.post("/api/sessions/{identifier}/advance")
    def advance_session(identifier: str, request: AdvanceRequest):
        session = store().get_session(identifier)
        if session is None:
            raise HTTPException(404, "推演会话不存在")
        run = require_run(session["run_id"], completed=True, simulation=True)
        store().advance_session(identifier, request.steps, len(run["result"]["series"]) - 1)
        return session_view(identifier)

    @application.post("/api/sessions/{identifier}/reveal")
    def reveal_session(identifier: str):
        session = store().get_session(identifier)
        if session is None:
            raise HTTPException(404, "推演会话不存在")
        run = require_run(session["run_id"], completed=True, simulation=True)
        store().advance_session(identifier, 0, len(run["result"]["series"]) - 1, reveal=True)
        return session_view(identifier)

    @application.get("/api/runs/{identifier}/export")
    def export_run(identifier: str):
        run = require_run(identifier, completed=True)
        datasets = [{"manifest": item, "rows": frame_records(center().load_snapshot(item))} for item in run["manifest"]]
        package = {"format": "quantsandbox-evidence-v2", "exported_at": utc_now(), "engine": run["result"].get("engine", {"version": "unknown", "source_sha256": None}),
                   "run": {key: run[key] for key in ["name", "config", "kind", "branch", "experiment", "result"]},
                   "datasets": datasets, "notice": DEMO_NOTICE if run["synthetic"] else "历史行情研究记录；请核对撮合与公司行为假设。"}
        package["sha256"] = hashlib.sha256(canonical_json(package).encode("utf-8")).hexdigest()
        return JSONResponse(package, headers={"Content-Disposition": f'attachment; filename="quantsandbox-{identifier[:8]}.json"'})

    @application.post("/api/import", status_code=202)
    def import_run(package: dict):
        if package.get("format") != "quantsandbox-evidence-v2":
            raise HTTPException(422, "不支持的研究包格式")
        supplied_hash = package.get("sha256")
        body = {key: value for key, value in package.items() if key != "sha256"}
        try:
            computed_hash = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, "研究包包含无法校验的数值或结构") from exc
        if computed_hash != supplied_hash:
            raise HTTPException(422, "研究包 SHA256 校验失败，内容可能被修改")
        try:
            imported = package["run"]
            config = RunConfig.model_validate(imported["config"]).model_dump(mode="json")
            if imported["kind"] not in {"backtest", "branch", "pressure", "parameter", "walk_forward"}:
                raise ValueError("未知研究类型")
            if imported["kind"] == "branch":
                BranchRequest.model_validate(imported["branch"])
            if imported["kind"] not in {"backtest", "branch"}:
                ExperimentRequest.model_validate(imported["experiment"])
            if not isinstance(imported["result"], dict):
                raise ValueError("研究结果格式无效")
            required = {"backtest": {"metrics", "series", "trades"}, "branch": {"metrics", "series", "trades"},
                        "pressure": {"baseline", "scenarios"}, "parameter": {"baseline", "variants"},
                        "walk_forward": {"metrics", "series", "folds"}}[imported["kind"]]
            if not required <= imported["result"].keys():
                raise ValueError("研究结果缺少可核对的指标或账本字段")
            frames = {}
            for dataset in package["datasets"]:
                manifest = dataset["manifest"]
                frame = validate_frame(pd.DataFrame(dataset["rows"]))
                if frame_hash(frame) != manifest["sha256"]:
                    raise ValueError("数据集 SHA256 校验失败")
                if manifest["source"] != config["source"] or manifest["synthetic"] != (config["source"] == "demo"):
                    raise ValueError("数据来源标记与研究配置不一致")
                if manifest["ticker"] in frames:
                    raise ValueError("研究包存在重复股票数据")
                frames[manifest["ticker"]] = frame
            if set(frames) != set(config["tickers"]):
                raise ValueError("研究包的数据集与股票池不一致")
            branch = imported.get("branch")
            if imported["kind"] == "branch":
                validated = BranchRequest.model_validate(branch)
                valid_dates = {str(pd.Timestamp(value).date()) for frame in frames.values() for value in frame.date
                               if config["start_date"] <= str(pd.Timestamp(value).date()) <= config["end_date"]}
                history = validated.history or []
                events = [*history, {key: value for key, value in branch.items() if key != "history"}]
                previous = config["start_date"]
                normalized_events = []
                for event in events:
                    if "history" in event:
                        raise ValueError("分叉历史必须为平铺事件序列")
                    checked = BranchRequest.model_validate(event).model_dump(mode="json", exclude_none=True)
                    if checked["fork_date"] not in valid_dates:
                        raise ValueError("分叉历史包含研究行情范围外的日期")
                    if checked["fork_date"] < previous:
                        raise ValueError("分叉历史日期必须按先后顺序排列")
                    previous = checked["fork_date"]
                    normalized_events.append(checked)
                branch = normalized_events[-1]
                if len(normalized_events) > 1:
                    branch["history"] = normalized_events[:-1]
            elif branch:
                raise ValueError("只有分叉研究可以携带分叉历史")
        except (ValueError, KeyError, TypeError, DataUnavailable) as exc:
            raise HTTPException(422, f"研究包验证失败：{exc}") from exc
        manifests = [center().snapshot(ticker, frame, config["source"]) for ticker, frame in frames.items()]
        config["name"] = f"导入重放 · {config['name'][:85]}"
        return schedule(config, kind=imported["kind"], branch=branch, manifest=manifests,
                        experiment=imported.get("experiment"), expected_result=imported["result"])

    @application.get("/api/notes")
    def list_notes(run_id: str | None = None):
        return {"notes": store().list_notes(run_id)}

    @application.post("/api/notes", status_code=201)
    def create_note(note: NoteRequest):
        if note.run_id:
            require_run(note.run_id)
        return store().save_note(note.title, note.body, note.run_id)

    @application.put("/api/notes/{identifier}")
    def update_note(identifier: str, note: NoteRequest):
        if not any(item["id"] == identifier for item in store().list_notes()):
            raise HTTPException(404, "笔记不存在")
        if note.run_id:
            require_run(note.run_id)
        return store().save_note(note.title, note.body, note.run_id, identifier)

    @application.patch("/api/runs/{identifier}/notes")
    def run_note(identifier: str, note: NoteRequest):
        require_run(identifier)
        notes = store().list_notes(identifier)
        return store().save_note(note.title, note.body, identifier, notes[0]["id"] if notes else None)

    @application.delete("/api/notes/{identifier}")
    def delete_note(identifier: str):
        if not store().delete_note(identifier):
            raise HTTPException(404, "笔记不存在")
        return {"deleted": True}

    @application.post("/api/assistant/plan")
    def assistant_plan(request: AssistantRequest):
        from backend.assistant import plan_research

        try:
            result = plan_research(request.prompt, request.base_config)
            result["config"] = RunConfig.model_validate(result["config"]).model_dump(mode="json")
        except (ValueError, ValidationError) as exc:
            raise HTTPException(422, f"研究配置未通过校验：{exc}") from exc
        return result

    return application


app = create_app()
