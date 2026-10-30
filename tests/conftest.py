from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_settings(database_url: str, **overrides) -> Settings:
    values = {
        "service_name": "apex-ops-api",
        "app_version": "9.9.9-test",
        "git_sha": "deadbeef",
        "environment": "test",
        "log_level": "INFO",
        "database_url": database_url,
        "fault_mode": "none",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def client_factory(tmp_path) -> Iterator[Callable[..., TestClient]]:
    """Build a TestClient (lifespan started) backed by a throwaway SQLite file."""
    clients: list[TestClient] = []

    def factory(database_url: str | None = None, **overrides) -> TestClient:
        url = database_url or f"sqlite:///{tmp_path / 'test.db'}"
        client = TestClient(create_app(make_settings(url, **overrides)))
        client.__enter__()
        clients.append(client)
        return client

    yield factory
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def client(client_factory) -> TestClient:
    return client_factory()
