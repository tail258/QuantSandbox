"""Evidence validation and deterministic replay submission."""
import hashlib
import pandas as pd
from backend.api.schemas import BranchRequest, ExperimentRequest, RunConfig
from backend.core.data_center import (DEMO_NOTICE, DataCenter, DataUnavailable, canonical_json,
                                     frame_hash, frame_records, utc_now, validate_frame)
from backend.services.errors import ResearchError
from backend.services.research import ResearchService


class EvidenceService:
    def __init__(self, research: ResearchService, center: DataCenter):
        self.research = research
        self.center = center

    def export_run(self, identifier: str):
        run = self.research.require_run(identifier, completed=True)
        datasets = [{"manifest": item, "rows": frame_records(self.center.load_snapshot(item))} for item in run["manifest"]]
        package = {"format": "quantsandbox-evidence-v2", "exported_at": utc_now(), "engine": run["result"].get("engine", {"version": "unknown", "source_sha256": None}),
                   "run": {key: run[key] for key in ["name", "config", "kind", "branch", "experiment", "result"]},
                   "datasets": datasets, "notice": DEMO_NOTICE if run["synthetic"] else "历史行情研究记录；请核对撮合与公司行为假设。"}
        package["sha256"] = hashlib.sha256(canonical_json(package).encode("utf-8")).hexdigest()
        return package

    def import_run(self, package: dict):
        if package.get("format") != "quantsandbox-evidence-v2":
            raise ResearchError(422, "不支持的研究包格式")
        supplied_hash = package.get("sha256")
        body = {key: value for key, value in package.items() if key != "sha256"}
        try:
            computed_hash = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
        except (ValueError, TypeError) as exc:
            raise ResearchError(422, "研究包包含无法校验的数值或结构") from exc
        if computed_hash != supplied_hash:
            raise ResearchError(422, "研究包 SHA256 校验失败，内容可能被修改")
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
            raise ResearchError(422, f"研究包验证失败：{exc}") from exc
        manifests = [self.center.snapshot(ticker, frame, config["source"]) for ticker, frame in frames.items()]
        config["name"] = f"导入重放 · {config['name'][:85]}"
        return self.research.schedule(config, kind=imported["kind"], branch=branch, manifest=manifests,
                        experiment=imported.get("experiment"), expected_result=imported["result"])
