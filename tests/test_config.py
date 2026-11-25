import pytest
import yaml

from app.config import (
    BAKED_CONFIG,
    editorial_config_path,
    load_editorial_config,
    save_editorial_config,
    validate_editorial_config,
)

BASE = {
    "target_articles": 15,
    "timezone": "America/New_York",
    "edition_time": "07:00",
    "weights": {"a": 60, "b": 40},
}


def test_path_override(monkeypatch, tmp_path):
    target = tmp_path / "editorial.yaml"
    monkeypatch.setenv("KASTLE_EDITORIAL_CONFIG", str(target))
    assert editorial_config_path() == target


def test_path_follows_database_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("KASTLE_EDITORIAL_CONFIG", raising=False)
    monkeypatch.setenv("KASTLE_DB", str(tmp_path / "kastle.db"))
    assert editorial_config_path() == tmp_path / "editorial.yaml"


def test_load_seeds_from_baked(monkeypatch, tmp_path):
    target = tmp_path / "editorial.yaml"
    monkeypatch.setenv("KASTLE_EDITORIAL_CONFIG", str(target))
    config = load_editorial_config()
    assert target.exists()
    assert config == yaml.safe_load(BAKED_CONFIG.read_text())


def test_load_reads_volume_copy(monkeypatch, tmp_path):
    target = tmp_path / "editorial.yaml"
    target.write_text(yaml.safe_dump(BASE))
    monkeypatch.setenv("KASTLE_EDITORIAL_CONFIG", str(target))
    assert load_editorial_config()["weights"] == {"a": 60, "b": 40}


def test_save_roundtrip_atomic(monkeypatch, tmp_path):
    target = tmp_path / "editorial.yaml"
    monkeypatch.setenv("KASTLE_EDITORIAL_CONFIG", str(target))
    updated = dict(BASE, edition_time="06:30")
    save_editorial_config(updated)
    assert yaml.safe_load(target.read_text()) == updated
    assert not target.with_suffix(".tmp").exists()


def test_save_rejects_invalid(monkeypatch, tmp_path):
    target = tmp_path / "editorial.yaml"
    target.write_text(yaml.safe_dump(BASE))
    monkeypatch.setenv("KASTLE_EDITORIAL_CONFIG", str(target))
    bad = dict(BASE, weights={"a": 99})
    with pytest.raises(ValueError, match="sum"):
        save_editorial_config(bad)
    assert yaml.safe_load(target.read_text()) == BASE  # untouched


@pytest.mark.parametrize(
    "patch,match",
    [
        ({"weights": {"a": 99}}, "sum"),
        ({"weights": {"a": -1, "b": 101}}, "non-negative"),
        ({"weights": {}}, "non-empty"),
        ({"target_articles": 0}, "target_articles"),
        ({"target_articles": 51}, "target_articles"),
        ({"timezone": "Not/AZone"}, "timezone"),
        ({"edition_time": "25:00"}, "edition_time"),
        ({"edition_time": "seven"}, "edition_time"),
    ],
)
def test_validate_rejects(patch, match):
    with pytest.raises(ValueError, match=match):
        validate_editorial_config(dict(BASE, **patch))
