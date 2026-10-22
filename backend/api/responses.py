"""Lossless public response contracts, independent of request normalization.

Nested audit records stay dictionaries so new engine fields and exact numeric
values survive response validation and evidence export unchanged.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ResponseModel(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)


class ReplayResult(ResponseModel):
    metrics: dict[str, Any]
    series: list[dict[str, Any]]
    bars: dict[str, list[dict[str, Any]]]
    trades: list[dict[str, Any]]
    decisions: list[dict[str, Any]]
    checkpoints: list[dict[str, Any]]


class ProvenancedResult(ResponseModel):
    engine: dict[str, Any]
    data_provenance: dict[str, Any]


class BacktestResult(ReplayResult, ProvenancedResult):
    engine_version: str
    config: dict[str, Any]
    assumptions: list[str]


class PressureScenario(ResponseModel):
    id: str
    name: str
    description: str
    changes: dict[str, Any]
    metrics: dict[str, Any]
    delta_return: float
    series: list[dict[str, Any]]


class PressureResult(ProvenancedResult):
    kind: Literal["stress"]
    baseline: dict[str, Any]
    scenarios: list[PressureScenario]
    assumptions: list[str]
    interpretation: str


class ParameterVariant(ResponseModel):
    value: int | float
    metrics: dict[str, Any]


class ParameterResult(ProvenancedResult):
    parameter: str
    baseline: dict[str, Any]
    variants: list[ParameterVariant]
    best_value: int | float
    notice: str


class WalkForwardFold(ResponseModel):
    fold: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    selected_strategy: dict[str, Any]
    training_metrics: dict[str, Any]
    test_metrics: dict[str, Any]
    trials: list[dict[str, Any]]


class WalkForwardResult(ProvenancedResult):
    kind: Literal["walk_forward"]
    folds: list[WalkForwardFold]
    metrics: dict[str, Any]
    series: list[dict[str, Any]]
    trades: list[dict[str, Any]]
    config: dict[str, Any]
    training_days: int
    test_days: int
    selection_objective: str
    assumptions: list[str]


class RunMetadata(ResponseModel):
    id: str
    name: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    progress: int
    created_at: str
    updated_at: str
    config: dict[str, Any]
    kind: Literal["backtest", "branch", "pressure", "parameter", "walk_forward"]
    parent_id: str | None
    branch: dict[str, Any] | None
    manifest: list[dict[str, Any]]
    error: dict[str, Any] | None
    synthetic: bool


class RunBase(RunMetadata):
    """Detail responses do not contain the summary-only metrics field."""


class BacktestRun(RunBase):
    kind: Literal["backtest"]
    result: BacktestResult | None


class BranchRun(RunBase):
    kind: Literal["branch"]
    result: BacktestResult | None


class PressureRun(RunBase):
    kind: Literal["pressure"]
    result: PressureResult | None


class ParameterRun(RunBase):
    kind: Literal["parameter"]
    result: ParameterResult | None


class WalkForwardRun(RunBase):
    kind: Literal["walk_forward"]
    result: WalkForwardResult | None


Run = Annotated[BacktestRun | BranchRun | PressureRun | ParameterRun | WalkForwardRun,
                Field(discriminator="kind")]


class RunSummary(RunMetadata):
    metrics: dict[str, Any] | None


class RunList(ResponseModel):
    runs: list[RunSummary]


class ReplaySession(ResponseModel):
    id: str
    run_id: str
    cursor: int
    date: str
    total_steps: int
    revealed: bool
    revealed_at: str | None
    source: str
    synthetic: bool
    result: ReplayResult
