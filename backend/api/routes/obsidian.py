"""Generic optional Obsidian module: preview/export, then explicit publish."""
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from backend.integrations.obsidian import ObsidianService

router = APIRouter(prefix="/api/obsidian", tags=["obsidian"])


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    vault_path: str = Field(default="", max_length=1000)
    folder: str = Field(default="QuantSandbox", max_length=300)


class NoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["research", "simulation"]
    run_id: str = Field(min_length=1, max_length=80)
    title: str = Field(default="", max_length=160)
    notes: str = Field(default="", max_length=20000)
    preview_token: str = Field(default="", max_length=100)


def service(request: Request):
    return ObsidianService(request.app.state.store.root,
                           simulation_get=lambda identifier: request.app.state.research.require_run(identifier, completed=True))


@router.get("/config")
def config(request: Request):
    return service(request).config()


@router.put("/config")
def save_config(value: Settings, request: Request):
    return service(request).save_config(value.model_dump())


@router.post("/preview")
def preview(value: NoteRequest, request: Request):
    return service(request).preview(value.model_dump())


@router.post("/export")
def export(value: NoteRequest, request: Request):
    content = service(request).export(value.model_dump())
    filename = f"quantsandbox-obsidian-{value.kind}-{value.run_id[:12]}.zip"
    return Response(content, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/publish")
def publish(value: NoteRequest, request: Request):
    return service(request).publish(value.model_dump())
