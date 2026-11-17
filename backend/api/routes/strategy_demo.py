"""Isolated synthetic walkthrough endpoints; no workspace dependencies."""
from fastapi import APIRouter
from pydantic import Field, model_validator

from backend.api.schemas import StrictModel
from backend.services.strategy_demo import (
    DEFAULT_FAST_PERIOD,
    DEFAULT_SLOW_PERIOD,
    MAX_EVIDENCE_LENGTH,
    MAX_PERIOD,
    replay_demo,
    run_demo,
)

router = APIRouter(prefix="/api/demo/strategy", tags=["offline strategy demo"])


class DemoParameters(StrictModel):
    fast_period: int = Field(default=DEFAULT_FAST_PERIOD, ge=2, lt=MAX_PERIOD, strict=True)
    slow_period: int = Field(default=DEFAULT_SLOW_PERIOD, ge=3, le=MAX_PERIOD, strict=True)

    @model_validator(mode="after")
    def ordered_periods(self):
        if self.fast_period >= self.slow_period:
            raise ValueError("Fast period must be smaller than slow period")
        return self


class DemoEvidence(StrictModel):
    evidence: str = Field(min_length=1, max_length=MAX_EVIDENCE_LENGTH)


@router.post("/run")
def run(parameters: DemoParameters):
    return run_demo(parameters.fast_period, parameters.slow_period)


@router.post("/replay")
def replay(request: DemoEvidence):
    return replay_demo(request.evidence)
