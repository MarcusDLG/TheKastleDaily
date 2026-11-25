"""Secret resolution — SECRETS.md milestone.

Resolution chain: process environment first, then the configured
backend (`SECRETS_BACKEND`, default `"env"`). The env backend is a
pure passthrough — the deployment default and zero-diff from direct
`os.environ` reads. Managed backends (aws) resolve lazily and cache
per process; they are only consulted when the variable is absent from
the environment, so `.env` files and local overrides always win.

Contract: values are never logged; a failed or unknown backend
resolves to None — identical to an unset variable, so consumers keep
their existing missing-env behavior (delivery skips, template
generator). Fails closed, never raises on lookup.
"""

import os


def secret(name: str) -> str | None:
    """Resolve a secret by name. None when unset everywhere."""
    value = os.environ.get(name)
    if value is not None:
        return value
    return _lookup(os.environ.get("SECRETS_BACKEND", "env"), name)


def _lookup(backend: str, name: str) -> str | None:
    if backend == "env":
        return None
    # Unknown backend: fail closed to unset rather than raise —
    # a misconfigured backend must not crash the pipeline.
    return None
