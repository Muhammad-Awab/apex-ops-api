import pytest

from app.config import ConfigError, load_settings, redact_url


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("DATABASE_URL", "DB_PASSWORD", "DB_PASSWORD_FILE", "FAULT_MODE"):
        monkeypatch.delenv(name, raising=False)


def test_password_is_read_from_secret_file(monkeypatch, tmp_path):
    secret = tmp_path / "db_password"
    secret.write_text("s3cr3t/with:special@chars\n", encoding="utf-8")
    monkeypatch.setenv("DB_PASSWORD_FILE", str(secret))
    monkeypatch.setenv("DB_HOST", "db")

    settings = load_settings()
    # URL-encoded so special characters cannot break the DSN.
    assert "s3cr3t%2Fwith%3Aspecial%40chars@db:5432" in settings.database_url
    # ...and never exposed by repr() / logs.
    assert "s3cr3t" not in repr(settings)
    assert "s3cr3t" not in settings.database_url_redacted


def test_missing_password_fails_fast():
    with pytest.raises(ConfigError, match="password missing"):
        load_settings()


def test_invalid_fault_mode_is_rejected(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("FAULT_MODE", "chaos-monkey")
    with pytest.raises(ConfigError, match="FAULT_MODE"):
        load_settings()


def test_redact_url_hides_password():
    assert redact_url("postgresql+psycopg://apex:hunter2@db:5432/apex_ops") == (
        "postgresql+psycopg://apex:***@db:5432/apex_ops"
    )
    assert redact_url("sqlite:///tmp/x.db") == "sqlite:///tmp/x.db"
