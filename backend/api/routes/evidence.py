"""HTTP endpoints; business decisions live in the application services."""
from typing import Annotated
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from backend.api.responses import Run
from backend.api.dependencies import evidence_service
from backend.services.evidence import EvidenceService

router = APIRouter(prefix="/api", tags=["evidence"])
Service = Annotated[EvidenceService, Depends(evidence_service)]


@router.get("/runs/{identifier}/export")
def export_run(identifier: str, *, service: Service):
    package = service.export_run(identifier)
    return JSONResponse(package, headers={"Content-Disposition": f'attachment; filename="quantsandbox-{identifier[:8]}.json"'})


@router.post("/import", status_code=202, response_model=Run)
def import_run(package: dict, *, service: Service):
    return service.import_run(package)
