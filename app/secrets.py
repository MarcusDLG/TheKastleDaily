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

_aws_cache: dict[str, str | None] = {}
_aws_client_instance: object = None
_aws_client_failed = False


def secret(name: str) -> str | None:
    """Resolve a secret by name. None when unset everywhere."""
    value = os.environ.get(name)
    if value is not None:
        return value
    return _lookup(os.environ.get("SECRETS_BACKEND", "env"), name)


def _lookup(backend: str, name: str) -> str | None:
    if backend == "aws":
        return _aws_lookup(name)
    # Unknown backend: fail closed to unset rather than raise —
    # a misconfigured backend must not crash the pipeline.
    return None


def _aws_lookup(name: str) -> str | None:
    # Cache negatives too: a missing secret must not re-issue an API
    # call on every pipeline pass.
    if name not in _aws_cache:
        _aws_cache[name] = _aws_fetch(name)
    return _aws_cache[name]


def _aws_fetch(name: str) -> str | None:
    try:
        client = _aws_client()
        if client is None:
            return None
        prefix = os.environ.get("SECRETS_PREFIX", "kastle-daily/")
        response = client.get_secret_value(SecretId=prefix + name)
    except Exception:
        return None
    value = response.get("SecretString")
    if value is not None:
        return value
    binary = response.get("SecretBinary")
    if isinstance(binary, bytes):
        try:
            return binary.decode("utf-8")
        except UnicodeDecodeError:
            return None
    return None


def _aws_client():
    """Process-cached boto3 client; None when boto3 or creds are absent."""
    global _aws_client_instance, _aws_client_failed
    if _aws_client_failed:
        return None
    if _aws_client_instance is not None:
        return _aws_client_instance
    try:
        import boto3

        _aws_client_instance = boto3.client("secretsmanager")
    except Exception:
        _aws_client_failed = True
        return None
    return _aws_client_instance
