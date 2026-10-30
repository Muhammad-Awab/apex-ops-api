"""Runtime configuration.

All configuration comes from environment variables (12-factor). Secrets are
read from files (``<NAME>_FILE``) so they can be mounted as Docker/Kubernetes
secrets instead of being placed in the environment, where they would leak via
``docker inspect``, crash dumps or ``/proc/<pid>/environ``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import quote_plus, urlsplit, urlunsplit

VALID_FAULT_MODES = {"none", "not_ready", "errors"}


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def read_secret(name: str) -> str | None:
    """Return a secret, preferring ``<name>_FILE`` over the plain ``<name>`` variable."""
    file_path = os.getenv(f"{name}_FILE")
    if file_path:
        try:
            with open(file_path, encoding="utf-8") as fh:
                return fh.read().strip()
        except OSError as exc:
            raise ConfigError(f"cannot read secret file for {name}: {exc.strerror}") from exc
    return os.getenv(name)


def build_database_url() -> str:
    explicit = os.getenv("DATABASE_URL")
    if explicit:
        return explicit

    password = read_secret("DB_PASSWORD")
    if not password:
        raise ConfigError("database password missing: set DB_PASSWORD_FILE (preferred) or DB_PASSWORD")

    user = os.getenv("DB_USER", "apex")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME", "apex_ops")
    return f"postgresql+psycopg://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{name}"


def redact_url(url: str) -> str:
    """Strip the password from a connection URL so it is safe to log."""
    parts = urlsplit(url)
    if parts.password is None:
        return url
    netloc = parts.netloc.replace(f":{parts.password}@", ":***@", 1)
    return urlunsplit(parts._replace(netloc=netloc))


@dataclass(frozen=True)
class Settings:
    service_name: str
    app_version: str
    git_sha: str
    environment: str
    log_level: str
    database_url: str
    fault_mode: str
    db_connect_timeout: int = 2  # seconds; libpq minimum is 2

    @property
    def database_url_redacted(self) -> str:
        return redact_url(self.database_url)

    def __repr__(self) -> str:  # never print the raw DSN
        return (
            f"Settings(service_name={self.service_name!r}, app_version={self.app_version!r}, "
            f"environment={self.environment!r}, database_url={self.database_url_redacted!r}, "
            f"fault_mode={self.fault_mode!r})"
        )


def load_settings() -> Settings:
    fault_mode = os.getenv("FAULT_MODE", "none").lower()
    if fault_mode not in VALID_FAULT_MODES:
        raise ConfigError(f"FAULT_MODE must be one of {sorted(VALID_FAULT_MODES)}, got {fault_mode!r}")

    return Settings(
        service_name=os.getenv("SERVICE_NAME", "apex-ops-api"),
        app_version=os.getenv("APP_VERSION", "0.0.0-dev"),
        git_sha=os.getenv("GIT_SHA", "unknown"),
        environment=os.getenv("ENVIRONMENT", "local"),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        database_url=build_database_url(),
        fault_mode=fault_mode,
        db_connect_timeout=int(os.getenv("DB_CONNECT_TIMEOUT", "2")),
    )
