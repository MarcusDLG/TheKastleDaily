from app.secrets import secret


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
