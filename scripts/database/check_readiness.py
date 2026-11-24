"""Check the running API from its own container without publishing a port."""

import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def request(path):
    url = f"http://127.0.0.1:8000{path}"
    for attempt in range(20):
        try:
            with urlopen(url, timeout=5) as response:
                return response.status, json.load(response)
        except HTTPError as response:
            return response.code, json.load(response)
        except URLError:
            if attempt == 19:
                raise
            time.sleep(0.5)


status = int(sys.argv[1])
assert request("/healthz") == (200, {"status": "ok"})
assert request("/readyz") == (
    status,
    {"status": "ready" if status == 200 else "unavailable"},
)
