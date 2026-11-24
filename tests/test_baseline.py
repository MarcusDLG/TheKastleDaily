from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[1]


def test_health():
    response = TestClient(app).get('/healthz')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


def test_admin_not_exposed():
    client = TestClient(app)
    for path in ('/docs', '/redoc', '/openapi.json', '/admin', '/mcp'):
        assert client.get(path).status_code == 404


def test_editorial_baseline():
    config = yaml.safe_load((ROOT / 'config/editorial.yaml').read_text())
    assert config['target_articles'] == 15
    assert config['weights'] == dict(formula_1=19, nascar=19, technology_ai=24,
                                     software_engineering=14, sim_racing=14,
                                     maker_radio=10, other=0)
    assert sum(config['weights'].values()) == 100
    assert config['social_video_sources'] == ['youtube']
    assert config['timezone'] == 'America/New_York'


def test_network_isolation():
    compose = yaml.safe_load((ROOT / 'compose.yaml').read_text())
    api, db = (compose['services'][key] for key in ('api', 'db'))
    assert not db.get('ports')
    assert compose['networks']['database']['internal'] is True
    assert api['ports'] == ['127.0.0.1:8765:8000']
    assert api['read_only'] is True
    assert api['cap_drop'] == ['ALL']
    assert all(not s.get('privileged') for s in (api, db))
