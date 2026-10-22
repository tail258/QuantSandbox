"""Application-scoped dependencies shared by every route group."""
from fastapi import Request
from backend.core.data_center import DataCenter
from backend.services.research import ResearchService
from backend.services.sessions import SessionService
from backend.services.evidence import EvidenceService
from backend.services.notes import NoteService


def research_service(request: Request) -> ResearchService:
    return request.app.state.research


def session_service(request: Request) -> SessionService:
    return request.app.state.sessions


def evidence_service(request: Request) -> EvidenceService:
    return request.app.state.evidence


def note_service(request: Request) -> NoteService:
    return request.app.state.notes


def data_center(request: Request) -> DataCenter:
    return request.app.state.center
