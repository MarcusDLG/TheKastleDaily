from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_editorial_baseline():
    config = yaml.safe_load((ROOT / 'config/editorial.yaml').read_text())
    assert config['target_articles'] == 15
    assert config['weights'] == dict(formula_1=19, nascar=19, technology_ai=24,
                                     software_engineering=14, sim_racing=14,
                                     maker_radio=10, other=0)
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
