"""The public release example must be offline, isolated and reproducible."""
import hashlib
import json
import socket

import pytest

from backend.core.data_format import canonical_json
from backend.services.errors import ResearchError
from backend.services.evidence import EvidenceService
from scripts.reproduce import EXPECTED, reproduce


def test_offline_example_replays_with_fixed_hashes_and_controls(tmp_path, monkeypatch):
    private = tmp_path / 'private-data'
    private.mkdir()
    sentinel = private / 'do-not-read.txt'
    sentinel.write_text('private', encoding='utf-8')
    monkeypatch.setenv('QUANT_SANDBOX_DATA_DIR', str(private))

    def network_forbidden(*args, **kwargs):
        raise AssertionError('The canonical example must not access the network')

    monkeypatch.setattr(socket.socket, 'connect', network_forbidden)
    output = tmp_path / 'public-example'
    first = reproduce(output)
    second = reproduce()
    for key, value in EXPECTED.items():
        assert first[key] == second[key] == value
    assert first['replay']['matched'] is True
    assert first['replay']['different_fields'] == []
    assert first['execution_fields'] == ['is_suspended', 'limit_up', 'limit_down']
    assert first['metrics'] == second['metrics']
    assert list(private.iterdir()) == [sentinel]
    assert sentinel.read_text(encoding='utf-8') == 'private'
    raw = (output / 'evidence.json').read_text(encoding='utf-8')
    assert str(tmp_path) not in raw
    assert str(tmp_path) not in (output / 'report.json').read_text(encoding='utf-8')
    package = json.loads(raw)
    rows = package['datasets'][0]['rows']
    assert {row['date'] for row in rows if row['is_suspended']} == {'2024-03-04'}
    assert all(row['limit_up'] is None and row['limit_down'] is None for row in rows)
    assert package['datasets'][0]['manifest']['sha256'] == EXPECTED['snapshot_sha256']
    assert package['sha256'] == hashlib.sha256(canonical_json({
        key: value for key, value in package.items() if key != 'sha256'
    }).encode('utf-8')).hexdigest()


def test_existing_output_is_never_overwritten(tmp_path):
    target = tmp_path / 'evidence.json'
    target.write_text('keep this original', encoding='utf-8')
    with pytest.raises(ValueError, match='empty'):
        reproduce(tmp_path)
    assert target.read_text(encoding='utf-8') == 'keep this original'


def test_changed_execution_control_is_rejected_even_after_outer_rehash(tmp_path):
    from backend.core.data_center import DataCenter
    from backend.services.research import ResearchService
    from backend.services.store import Store

    output = tmp_path / 'public'
    reproduce(output)
    package = json.loads((output / 'evidence.json').read_text(encoding='utf-8'))
    package['datasets'][0]['rows'][0]['is_suspended'] = True
    package['sha256'] = hashlib.sha256(canonical_json({
        key: value for key, value in package.items() if key != 'sha256'
    }).encode('utf-8')).hexdigest()
    store = Store(tmp_path / 'tamper-check')
    with pytest.raises(ResearchError, match='SHA256'):
        EvidenceService(ResearchService(store), DataCenter(root=store.root)).import_run(package)
