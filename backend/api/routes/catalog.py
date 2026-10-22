"""Catalog and data availability."""
from typing import Annotated
from fastapi import APIRouter, Depends
from backend.api.dependencies import data_center
from backend.api.schemas import RunConfig
from backend.core.data_center import DataCenter, UNIVERSE
from backend.version import VERSION
from backend.core.strategy_catalog import strategy_catalog

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/health")
def health():
    return {"status": "ok", "version": VERSION, "engine": "event-driven", "storage": "sqlite", "worker": "process"}


@router.get("/catalog")
def catalog(center: Annotated[DataCenter, Depends(data_center)]):
    return {"tickers": UNIVERSE, "strategies": strategy_catalog(), "sources": center.status()["sources"], "defaults": RunConfig().model_dump(mode="json"),
            "capabilities": ["portfolio", "branch", "blind_replay", "pressure", "parameter", "walk_forward",
                             "evidence_export", "evidence_replay", "notes", "local_research_commands"]}


@router.get("/data/status")
def data_status(center: Annotated[DataCenter, Depends(data_center)]):
    return center.status()
