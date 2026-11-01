"""Cross-module projects and fixed research-price snapshot bridge."""
import hashlib
import re
from typing import Literal

import pandas as pd
from fastapi import APIRouter, Request
from pydantic import Field

from backend.api.schemas import RunConfig, StrictModel
from backend.core.data_format import DataUnavailable, canonical_json, validate_frame
from backend.services.errors import ResearchError
from backend.workbench import store

router = APIRouter(prefix='/api', tags=['projects and data bridge'])


class ProjectRequest(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    question: str = Field(default='', max_length=20000)
    symbols: list[str] = Field(default_factory=list, max_length=40)


class LinkRequest(StrictModel):
    kind: Literal['research', 'simulation']
    run_id: str = Field(min_length=1, max_length=64)


class BridgeRequest(StrictModel):
    snapshot_ids: list[str] = Field(min_length=1, max_length=10)
    config: RunConfig
    project_id: str | None = None


@router.get('/projects')
def projects(request: Request):
    return request.app.state.projects.list()


@router.post('/projects', status_code=201)
def create_project(body: ProjectRequest, request: Request):
    return request.app.state.projects.create(body.name, body.question, body.symbols)


@router.get('/projects/{identifier}')
def get_project(identifier: str, request: Request):
    return request.app.state.projects.require(identifier)


@router.post('/projects/{identifier}/links')
def link_record(identifier: str, body: LinkRequest, request: Request):
    if body.kind == 'research':
        try:
            store.get_run(body.run_id)
        except ValueError as exc:
            raise ResearchError(404, str(exc)) from exc
    else:
        request.app.state.research.require_run(body.run_id)
    return request.app.state.projects.link(identifier, body.kind, body.run_id)


@router.post('/bridge/backtests', status_code=202)
def bridge_backtest(body: BridgeRequest, request: Request):
    """Only immutable raw OHLCV inputs cross this boundary; never re-download."""
    if body.config.source != 'snapshot':
        raise ResearchError(422, '桥接来源必须选择 snapshot')
    if len(set(body.snapshot_ids)) != len(body.snapshot_ids):
        raise ResearchError(422, '数据快照不能重复')
    if body.project_id:
        request.app.state.projects.require(body.project_id)
    checked = []
    for sid in body.snapshot_ids:
        if not re.fullmatch(r'[a-f0-9]{20}', sid):
            raise ResearchError(422, '研究快照编号无效')
        try:
            snapshot = store.get_snapshot(sid)
        except ValueError as exc:
            raise ResearchError(404, str(exc)) from exc
        spec = snapshot.get('request', {})
        if snapshot.get('kind') != 'quotes' or spec.get('adjust') != '3':
            raise ResearchError(422, '回测只接收明确标注为不复权的股票 OHLCV 快照')
        if '成交量统一为股' not in snapshot.get('method', ''):
            raise ResearchError(422, '快照缺少成交量为股的明确口径')
        ticker = snapshot.get('symbol')
        if ticker not in body.config.tickers or any(ticker == item[0] for item in checked):
            raise ResearchError(422, '快照证券与股票池不一致或重复')
        start, end = body.config.start_date.isoformat(), body.config.end_date.isoformat()
        if spec.get('start', '9999') > start or spec.get('end', '') < end:
            raise ResearchError(422, '原始快照请求范围未覆盖研究区间，请先明确补充行情')
        rows = snapshot.get('rows', [])
        if len({r.get('date') for r in rows}) != len(rows):
            raise ResearchError(422, '快照包含重复日期，请先核对来源')
        try:
            frame = validate_frame(pd.DataFrame(rows))
            frame = validate_frame(frame.loc[frame.date <= pd.Timestamp(end)])
        except (ValueError, TypeError, DataUnavailable) as exc:
            raise ResearchError(422, f'快照行情无效：{exc}') from exc
        if frame.loc[frame.date.between(start, end)].empty:
            raise ResearchError(422, '研究区间内没有可用行情')
        origin = {'module': 'research', 'snapshot_id': sid,
                  'snapshot_sha256': hashlib.sha256(store.encode(snapshot).encode()).hexdigest(),
                  'source': snapshot.get('source'), 'source_url': snapshot.get('source_url'),
                  'fetched_at': snapshot.get('fetched_at'), 'request': spec,
                  'method': snapshot.get('method'), 'price_basis': 'raw_unadjusted', 'volume_unit': 'shares',
                  'transformation': '保留原始 OHLCV；仅截断研究结束日之后的行；前置历史用于指标预热'}
        checked.append((ticker, frame, origin))
    if {item[0] for item in checked} != set(body.config.tickers):
        raise ResearchError(422, '每只证券须提供一个固定原始快照')
    manifests = [request.app.state.center.snapshot(ticker, frame, 'snapshot', origin=origin)
                 for ticker, frame, origin in checked]
    run = request.app.state.research.schedule(body.config.model_dump(mode='json'), manifest=manifests)
    if body.project_id:
        request.app.state.projects.link(body.project_id, 'simulation', run['id'])
    return run
