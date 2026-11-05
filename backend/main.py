"""QuantSandbox application composition. Start with uvicorn backend.main:app."""
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from backend.api.routes import assistant, catalog, evidence, notes, runs, sessions
from backend.core.data_center import DataCenter, DataUnavailable, data_root
from backend.services.errors import ResearchError
from backend.services.evidence import EvidenceService
from backend.services.notes import NoteService
from backend.services.research import ResearchService
from backend.services.runner import JobRunner
from backend.services.sessions import SessionService
from backend.services.store import Store
from backend.services.projects import ProjectStore
from backend.api.routes import projects
from backend.workbench import store as workbench_store
from backend.workbench.app import router as workbench_router
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
        application.state.projects = ProjectStore(selected_root)
        if runner:
            runner.start()
        try:
            yield
        finally:
            if runner:
                runner.close()

    application = FastAPI(title="QuantSandbox Research API", version=VERSION, lifespan=lifespan)
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                       "http://localhost:4173", "http://127.0.0.1:4173",
                       "http://localhost:8766", "http://127.0.0.1:8766"],
        allow_credentials=False,
        allow_origin_regex=r'http://(?:localhost|127\.0\.0\.1)(?::\d+)?',
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @application.middleware('http')
    async def local_scope(request, call_next):
        origin = request.headers.get('origin', '')
        try:
            parsed = urlsplit(origin)
            local_origin = (parsed.scheme == 'http' and parsed.hostname in {'localhost', '127.0.0.1'}
                            and parsed.username is None and parsed.password is None
                            and not parsed.path and not parsed.query and not parsed.fragment)
            if origin:
                parsed.port  # Validate the origin's port before accepting it.
        except ValueError:
            local_origin = False
        if (origin and not local_origin) or request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse(status_code=403, content={'detail': '仅允许本地工作台来源'})
        token = workbench_store._scope_data.set(selected_root / 'workbench' if root is not None else workbench_store.DATA)
        try:
            return await call_next(request)
        finally:
            workbench_store._scope_data.reset(token)

    @application.exception_handler(ValueError)
    async def value_error(request, exception):
        return JSONResponse(status_code=400, content={'detail': str(exception)})

    @application.exception_handler(KeyError)
    async def missing_key(request, exception):
        return JSONResponse(status_code=400, content={'detail': f'缺少必要字段：{exception}'})

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

    for routes in (catalog, runs, sessions, evidence, notes, assistant, projects):
        application.include_router(routes.router)
    application.include_router(workbench_router)
    from backend.api.routes import us_equities
    application.include_router(us_equities.router)
    from backend.api.routes import obsidian
    application.include_router(obsidian.router)
    dist = Path(__file__).resolve().parents[1] / 'frontend' / 'dist'
    if dist.exists():
        application.mount('/', StaticFiles(directory=dist, html=True), name='ui')
    return application


app = create_app()
