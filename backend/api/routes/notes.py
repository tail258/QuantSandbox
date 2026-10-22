"""HTTP endpoints; business decisions live in the application services."""
from typing import Annotated
from fastapi import APIRouter, Depends
from backend.api.schemas import NoteRequest
from backend.api.dependencies import note_service
from backend.services.notes import NoteService

router = APIRouter(prefix="/api", tags=["notes"])
Service = Annotated[NoteService, Depends(note_service)]


@router.get("/notes")
def list_notes(run_id: str | None = None, *, service: Service):
    return service.list_notes(run_id)


@router.post("/notes", status_code=201)
def create_note(note: NoteRequest, *, service: Service):
    return service.create_note(note)


@router.put("/notes/{identifier}")
def update_note(identifier: str, note: NoteRequest, *, service: Service):
    return service.update_note(identifier, note)


@router.patch("/runs/{identifier}/notes")
def run_note(identifier: str, note: NoteRequest, *, service: Service):
    return service.run_note(identifier, note)


@router.delete("/notes/{identifier}")
def delete_note(identifier: str, *, service: Service):
    return service.delete_note(identifier)
