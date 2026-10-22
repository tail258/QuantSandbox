"""HTTP endpoints; business decisions live in the application services."""
from typing import Annotated
from fastapi import APIRouter, Depends, Query
from backend.api.schemas import BranchRequest, ExperimentRequest, RunConfig
from backend.api.responses import Run, RunList
from backend.api.dependencies import research_service
from backend.services.research import ResearchService

router = APIRouter(prefix="/api", tags=["runs"])
Service = Annotated[ResearchService, Depends(research_service)]


@router.post("/runs", status_code=202, response_model=Run)
def create_run(config: RunConfig, *, service: Service):
    return service.create_run(config)


@router.get("/runs", response_model=RunList)
def list_runs(limit: int = Query(default=100, ge=1, le=200), *, service: Service):
    return service.list_runs(limit)


@router.get("/runs/{identifier}", response_model=Run)
def get_run(identifier: str, *, service: Service):
    return service.get_run(identifier)


@router.post("/runs/{identifier}/cancel", response_model=Run)
def cancel_run(identifier: str, *, service: Service):
    return service.cancel_run(identifier)


@router.post("/runs/{identifier}/branch", status_code=202, response_model=Run)
def create_branch(identifier: str, request: BranchRequest, *, service: Service):
    return service.create_branch(identifier, request)


@router.post("/runs/{identifier}/experiments", status_code=202, response_model=Run)
def create_experiment(identifier: str, request: ExperimentRequest, *, service: Service):
    return service.create_experiment(identifier, request)
