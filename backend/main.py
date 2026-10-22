"""QuantSandbox application composition. Start with uvicorn backend.main:app."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.routes import assistant, catalog, evidence, notes, runs, sessions
from backend.core.data_center import DataCenter, DataUnavailable, data_root
from backend.services.errors import ResearchError
from backend.services.evidence import EvidenceService
from backend.services.notes import NoteService
from backend.services.research import ResearchService
from backend.services.runner import JobRunner
from backend.services.sessions import SessionService
from backend.services.store import Store
from backend.version import VERSION


def create_app(root: str | Path | None = None, *, run_jobs: bool = True) -> FastAPI:
    selected_root = Path(root) if root else data_root()

    @asynccontextmanager
    async def lifespan(application):
        store = Store(selected_root)
        center = DataCenter(root=selected_root)
        runner = JobRunner(store) if run_jobs else None
        research = ResearchService(store, runner)
        application.state.store = store
        application.state.center = center
        application.state.runner = runner
        application.state.research = research
        application.state.sessions = SessionService(research)
        application.state.evidence = EvidenceService(research, center)
        application.state.notes = NoteService(research)
        if runner:
            runner.start()
        try:
            yield
        finally:
            if runner:
                runner.close()

    application = FastAPI(title="QuantSandbox Research API", version=VERSION, lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                       "http://localhost:4173", "http://127.0.0.1:4173"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @application.exception_handler(ResearchError)
    async def research_error(request, exception):
        return JSONResponse(status_code=exception.status_code, content={"detail": exception.detail})

    @application.exception_handler(DataUnavailable)
    async def unavailable_handler(request, exception):
        return JSONResponse(status_code=503, content={"detail": str(exception), "code": "data_unavailable"})

    @application.exception_handler(RequestValidationError)
    async def validation_handler(request, exception):
        # Invalid input can contain NaN/Infinity: do not echo it into strict JSON.
        errors = [{"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
                  for error in exception.errors()]
        return JSONResponse(status_code=422, content={"detail": errors, "code": "invalid_request"})

    for routes in (catalog, runs, sessions, evidence, notes, assistant):
        application.include_router(routes.router)
    return application


app = create_app()
