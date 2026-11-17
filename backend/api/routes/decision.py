"""Point-in-time, project-scoped stock/ETF decision overview."""
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from backend.services import stock_decision

router = APIRouter(prefix='/api/decision', tags=['stock decision overview'])
ProjectId = Annotated[str | None, Query(pattern=r'^[0-9a-f]{32}$')]
SnapshotId = Annotated[str | None, Query(pattern=r'^[0-9a-f]{20}$')]
RequiredSnapshot = Annotated[str, Query(pattern=r'^[0-9a-f]{20}$')]
HoldingSessions = Annotated[int, Query(ge=1, le=20)]


class FactorSelection(BaseModel):
    selected: list[str] = Field(max_length=5)


def _project(request, project_id):
    return request.app.state.projects.require(project_id) if project_id else None


@router.get('/{symbol}')
def read(symbol: str, request: Request, project_id: ProjectId = None,
         snapshot_id: SnapshotId = None, as_of: date | None = None):
    return stock_decision.get_analysis(symbol, _project(request, project_id), snapshot_id=snapshot_id,
                                       cutoff=as_of.isoformat() if as_of else None)


@router.post('/{symbol}/refresh')
def refresh(symbol: str, request: Request, project_id: ProjectId = None):
    return stock_decision.refresh_analysis(symbol, _project(request, project_id))


@router.get('/{symbol}/evaluation')
def evaluation(symbol: str, request: Request, snapshot_id: RequiredSnapshot,
               project_id: ProjectId = None, as_of: date | None = None, holding_sessions: HoldingSessions = 5):
    return stock_decision.evaluation(symbol, _project(request, project_id), snapshot_id,
                                     cutoff=as_of.isoformat() if as_of else None, holding_sessions=holding_sessions)


@router.get('/{symbol}/factors')
def factors(symbol: str, request: Request, project_id: ProjectId = None):
    return stock_decision.factor_selection(symbol, _project(request, project_id))


@router.put('/{symbol}/factors')
def save_factors(symbol: str, payload: FactorSelection, request: Request, project_id: ProjectId = None):
    return stock_decision.factor_selection(symbol, _project(request, project_id), payload.selected)
