from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class StrategyConfig(StrictModel):
    name: Literal["dual_ma", "rsi_reversal", "momentum", "bollinger_bands"] = "dual_ma"
    parameters: dict[str, float | int] = Field(default_factory=lambda: {"fast_period": 5, "slow_period": 20})

    @model_validator(mode="before")
    @classmethod
    def normalize_names(cls, values):
        if isinstance(values, dict):
            values = dict(values)
            if not isinstance(values.get("name", "dual_ma"), str):
                raise ValueError("策略名称必须为字符串")
            values["name"] = {"sma_cross": "dual_ma", "rsi_reversion": "rsi_reversal"}.get(values.get("name"), values.get("name", "dual_ma"))
            params = values.get("parameters", {})
            if not isinstance(params, dict):
                raise ValueError("策略参数必须为键值对象")
            aliases = {"fast": "fast_period", "slow": "slow_period", "lookback": "window", "period": "window",
                       "oversold": "buy_threshold", "overbought": "sell_threshold"}
            defaults = {"dual_ma": {"fast_period": 5, "slow_period": 20}, "rsi_reversal": {"window": 14, "buy_threshold": 30, "sell_threshold": 70},
                        "bollinger_bands": {"window": 20, "std_dev": 2}, "momentum": {"window": 20, "threshold": .02}}
            values["parameters"] = {**defaults.get(values["name"], {}), **{aliases.get(key, key): value for key, value in params.items()}}
        return values

    @model_validator(mode="after")
    def parameter_bounds(self):
        permitted = {"dual_ma": {"fast_period", "slow_period"}, "rsi_reversal": {"window", "buy_threshold", "sell_threshold"},
                     "momentum": {"window", "threshold"}, "bollinger_bands": {"window", "std_dev"}}[self.name]
        if self.parameters.keys() - permitted:
            raise ValueError(f"{self.name} 不支持参数 {sorted(self.parameters.keys() - permitted)}")
        for key, value in self.parameters.items():
            if abs(value) > 500:
                raise ValueError("策略参数超出允许范围")
            if key in {"fast_period", "slow_period", "window"} and (value < 2 or int(value) != value):
                raise ValueError("指标周期必须为 2 到 500 的整数")
        if self.name == "dual_ma" and self.parameters.get("fast_period", 5) >= self.parameters.get("slow_period", 20):
            raise ValueError("快均线周期必须小于慢均线周期")
        if self.name == "rsi_reversal" and not (0 < self.parameters.get("buy_threshold", 30) < self.parameters.get("sell_threshold", 70) < 100):
            raise ValueError("RSI 阈值必须满足 0 < oversold < overbought < 100")
        if self.name == "momentum" and not 0 <= self.parameters.get("threshold", .02) < 1:
            raise ValueError("动量阈值应使用 [0,1) 小数收益率")
        if self.name == "bollinger_bands" and not 0 < self.parameters.get("std_dev", 2) <= 10:
            raise ValueError("布林带标准差倍数应在 (0,10] 内")
        return self


class AccountConfig(StrictModel):
    initial_cash: float = Field(default=1000000, ge=1000, le=1e10)
    commission_rate: float = Field(default=.0003, ge=0, le=.1)
    tax_rate: float = Field(default=.0005, ge=0, le=.1)
    min_commission: float = Field(default=5, ge=0, le=10000)
    slippage_bps: float = Field(default=5, ge=0, le=1000)
    position_size: float = Field(default=.3, gt=0, le=1)


class RunConfig(StrictModel):
    name: str = Field(default="双均线 · 基线研究", min_length=1, max_length=100)
    tickers: list[str] = Field(default_factory=lambda: ["000858", "601318", "600036"], min_length=1, max_length=10)
    start_date: date = date(2024, 1, 1)
    end_date: date = date(2025, 12, 31)
    source: Literal["demo", "akshare"] = "demo"
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    account: AccountConfig = Field(default_factory=AccountConfig)

    @field_validator("tickers")
    @classmethod
    def valid_tickers(cls, values):
        values = [value.lower().removeprefix("sh").removeprefix("sz") for value in values]
        if any(not re.fullmatch(r"\d{6}", value) for value in values):
            raise ValueError("股票代码必须为六位数字")
        if len(set(values)) != len(values):
            raise ValueError("股票池不能包含重复代码")
        return values

    @model_validator(mode="after")
    def valid_dates(self):
        if self.start_date > self.end_date:
            raise ValueError("开始日期不能晚于结束日期")
        if self.start_date < date(2000, 1, 1) or (self.end_date - self.start_date).days > 3653:
            raise ValueError("单次研究最多十年，开始日期不能早于 2000 年")
        if self.source == "demo" and not (date(2019, 1, 1) <= self.start_date <= self.end_date <= date(2026, 9, 18)):
            raise ValueError("演示数据范围为 2019-01-01 至 2026-09-18")
        if self.source == "akshare" and self.end_date > date.today():
            raise ValueError("真实行情的结束日期不能晚于今天")
        return self


class BranchRequest(StrictModel):
    name: str | None = Field(default=None, max_length=100)
    fork_date: date
    strategy: StrategyConfig | None = None
    account: dict[str, float] | None = None
    history: list[dict] | None = Field(default=None, max_length=20)

    @field_validator("account")
    @classmethod
    def account_change(cls, value):
        if value is not None:
            if value.keys() - {"position_size"}:
                raise ValueError("分叉仅允许改变仓位比例；费用变化请使用压力实验")
            if "position_size" in value and not 0 < value["position_size"] <= 1:
                raise ValueError("仓位比例必须大于 0 且不超过 1")
        return value


class ExperimentRequest(StrictModel):
    kind: Literal["pressure", "parameter", "walk_forward"]
    parameter: str | None = None
    values: list[float] | None = Field(default=None, min_length=2, max_length=12)
    training_days: int = Field(default=120, ge=30, le=1000)
    test_days: int = Field(default=40, ge=10, le=250)


class SessionRequest(StrictModel):
    cursor: int = Field(default=0, ge=0)


class AdvanceRequest(StrictModel):
    steps: int = Field(default=1, ge=1, le=60)


class NoteRequest(StrictModel):
    run_id: str | None = None
    title: str = Field(default="研究笔记", min_length=1, max_length=200)
    body: str = Field(default="", max_length=20000)


class AssistantRequest(StrictModel):
    prompt: str = Field(min_length=1, max_length=4000)
    base_config: dict | None = None
