"""Cross-module projects and fixed research-price snapshot bridge."""
import hashlib
import re
from datetime import date
from threading import Lock
from typing import Literal

import pandas as pd
from fastapi import APIRouter, Query, Request
from pydantic import Field

from backend.api.schemas import RunConfig, StrictModel
from backend.core.data_format import DataUnavailable, canonical_json, validate_frame
from backend.core.engine import ENGINE_VERSION
from backend.core.strategy_catalog import warmup_requirements
from backend.services.errors import ResearchError
from backend.services.daily_paper import advance_paper, list_paper, paper_lock, start_paper
from backend.workbench import store
from backend.workbench.execution_history import calendar_span

router = APIRouter(prefix='/api', tags=['projects and data bridge'])
plan_submission_lock = Lock()


class ProjectRequest(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    question: str = Field(default='', max_length=20000)
    symbols: list[str] = Field(default_factory=list, max_length=40)


class LinkRequest(StrictModel):
    kind: Literal['research', 'simulation']
    run_id: str = Field(min_length=1, max_length=64)


class ProjectPatch(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    question: str | None = Field(default=None, max_length=20000)
    symbols: list[str] | None = Field(default=None, max_length=40)
    conclusion: str | None = Field(default=None, max_length=20000)
    expected_updated_at: str | None = Field(default=None, max_length=48)


class BridgeRequest(StrictModel):
    snapshot_ids: list[str] = Field(min_length=1, max_length=10)
    config: RunConfig
    project_id: str | None = None
    plan_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')


class PaperObservation(StrictModel):
    snapshot_id: str = Field(pattern=r'^[a-f0-9]{20}$')
    as_of: date


@router.get('/projects')
def projects(request: Request):
    return request.app.state.projects.list()


@router.post('/projects', status_code=201)
def create_project(body: ProjectRequest, request: Request):
    return request.app.state.projects.create(body.name, body.question, body.symbols)


@router.get('/projects/{identifier}')
def get_project(identifier: str, request: Request):
    return request.app.state.projects.require(identifier)


@router.get('/projects/{identifier}/strategy-runs')
def project_strategy_runs(identifier: str, request: Request, limit: int = Query(25, ge=1, le=50)):
    project = request.app.state.projects.require(identifier)
    ids = [link['run_id'] for link in project['links'] if link['kind'] == 'simulation']
    return {'runs': request.app.state.store.list_runs(limit, run_ids=ids)}


@router.patch('/projects/{identifier}')
def update_project(identifier: str, body: ProjectPatch, request: Request):
    changes = body.model_dump(exclude_unset=True, exclude={'expected_updated_at'})
    return request.app.state.projects.update(identifier, changes, expected_updated_at=body.expected_updated_at)


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


@router.get('/projects/{identifier}/daily-paper')
def paper_history(identifier: str, request: Request):
    request.app.state.projects.require(identifier)
    return {'records': list_paper(request.app.state.store.root, identifier)}


@router.post('/projects/{identifier}/daily-paper', status_code=201)
def paper_start(identifier: str, body: PaperObservation, request: Request):
    project = request.app.state.projects.require(identifier)
    with paper_lock:
        return start_paper(request.app.state.store.root, project, store.get_snapshot(body.snapshot_id), body.as_of)


@router.post('/projects/{identifier}/daily-paper/{account_id}/advance')
def paper_advance(identifier: str, account_id: str, body: PaperObservation, request: Request):
    project = request.app.state.projects.require(identifier)
    with paper_lock:
        return advance_paper(request.app.state.store.root, project, account_id, store.get_snapshot(body.snapshot_id),
                             body.as_of, store.get_snapshot)


def prepare_bridge(body: BridgeRequest, request: Request, *, require_project: bool):
    """Validate a frozen input once, using the same rules for plan and submission."""
    if body.config.source != 'snapshot':
        raise ResearchError(422, '桥接来源必须选择 snapshot')
    if len(set(body.snapshot_ids)) != len(body.snapshot_ids):
        raise ResearchError(422, '数据快照不能重复')
    if require_project and not body.project_id:
        raise ResearchError(422, '回测计划必须指定研究项目')
    if body.project_id:
        project = request.app.state.projects.require(body.project_id)
        if require_project and not set(body.config.tickers) <= set(project['symbols']):
            raise ResearchError(422, '回测证券不在指定项目中，请先核对项目与证券')
    checked = []
    for sid in body.snapshot_ids:
        if not re.fullmatch(r'[a-f0-9]{20}', sid):
            raise ResearchError(422, '研究快照编号无效')
        try:
            snapshot = store.get_snapshot(sid)
        except ValueError as exc:
            raise ResearchError(404, str(exc)) from exc
        original = {key: value for key, value in snapshot.items() if key != 'id'}
        if require_project and (snapshot.get('id') != sid or
                                not hashlib.sha256(store.encode(original).encode()).hexdigest().startswith(sid)):
            raise ResearchError(409, '快照未通过内容完整性校验')
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
        if 'execution_history' in snapshot:
            origin['execution_history'] = snapshot['execution_history']
        checked.append((ticker, frame, origin))
    if {item[0] for item in checked} != set(body.config.tickers):
        raise ResearchError(422, '每只证券须提供一个固定原始快照')
    return sorted(checked, key=lambda item: item[0]) if require_project else checked


def bridge_plan(body: BridgeRequest, checked) -> dict:
    config = body.config.model_dump(mode='json')
    start, end = config['start_date'], config['end_date']
    inputs, warnings = [], []
    history_target, volume_target = warmup_requirements(body.config.strategy.name, body.config.strategy.parameters)
    for ticker, frame, origin in checked:
        preceding = frame.loc[frame.date < start]
        period = frame.loc[frame.date >= start]
        dates = set(period.date.dt.strftime('%Y-%m-%d'))
        calendar = (origin.get('execution_history') or {}).get('calendar') or {}
        span = calendar_span(calendar)
        missing = None
        if span is not None and span[0] <= start <= end <= span[1]:
            sessions = {day for day in calendar['sessions'] if start <= day <= end}
            if dates <= sessions:
                missing = sorted(sessions - dates)
        first, last = min(dates), max(dates)
        volume_rows = None
        if volume_target is not None:
            valid_volume = preceding.volume.gt(0)
            if 'is_suspended' in preceding:
                valid_volume &= ~preceding.is_suspended.eq(True).fillna(False)
            volume_rows = int(valid_volume.sum())
        if len(preceding) < history_target or (volume_target is not None and volume_rows < volume_target):
            warnings.append({'ticker': ticker, 'code': 'short_warmup'})
        if first > start or last < end:
            warnings.append({'ticker': ticker, 'code': 'observations_do_not_reach_requested_bounds'})
        if missing is None or missing:
            warnings.append({'ticker': ticker, 'code': 'calendar_unknown' if missing is None else 'missing_sessions'})
        inputs.append({'ticker': ticker, **{k: v for k, v in origin.items() if k != 'execution_history'},
                       'first_observed_date': first, 'last_observed_date': last, 'observations': len(period),
                       'warmup_rows': len(preceding), 'warmup_positive_volume_rows': volume_rows,
                       'recommended_warmup_rows': history_target,
                       'calendar_start_date': span[0] if span else None, 'calendar_end_date': span[1] if span else None,
                       'calendar_has_sessions': missing is not None, 'missing_session_count': len(missing) if missing is not None else None,
                       'sample_missing_sessions': missing[:20] if missing is not None else None})
    key = {'kind': 'fixed-backtest-v1', 'engine_version': ENGINE_VERSION, 'project_id': body.project_id, 'config': config,
           'snapshots': [[row['snapshot_id'], row['snapshot_sha256']] for row in inputs]}
    return {'plan_id': hashlib.sha256(canonical_json(key).encode()).hexdigest(),
            'project_id': body.project_id, 'config': config, 'inputs': inputs, 'warnings': warnings}


@router.post('/bridge/backtests/preview')
def preview_backtest(body: BridgeRequest, request: Request):
    checked = prepare_bridge(body, request, require_project=True)
    return bridge_plan(body, checked)


def submit_bridge(body, request, checked, *, identifier=None):
    research = request.app.state.research
    run = research.store.get_run(identifier) if identifier else None
    if run is None:
        manifests = [request.app.state.center.snapshot(ticker, frame, 'snapshot', origin=origin)
                     for ticker, frame, origin in checked]
        run = research.schedule(body.config.model_dump(mode='json'), manifest=manifests, identifier=identifier)
    else:
        run = research.get_run(identifier)
    if body.project_id:
        request.app.state.projects.link(body.project_id, 'simulation', run['id'])
    return run


@router.post('/bridge/backtests', status_code=202)
def bridge_backtest(body: BridgeRequest, request: Request):
    """Only immutable raw OHLCV inputs cross this boundary; never re-download."""
    checked = prepare_bridge(body, request, require_project=body.plan_id is not None)
    if body.plan_id is None:
        return submit_bridge(body, request, checked)
    plan = bridge_plan(body, checked)
    if plan['plan_id'] != body.plan_id:
        raise ResearchError(409, '回测配置、快照或引擎版本已变化，请重新预检后提交')
    # The plan key is stable across sessions. Returning the existing run repairs
    # the project link if the server stopped between the two database writes.
    identifier = hashlib.sha256(f"bridge-run:{body.plan_id}".encode()).hexdigest()[:32]
    with plan_submission_lock:
        return submit_bridge(body, request, checked, identifier=identifier)
