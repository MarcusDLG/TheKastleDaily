"""Container health check: exit 0 when the scheduler has woken recently."""

import json
import sys
from datetime import UTC, datetime

from app.schedule import POLL_CAP_SECONDS, state_path

STALE_AFTER = 4 * POLL_CAP_SECONDS


def main() -> int:
    try:
        wake = datetime.fromisoformat(json.loads(state_path().read_text())["wake"])
    except (OSError, ValueError, KeyError):
        return 1
    age = (datetime.now(UTC) - wake).total_seconds()
    return 0 if age < STALE_AFTER else 1


if __name__ == "__main__":
    sys.exit(main())
