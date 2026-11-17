"""Project-scoped daily Chan analysis, offline demo and raw evidence replay."""
from fastapi import APIRouter, Request
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from backend.api.schemas import StrictModel
from backend.services import chan_research
from backend.services.errors import ResearchError

router = APIRouter(prefix='/api', tags=['daily Chan research'])


class SnapshotRequest(StrictModel):
    snapshot_id: str = Field(pattern=r'^[0-9a-f]{20}$')


@router.get('/projects/{project_id}/chan/snapshots')
def list_snapshots(project_id: str, request: Request):
    project = request.app.state.projects.require(project_id)
    return {'snapshots': chan_research.list_snapshots(project)}


@router.post('/projects/{project_id}/chan/analyze')
def analyze(project_id: str, body: SnapshotRequest, request: Request):
    project = request.app.state.projects.require(project_id)
    return chan_research.analyze_project(project, body.snapshot_id)


@router.post('/chan/demo')
def demo():
    return chan_research.demo()


@router.post('/chan/replay', openapi_extra={'requestBody': {'required': True, 'content': {
    'application/json': {'schema': {'type': 'object', 'description': 'Original Chan evidence JSON file'}},
}}})
async def replay(request: Request):
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > chan_research.MAX_EVIDENCE_BYTES:
            raise ResearchError(413, f'Chan evidence must not exceed {chan_research.MAX_EVIDENCE_BYTES} bytes')
        body.extend(chunk)
    return await run_in_threadpool(chan_research.replay, bytes(body))
