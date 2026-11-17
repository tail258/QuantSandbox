import hashlib
import json
from backend.workbench.etf_demo import create_demo
from backend.workbench.etf_intraday import comparison, timestamp


def test_synthetic_demo_is_deterministic_recomputable_and_isolated(monkeypatch):
    from backend.workbench import store
    import socket
    def forbidden(*args, **kwargs):
        raise AssertionError('Demo must not access the persistent store')
    monkeypatch.setattr(store, 'db', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    first = create_demo()
    assert first == create_demo()
    assert first['synthetic'] is True
    assert len(first['inputs']['history']['rows']) == 48 * 21
    assert first['comparison']['ratio'] == 1.5
    assert first['comparison']['sample_count'] == 20
    inputs = first['inputs']
    assert first['comparison'] == comparison(inputs['quote'], inputs['history'], timestamp(first['clock']), inputs['calendar'])
    assert first['input_sha256'] == hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def test_demo_api_exposes_the_same_fixed_inputs():
    from fastapi.testclient import TestClient
    from backend.main import app
    response = TestClient(app).get('/api/research/etf/intraday-demo')
    assert response.status_code == 200
    assert response.json() == create_demo()
