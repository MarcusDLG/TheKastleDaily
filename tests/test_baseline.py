from pathlib import Path

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
    worker = compose['services']['worker']
    assert len(compose['services']) == 1
    assert not worker.get('ports')
    assert worker['read_only'] is True
    assert worker['cap_drop'] == ['ALL']
    assert 'no-new-privileges:true' in worker['security_opt']
    assert worker.get('privileged') is not True
    assert compose.get('networks') is None
