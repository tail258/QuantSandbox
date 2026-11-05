"""US research facade; all calculations are shared with the CLI."""
from fastapi import APIRouter, Request
from pydantic import Field
from backend.api.schemas import StrictModel
from backend.workbench import store, us_equities

router = APIRouter(prefix='/api/research/us', tags=['US company research'])


class PriceImport(StrictModel):
    text: str = Field(max_length=8_000_000)
    source_url: str = Field(min_length=1, max_length=2000)


class SaveResearch(StrictModel):
    project_id: str | None = None
    snapshot_ids: list[str] = Field(min_length=1, max_length=2)


@router.get('/catalog')
def catalog():
    return us_equities.catalog()


@router.get('/company/{symbol}')
def company(symbol: str):
    return us_equities.dashboard(symbol)


@router.post('/company/{symbol}/refresh')
def refresh(symbol: str):
    return us_equities.refresh(symbol)


@router.post('/company/{symbol}/prices')
def prices(symbol: str, body: PriceImport):
    us_equities.import_prices(symbol, body.text, body.source_url)
    return us_equities.dashboard(symbol)


@router.post('/company/{symbol}/save', status_code=201)
def save(symbol: str, body: SaveResearch, request: Request):
    if body.project_id:
        request.app.state.projects.require(body.project_id)
    result = us_equities.dashboard_from_snapshots(symbol, body.snapshot_ids)
    snapshots = store.get_snapshots(body.snapshot_ids)
    record = store.save_run({'kind': 'us_equity', 'title': result['instrument']['symbol'] + ' · US company research',
        'params': {'symbol': result['instrument']['symbol'], 'market': 'US', 'currency': 'USD', 'basis': 'annual_current_revision', 'project_id': body.project_id},
        'inputs': body.snapshot_ids, 'result': result,
        'sources': [{k: s.get(k) for k in ('id', 'source', 'source_url', 'fetched_at', 'method', 'unit')} for s in snapshots]})
    if body.project_id:
        request.app.state.projects.link(body.project_id, 'research', record['id'])
    return record
