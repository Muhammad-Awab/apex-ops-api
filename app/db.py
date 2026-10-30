"""Database access (SQLAlchemy 2.x).

PostgreSQL in containers; SQLite in unit tests so they run without Docker.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    severity: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class Database:
    def __init__(self, url: str, connect_timeout: int = 2) -> None:
        connect_args = {}
        if url.startswith("postgresql"):
            # Bounds the TCP connect only. DNS lookup time is bounded separately via
            # dns_opt in docker-compose.yml (incident drill finding, docs/evidence/09a_*).
            connect_args = {"connect_timeout": connect_timeout}
        self.engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
        self._sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.schema_ready = False

    def ensure_schema(self) -> None:
        # Simple create-if-missing. A real service would use Alembic migrations
        # (see docs/DECISION_MEMO.md - expand/contract for rollback safety).
        if not self.schema_ready:
            Base.metadata.create_all(self.engine)
            self.schema_ready = True

    def ping(self) -> None:
        with self.engine.connect() as conn:
            conn.execute(text("SELECT 1"))

    @contextmanager
    def session(self) -> Iterator[Session]:
        with self._sessions() as session:
            yield session

    def dispose(self) -> None:
        self.engine.dispose()
