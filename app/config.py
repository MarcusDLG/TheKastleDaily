"""Editorial configuration — volume-first per WEB_ADMIN.md phase 3.

The mutable copy lives next to the database (`<db dir>/editorial.yaml`);
the image-baked `config/editorial.yaml` is the seed copied on first
load. `KASTLE_EDITORIAL_CONFIG` overrides the location outright.
Writes are atomic (tmp + replace) and validated before landing.
"""

import os
import shutil
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

BAKED_CONFIG = Path("config/editorial.yaml")


def editorial_config_path() -> Path:
    override = os.environ.get("KASTLE_EDITORIAL_CONFIG")
    if override:
        return Path(override)
    from app.database import database_path

    db = database_path()
    if db == ":memory:":
        return BAKED_CONFIG
    return Path(db).parent / "editorial.yaml"


def load_editorial_config() -> dict:
    """The live config — seeds the volume copy from the baked default."""
    path = editorial_config_path()
    if not path.exists() and path != BAKED_CONFIG:
        try:
            shutil.copyfile(BAKED_CONFIG, path)
        except OSError:
            pass
    if not path.exists():
        path = BAKED_CONFIG
    return yaml.safe_load(path.read_text()) or {}


def validate_editorial_config(config: dict) -> None:
    """Enforce the invariants selection and scheduling rely on."""
    weights = config.get("weights")
    if not isinstance(weights, dict) or not weights:
        raise ValueError("weights must be a non-empty map")
    if any(not isinstance(v, int) or v < 0 for v in weights.values()):
        raise ValueError("weights must be non-negative integers")
    if sum(weights.values()) != 100:
        raise ValueError("weights must sum to 100")
    target = config.get("target_articles")
    if not isinstance(target, int) or not 1 <= target <= 50:
        raise ValueError("target_articles must be 1-50")
    try:
        ZoneInfo(str(config["timezone"]))
    except KeyError as error:
        raise ValueError("timezone must be a valid IANA name") from error
    raw = str(config.get("edition_time", ""))
    hour, _, minute = raw.partition(":")
    if not (
        hour.isdigit() and minute.isdigit()
        and 0 <= int(hour) <= 23 and 0 <= int(minute) <= 59
    ):
        raise ValueError("edition_time must be HH:MM")


def save_editorial_config(config: dict) -> Path:
    validate_editorial_config(config)
    path = editorial_config_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(yaml.safe_dump(config, sort_keys=False))
    tmp.replace(path)
    return path
