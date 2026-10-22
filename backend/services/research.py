"""Research submission, branching and experiments, independent of HTTP."""
from __future__ import annotations
import copy
import importlib.util
from decimal import Decimal, ROUND_HALF_EVEN
from pydantic import ValidationError
from backend.api.schemas import BranchRequest, ExperimentRequest, RunConfig, StrategyConfig
from backend.core.data_center import UNIVERSE, DataUnavailable
from backend.core.strategy_catalog import strategy_catalog
from backend.services.errors import ResearchError
from backend.services.store import Store


def public_run(run: dict) -> dict:
    return {key: value for key, value in run.items() if key not in {"expected_result", "experiment"}}


def automatic_parameter_values(strategy: dict, parameter: dict) -> list[int | float]:
    """Quantize sensitivity trials to the editor grid, then validate relations."""
    key = parameter["key"]
    current = Decimal(str(strategy["parameters"][key]))
    minimum, maximum, step = (Decimal(str(parameter[k])) for k in ("min", "max", "step"))

    def valid(value):
        candidate = copy.deepcopy(strategy)
        candidate["parameters"][key] = value
        try:
            StrategyConfig.model_validate(candidate)
            return True
        except ValidationError:
            return False

    def number(value):
        return int(value) if step == step.to_integral_value() else float(value)

    values = set()
    for scale in ("0.5", "0.75", "1", "1.25", "1.5"):
        ticks = ((current * Decimal(scale) - minimum) / step).to_integral_value(rounding=ROUND_HALF_EVEN)
        value = minimum + ticks * step
        if minimum <= value <= maximum and valid(number(value)):
            values.add(number(value))
    # At zero or a relational boundary, scaled candidates can collapse to one.
    # Search nearby grid points instead of submitting a doomed experiment.
    if len(values) < 2:
        grid = [minimum + index * step for index in range(int((maximum - minimum) / step) + 1)]
        for value in sorted(grid, key=lambda value: (abs(value - current), value)):
            if valid(number(value)):
                values.add(number(value))
            if len(values) >= 2:
                break
    if len(values) < 2:
        raise ResearchError(422, f"参数 {key} 在当前策略约束下不足两个有效候选值，请调整基线参数或显式指定 values。")
    return sorted(values)


class ResearchService:
    def __init__(self, store: Store, runner=None):
        self.store = store
        self.runner = runner

    def require_run(self, identifier: str, completed=False, simulation=False) -> dict:
        run = self.store.get_run(identifier)
        if run is None:
            raise ResearchError(404, "研究记录不存在")
        if completed and run["status"] != "completed":
            raise ResearchError(409, "研究尚未完成")
        if simulation and run["kind"] not in {"backtest", "branch"}:
            raise ResearchError(422, "此操作需要普通回测或历史分叉结果")
        return run

    def schedule(self, config, **kwargs):
        if self.store.active_count() >= 20:
            raise ResearchError(429, "已有 20 个研究排队，请等待任务完成或取消任务")
        run = self.store.create_run(config, **kwargs)
        if self.runner:
            self.runner.notify()
        return public_run(run)

    def create_run(self, config: RunConfig):
        if config.source == "akshare" and importlib.util.find_spec("akshare") is None:
            raise DataUnavailable("AKShare 尚未安装，请先安装 requirements-market.txt。当前请求没有改用演示数据。")
        if config.source == "demo" and set(config.tickers) - {item["ticker"] for item in UNIVERSE}:
            raise ResearchError(422, "演示行情仅支持目录中列出的示例股票")
        return self.schedule(config.model_dump(mode="json"))

    def list_runs(self, limit: int = 100):
        return {"runs": self.store.list_runs(limit)}

    def get_run(self, identifier: str):
        return public_run(self.require_run(identifier))

    def cancel_run(self, identifier: str):
        run = self.require_run(identifier)
        if run["status"] not in {"queued", "running"}:
            return public_run(run)
        if self.runner:
            self.runner.cancel(identifier)
        else:
            self.store.patch_run(identifier, unless_terminal=True, status="cancelled")
        return public_run(self.require_run(identifier))

    def create_branch(self, identifier: str, request: BranchRequest):
        parent = self.require_run(identifier, completed=True, simulation=True)
        fork_date = request.fork_date.isoformat()
        if fork_date not in {item["date"] for item in parent["result"]["series"]}:
            raise ResearchError(422, "分叉日期必须为当前研究范围内可见的交易日")
        config = copy.deepcopy(parent["config"])
        config["name"] = request.name or f"{parent['name'][:60]} · {fork_date} 分叉"
        branch = request.model_dump(mode="json", exclude_none=True)
        branch.pop("history", None)
        if parent["branch"]:
            previous = parent["branch"]
            if fork_date < previous["fork_date"]:
                raise ResearchError(422, "子分支不能早于父分支的分叉日期")
            branch["history"] = [*previous.get("history", []), {key: value for key, value in previous.items() if key != "history"}]
            if len(branch["history"]) > 20:
                raise ResearchError(422, "单条研究路径最多支持 20 次分叉")
        return self.schedule(config, kind="branch", parent_id=identifier, branch=branch, manifest=parent["manifest"])

    def create_experiment(self, identifier: str, request: ExperimentRequest):
        parent = self.require_run(identifier, completed=True, simulation=True)
        if parent["kind"] == "branch":
            raise ResearchError(422, "请从基线运行实验；分支实验尚未支持。")
        options = request.model_dump(mode="json")
        if request.kind == "parameter":
            options["parameter"] = request.parameter or ("fast_period" if parent["config"]["strategy"]["name"] == "dual_ma" else "window")
            strategy = parent["config"]["strategy"]
            metadata = next(item for item in strategy_catalog() if item["name"] == strategy["name"])
            parameter = next((item for item in metadata["parameters"] if item["key"] == options["parameter"]), None)
            if parameter is None:
                raise ResearchError(422, f"{strategy['name']} 不支持参数 {options['parameter']}")
            if request.values is not None:
                options["values"] = request.values
            else:
                options["values"] = automatic_parameter_values(strategy, parameter)
            for value in options["values"]:
                strategy = copy.deepcopy(parent["config"]["strategy"])
                strategy["parameters"][options["parameter"]] = value
                try:
                    StrategyConfig.model_validate(strategy)
                except ValidationError as exc:
                    raise ResearchError(422, str(exc)) from exc
        if request.kind == "walk_forward" and len(parent["result"]["series"]) <= request.training_days + request.test_days:
            raise ResearchError(422, "研究时间不足一个完整的训练窗口和样本外窗口，请扩大日期范围。")
        config = copy.deepcopy(parent["config"])
        label = {"pressure": "压力实验", "parameter": "参数实验", "walk_forward": "滚动样本外"}[request.kind]
        config["name"] = f"{parent['name'][:70]} · {label}"
        return self.schedule(config, kind=request.kind, parent_id=identifier, manifest=parent["manifest"],
                        experiment=options)
