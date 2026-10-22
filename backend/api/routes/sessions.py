"""HTTP endpoints; business decisions live in the application services."""
from typing import Annotated
from fastapi import APIRouter, Depends
from backend.api.schemas import AdvanceRequest, SessionRequest
from backend.api.responses import ReplaySession
from backend.api.dependencies import session_service
from backend.services.sessions import SessionService

router = APIRouter(prefix="/api", tags=["sessions"])
Service = Annotated[SessionService, Depends(session_service)]


@router.post("/runs/{identifier}/sessions", response_model=ReplaySession)
def create_session(identifier: str, request: SessionRequest, *, service: Service):
    return service.create_session(identifier, request)


@router.get("/sessions/{identifier}", response_model=ReplaySession)
def get_session(identifier: str, *, service: Service):
    return service.get_session(identifier)


@router.post("/sessions/{identifier}/advance", response_model=ReplaySession)
def advance_session(identifier: str, request: AdvanceRequest, *, service: Service):
    return service.advance_session(identifier, request)


@router.post("/sessions/{identifier}/reveal", response_model=ReplaySession)
def reveal_session(identifier: str, *, service: Service):
    return service.reveal_session(identifier)
