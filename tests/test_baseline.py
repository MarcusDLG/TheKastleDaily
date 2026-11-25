from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_editorial_baseline():
    config = yaml.safe_load((ROOT / 'config/editorial.yaml').read_text())
    assert config['target_articles'] == 15
    assert config['weights'] == dict(motorsport=18, sim_racing=10,
                                     technology_ai=16, software_engineering=10,
                                     maker_fabrication=12, radio_comms=6,
                                     space=8, culinary=6, visual_craft=4,
                                     homelab=6, life_systems=4)
    assert sum(config['weights'].values()) == 100
    assert config['social_video_sources'] == ['youtube']
    assert config['timezone'] == 'America/New_York'


def test_worker_isolation():
    compose = yaml.safe_load((ROOT / 'compose.yaml').read_text())
    assert set(compose['services']) <= {'worker', 'admin'}
    worker = compose['services']['worker']
    assert not worker.get('ports')
    assert worker['read_only'] is True
    assert worker['cap_drop'] == ['ALL']
    assert 'no-new-privileges:true' in worker['security_opt']
    assert worker.get('privileged') is not True
    assert compose.get('networks') is None


def test_admin_service_exposure():
    """The opt-in admin service hardens like the worker and may only
    publish on the host loopback — never a routable address."""
    compose = yaml.safe_load((ROOT / 'compose.yaml').read_text())
    admin = compose['services'].get('admin')
    if admin is None:
        pytest.skip('admin service not defined')
    assert 'admin' in admin.get('profiles', [])
    assert admin['read_only'] is True
    assert admin['cap_drop'] == ['ALL']
    assert 'no-new-privileges:true' in admin['security_opt']
    for mapping in admin.get('ports', []):
        assert str(mapping).startswith('127.0.0.1:')
