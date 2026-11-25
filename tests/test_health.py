import json
from datetime import UTC, datetime, timedelta

from app import health


def write_wake(path, when):
    path.write_text(json.dumps({"wake": when.isoformat()}))


def test_missing_state_is_unhealthy(tmp_path, monkeypatch):
    monkeypatch.setattr(health, "state_path", lambda: tmp_path / "run-state.json")
    assert health.main() == 1


def test_fresh_wake_is_healthy(tmp_path, monkeypatch):
    target = tmp_path / "run-state.json"
    write_wake(target, datetime.now(UTC))
    monkeypatch.setattr(health, "state_path", lambda: target)
    assert health.main() == 0


def test_stale_wake_is_unhealthy(tmp_path, monkeypatch):
    target = tmp_path / "run-state.json"
    write_wake(target, datetime.now(UTC) - timedelta(hours=2))
    monkeypatch.setattr(health, "state_path", lambda: target)
    assert health.main() == 1
