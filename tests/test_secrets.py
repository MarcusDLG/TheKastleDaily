import pytest

from app import secrets
from app.secrets import secret


class _FakeSecretsClient:
    """Stand-in for a boto3 Secrets Manager client."""

    def __init__(self, values: dict):
        self.values = values
        self.calls: list[str] = []

    def get_secret_value(self, SecretId: str) -> dict:
        self.calls.append(SecretId)
        value = self.values[SecretId]
        if isinstance(value, Exception):
            raise value
        return {"SecretString": value}


@pytest.fixture
def fake_aws(monkeypatch):
    """aws backend with an injected client and a fresh value cache."""
    monkeypatch.setenv("SECRETS_BACKEND", "aws")
    monkeypatch.delenv("SECRETS_PREFIX", raising=False)
    monkeypatch.setattr(secrets, "_aws_cache", {})

    def install(values: dict) -> _FakeSecretsClient:
        client = _FakeSecretsClient(values)
        monkeypatch.setattr(secrets, "_aws_client", lambda: client)
        return client

    return install


def test_env_value_wins(monkeypatch):
    monkeypatch.setenv("SMTP_PASSWORD", "from-env")
    monkeypatch.setenv("SECRETS_BACKEND", "aws")
    assert secret("SMTP_PASSWORD") == "from-env"


def test_unset_resolves_none(monkeypatch):
    monkeypatch.delenv("MISSING_VALUE", raising=False)
    monkeypatch.delenv("SECRETS_BACKEND", raising=False)
    assert secret("MISSING_VALUE") is None


def test_env_backend_resolves_none(monkeypatch):
    monkeypatch.delenv("MISSING_VALUE", raising=False)
    monkeypatch.setenv("SECRETS_BACKEND", "env")
    assert secret("MISSING_VALUE") is None


def test_unknown_backend_fails_closed(monkeypatch):
    monkeypatch.delenv("MISSING_VALUE", raising=False)
    monkeypatch.setenv("SECRETS_BACKEND", "nonexistent")
    assert secret("MISSING_VALUE") is None


def test_empty_string_returned_verbatim(monkeypatch):
    """Empty env values pass through; call sites normalize."""
    monkeypatch.setenv("SOME_VALUE", "")
    assert secret("SOME_VALUE") == ""


def test_aws_resolves_prefixed_name(monkeypatch, fake_aws):
    client = fake_aws({"kastle-daily/SMTP_PASSWORD": "from-aws"})
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    assert secret("SMTP_PASSWORD") == "from-aws"
    assert client.calls == ["kastle-daily/SMTP_PASSWORD"]


def test_aws_prefix_override(monkeypatch, fake_aws):
    client = fake_aws({"paper/OPENAI_API_KEY": "sk-x"})
    monkeypatch.setenv("SECRETS_PREFIX", "paper/")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert secret("OPENAI_API_KEY") == "sk-x"
    assert client.calls == ["paper/OPENAI_API_KEY"]


def test_aws_missing_secret_fails_closed(monkeypatch, fake_aws):
    fake_aws({})
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    assert secret("SMTP_PASSWORD") is None


def test_aws_lookup_error_fails_closed(monkeypatch, fake_aws):
    fake_aws({"kastle-daily/SMTP_PASSWORD": RuntimeError("denied")})
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    assert secret("SMTP_PASSWORD") is None


def test_aws_unavailable_client_fails_closed(monkeypatch, fake_aws):
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    monkeypatch.setattr(secrets, "_aws_client", lambda: None)
    assert secret("SMTP_PASSWORD") is None


def test_aws_values_cached_per_process(monkeypatch, fake_aws):
    client = fake_aws({"kastle-daily/SMTP_PASSWORD": "v1"})
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    assert secret("SMTP_PASSWORD") == "v1"
    client.values["kastle-daily/SMTP_PASSWORD"] = "v2"
    assert secret("SMTP_PASSWORD") == "v1"
    assert client.calls == ["kastle-daily/SMTP_PASSWORD"]


def test_aws_misses_cached_too(monkeypatch, fake_aws):
    client = fake_aws({})
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    assert secret("SMTP_PASSWORD") is None
    assert secret("SMTP_PASSWORD") is None
    assert client.calls == ["kastle-daily/SMTP_PASSWORD"]


def test_aws_env_value_short_circuits_backend(monkeypatch, fake_aws):
    client = fake_aws({})
    monkeypatch.setenv("SMTP_PASSWORD", "env-wins")
    assert secret("SMTP_PASSWORD") == "env-wins"
    assert client.calls == []
