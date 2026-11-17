"""Daily Chan research on immutable project quotes and portable evidence."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import closing, contextmanager
from datetime import date, datetime, timedelta
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError

from backend.core.data_format import COLUMNS, canonical_json
from backend.services.errors import ResearchError
from backend.workbench import store

MAX_BARS = 4_000
MAX_EVIDENCE_BYTES = 2_000_000
EVIDENCE_SCHEMA = 'quantsandbox.chan-evidence.v1'
ALGORITHM = 'daily-chan-v1'
DEMO_ID = 'daily-chan-demo-v1'


def _date(value: str) -> str:
    if date.fromisoformat(value).isoformat() != value:
        raise ValueError('Use YYYY-MM-DD for observation dates')
    return value


def _source_url(value: str) -> str:
    url = urlsplit(value)
    if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password:
        raise ValueError('Source URL must use HTTP or HTTPS')
    return value


def _source_time(value: str) -> str:
    if datetime.fromisoformat(value).utcoffset() is None:
        raise ValueError('Snapshot acquisition time requires a UTC offset')
    return value


ObservationDate = Annotated[str, AfterValidator(_date)]
SourceUrl = Annotated[str, Field(max_length=2_048), AfterValidator(_source_url)]
Digest = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class EvidenceModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class DailyBar(EvidenceModel):
    date: ObservationDate
    open: Positive
    high: Positive
    low: Positive
    close: Positive
    volume: Annotated[float, Field(ge=0, allow_inf_nan=False)]


class Coverage(EvidenceModel):
    observed_rows: int = Field(ge=1, le=MAX_BARS)
    excluded_suspension_dates: list[ObservationDate] = Field(max_length=MAX_BARS)
    missing_session_dates: list[ObservationDate] | None = Field(max_length=MAX_BARS)
    unknown_suspension_count: int = Field(ge=0, le=MAX_BARS)
    cash_dividend_ex_dates: list[ObservationDate] = Field(max_length=MAX_BARS)
    calendar_verified: bool


class FrozenInput(EvidenceModel):
    mode: Literal['project', 'synthetic']
    project_id: Annotated[str, Field(pattern=r'^[0-9a-f]{32}$')] | None
    snapshot_id: str = Field(pattern=r'^(?:[0-9a-f]{20}|daily-chan-demo-v1)$')
    symbol: str = Field(pattern=r'^(?:[0-9]{6}|CHAN-DEMO)$')
    start_date: ObservationDate
    end_date: ObservationDate
    row_count: int = Field(ge=1, le=MAX_BARS)
    source: str = Field(min_length=1, max_length=500)
    source_url: SourceUrl | None
    fetched_at: Annotated[str, Field(max_length=100), AfterValidator(_source_time)] | None
    price_basis: Literal['raw_unadjusted', 'synthetic']
    volume_unit: Literal['shares', 'artificial']
    sha256: Digest
    source_sha256: Digest | None
    coverage: Coverage


class Evidence(EvidenceModel):
    schema_version: Literal['quantsandbox.chan-evidence.v1']
    algorithm: Literal['daily-chan-v1']
    input: FrozenInput
    bars: list[DailyBar] = Field(min_length=1, max_length=MAX_BARS)
    result_sha256: Digest
    sha256: Digest


def _hash(value) -> str:
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


@contextmanager
def _quotes_database():
    path = store.data_path() / 'workbench.sqlite'
    if not path.is_file():
        yield None
        return
    # Open the existing store without its create/migrate/PRAGMA write path.
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=10)) as connection:
        yield connection


def _quote_keys(project: dict) -> tuple[str, ...]:
    return tuple(f'{prefix}:{symbol}' for symbol in project['symbols'] if re.fullmatch(r'[0-9]{6}', symbol)
                 for prefix in ('quotes', 'execution-quotes'))


def list_snapshots(project: dict) -> list[dict]:
    keys = _quote_keys(project)
    if not keys:
        return []
    placeholders = ','.join('?' for _ in keys)
    with _quotes_database() as connection:
        if connection is None:
            return []
        rows = connection.execute(f'''
            SELECT id, json_extract(payload, '$.symbol'),
                   json_extract(payload, '$.rows[0].date'), json_extract(payload, '$.rows[#-1].date'),
                   json_array_length(payload, '$.rows'), json_extract(payload, '$.source')
            FROM snapshots WHERE key IN ({placeholders})
              AND json_extract(payload, '$.kind') = 'quotes'
              AND json_extract(payload, '$.request.adjust') = '3'
              AND json_array_length(payload, '$.rows') BETWEEN 1 AND ?
            ORDER BY fetched DESC, id
        ''', (*keys, MAX_BARS)).fetchall()
    return [{'id': identifier, 'symbol': symbol, 'start_date': start, 'end_date': end,
             'row_count': count, 'source': source, 'price_basis': 'raw_unadjusted'}
            for identifier, symbol, start, end, count, source in rows if symbol in project['symbols']]


def _project_snapshot(project: dict, snapshot_id: str) -> dict:
    keys = _quote_keys(project)
    with _quotes_database() as connection:
        row = connection.execute('SELECT key,payload FROM snapshots WHERE id=?', (snapshot_id,)).fetchone() if connection else None
    if row is None or row[0] not in keys:
        raise ResearchError(404, 'Daily quote snapshot does not belong to this project')
    snapshot = json.loads(row[1])
    if snapshot.get('symbol') not in project['symbols']:
        raise ResearchError(404, 'Daily quote snapshot does not belong to this project')
    if snapshot.get('kind') != 'quotes' or snapshot.get('request', {}).get('adjust') != '3':
        raise ResearchError(422, 'Daily Chan requires an explicitly unadjusted quote snapshot')
    if '成交量统一为股' not in snapshot.get('method', ''):
        raise ResearchError(422, 'Daily quote snapshot must declare volume in shares')
    if not 1 <= len(snapshot.get('rows', [])) <= MAX_BARS:
        raise ResearchError(422, f'Daily quote snapshot must contain 1–{MAX_BARS} rows')
    source = {key: value for key, value in snapshot.items() if key != 'id'}
    if snapshot.get('id') != snapshot_id or not hashlib.sha256(store.encode(source).encode()).hexdigest().startswith(snapshot_id):
        raise ResearchError(409, 'Research quote snapshot failed its original integrity check')
    return snapshot


def _bars(rows: list[dict]) -> list[dict]:
    return [DailyBar.model_validate({key: row[key] for key in COLUMNS}).model_dump() for row in rows]


def _frozen_input(**metadata) -> dict:
    return FrozenInput.model_validate(metadata).model_dump()


def _project_inputs(project: dict, snapshot: dict) -> tuple[dict, list[dict]]:
    rows = snapshot['rows']
    try:
        original_dates = [_date(row['date']) for row in rows]
        if original_dates != sorted(set(original_dates)):
            raise ValueError('Quote dates must be unique and strictly increasing')
        skipped = [row['date'] for row in rows if row.get('is_suspended') is True]
        bars = _bars([row for row in rows if row.get('is_suspended') is not True])
        if not bars:
            raise ValueError('Snapshot contains no nonsuspended daily observations')
        execution = snapshot.get('execution_history', {})
        calendar = execution.get('calendar') or {}
        sessions = calendar.get('sessions')
        ex_dates = sorted({row['dividend_ex_date'] for row in rows if row.get('dividend_ex_date')})
        metadata = _frozen_input(
            mode='project', project_id=project['id'], snapshot_id=snapshot['id'], symbol=snapshot['symbol'],
            start_date=bars[0]['date'], end_date=bars[-1]['date'], row_count=len(bars), source=snapshot['source'],
            source_url=snapshot.get('source_url') or None, fetched_at=snapshot.get('fetched_at'),
            price_basis='raw_unadjusted', volume_unit='shares', sha256=_hash(bars),
            source_sha256=hashlib.sha256(store.encode(snapshot).encode()).hexdigest(),
            coverage={'observed_rows': len(rows), 'excluded_suspension_dates': skipped,
                      'missing_session_dates': sorted(set(sessions) - set(original_dates)) if sessions is not None else None,
                      'unknown_suspension_count': sum(row.get('is_suspended') is None for row in rows),
                      'cash_dividend_ex_dates': ex_dates, 'calendar_verified': sessions is not None},
        )
    except (KeyError, ValueError, TypeError, ValidationError) as exc:
        raise ResearchError(422, f'Invalid daily quote snapshot: {exc}') from exc
    return metadata, bars


def _demo_inputs() -> tuple[dict, list[dict]]:
    # Sawtooth sub-trends embedded in a larger rise/fall, with several crossings.
    # Integer prices are in hundredths, so interpolation rounds deterministically.
    points = (1300, 1000, 1600, 1200, 2000, 1400, 1700, 900, 1500, 1100,
              1800, 1200, 1500, 800, 1400, 1000, 1700, 1100, 1400, 700,
              1300, 900, 1600, 1000, 1300, 600, 1200, 800, 1500, 900, 1250)
    steps = 5
    prices = [((steps - offset) * start + offset * finish) // steps
              for start, finish in zip(points, points[1:]) for offset in range(steps)]
    prices.append(points[-1])
    session = date(2024, 1, 2)
    bars = []
    for index, price in enumerate(prices):
        while session.weekday() >= 5:
            session += timedelta(days=1)
        bars.append({'date': session.isoformat(), 'open': (price - 1) / 100, 'high': (price + 2) / 100,
                     'low': (price - 2) / 100, 'close': (price + 1) / 100, 'volume': 100_000.0 + index * 100})
        session += timedelta(days=1)
    return _frozen_input(
        mode='synthetic', project_id=None, snapshot_id=DEMO_ID, symbol='CHAN-DEMO', start_date=bars[0]['date'],
        end_date=bars[-1]['date'], row_count=len(bars), source='QuantSandbox synthetic fixture',
        source_url=None, fetched_at=None, price_basis='synthetic', volume_unit='artificial',
        sha256=_hash(bars), source_sha256=None,
        coverage={'observed_rows': len(bars), 'excluded_suspension_dates': [], 'missing_session_dates': None,
                  'unknown_suspension_count': 0, 'cash_dividend_ex_dates': [], 'calendar_verified': False},
    ), bars


def _response(metadata: dict, bars: list[dict]) -> dict:
    from backend.core.chan import recognize_daily

    dates = [bar['date'] for bar in bars]
    if dates != sorted(set(dates)):
        raise ResearchError(422, 'Daily bars must have unique ascending dates')
    if any(bar['low'] > min(bar['open'], bar['close']) or bar['high'] < max(bar['open'], bar['close']) for bar in bars):
        raise ResearchError(422, 'Daily quote highs or lows disagree with opening and closing prices')
    if (metadata['row_count'], metadata['start_date'], metadata['end_date'], metadata['sha256']) != (
            len(bars), dates[0], dates[-1], _hash(bars)):
        raise ResearchError(422, 'Chan evidence does not match its frozen input records')
    coverage = metadata['coverage']
    excluded, missing = coverage['excluded_suspension_dates'], coverage['missing_session_dates']
    absent = excluded + (missing or [])
    if (coverage['observed_rows'] != len(bars) + len(excluded) or coverage['unknown_suspension_count'] > len(bars)
            or coverage['calendar_verified'] != (missing is not None) or len(set(absent)) != len(absent)
            or set(absent).intersection(dates)):
        raise ResearchError(422, 'Chan evidence has inconsistent observation coverage')
    result = recognize_daily(bars)
    if result['algorithm'] != ALGORITHM:
        raise RuntimeError('Chan evidence version and core algorithm differ')
    package = {'schema_version': EVIDENCE_SCHEMA, 'algorithm': ALGORITHM, 'input': metadata,
               'bars': bars, 'result_sha256': _hash(result)}
    raw = canonical_json({**package, 'sha256': _hash(package)})
    return {'input': metadata, 'bars': bars, 'result': result, 'evidence': raw}


def analyze_project(project: dict, snapshot_id: str) -> dict:
    return _response(*_project_inputs(project, _project_snapshot(project, snapshot_id)))


def demo() -> dict:
    return _response(*_demo_inputs())


def _unique_members(pairs: list[tuple]) -> dict:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError('Duplicate member in Chan evidence')
    return result


def replay(raw: bytes) -> dict:
    if len(raw) > MAX_EVIDENCE_BYTES:
        raise ResearchError(413, f'Chan evidence must not exceed {MAX_EVIDENCE_BYTES} bytes')
    try:
        package = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_unique_members)
        if not isinstance(package, dict):
            raise ValueError('Expected an evidence object')
        checksum = package.get('sha256')
        if checksum != _hash({key: value for key, value in package.items() if key != 'sha256'}):
            raise ValueError('Chan evidence checksum mismatch')
        evidence = Evidence.model_validate(package)
    except (ValueError, TypeError, RecursionError, ValidationError) as exc:
        raise ResearchError(422, 'Invalid, altered or unsupported Chan evidence') from exc
    metadata = evidence.input.model_dump()
    bars = [bar.model_dump() for bar in evidence.bars]
    if metadata['mode'] == 'synthetic':
        if (metadata, bars) != _demo_inputs():
            raise ResearchError(422, 'Chan demo evidence does not match the fixed fixture')
    elif (metadata['price_basis'] != 'raw_unadjusted' or metadata['volume_unit'] != 'shares'
          or not all(metadata[field] for field in ('project_id', 'source_sha256', 'fetched_at'))
          or not re.fullmatch(r'[0-9a-f]{20}', metadata['snapshot_id']) or metadata['symbol'] == 'CHAN-DEMO'):
        raise ResearchError(422, 'Invalid project attribution in Chan evidence')
    response = _response(metadata, bars)
    if _hash(response['result']) != evidence.result_sha256:
        raise ResearchError(409, 'Recomputed Chan structures differ from the exported result')
    return {**response, 'verified': True}
