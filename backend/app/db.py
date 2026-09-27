"""Persistence: every analysis and every approval is stored for the audit trail."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AnalysisRow(Base):
    __tablename__ = "analyses"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    address: Mapped[str] = mapped_column(String(300), index=True)
    list_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    mao: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(40), default="Analyzed")
    inputs: Mapped[dict] = mapped_column(JSON)     # raw provider data, so recompute never refetches
    result: Mapped[dict] = mapped_column(JSON)     # latest Analysis
    trail: Mapped[list] = mapped_column(JSON, default=list)


class ApprovalRow(Base):
    __tablename__ = "approvals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    tier: Mapped[str] = mapped_column(String(20))
    price: Mapped[float] = mapped_column(Float)
    approved_by: Mapped[str] = mapped_column(String(120))
    agent_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    letter_text: Mapped[str] = mapped_column(Text)
    snapshot: Mapped[dict] = mapped_column(JSON)   # criteria, comps used, MAO at the moment of approval
    sent: Mapped[bool] = mapped_column(Boolean, default=False)
    subject: Mapped[str | None] = mapped_column(String(300), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_from: Mapped[str | None] = mapped_column(String(200), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    message_id: Mapped[str | None] = mapped_column(String(300), nullable=True)
    thread_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    send_error: Mapped[str | None] = mapped_column(Text, nullable=True)


_settings = get_settings()
_url = _settings.database_url
if _url.startswith("postgres://"):  # Render/Heroku style URLs
    _url = _url.replace("postgres://", "postgresql+psycopg://", 1)
elif _url.startswith("postgresql://"):
    _url = _url.replace("postgresql://", "postgresql+psycopg://", 1)
engine = create_engine(_url, connect_args={"check_same_thread": False} if _url.startswith("sqlite") else {},
                       pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


# Columns added after the first release. create_all() doesn't alter existing tables,
# so add any that are missing. (Swap for Alembic once the schema changes more often.)
_ADDED_COLUMNS = {
    "approvals": {
        "subject": "VARCHAR(300)", "sent_at": "TIMESTAMP WITH TIME ZONE", "sent_from": "VARCHAR(200)",
        "provider": "VARCHAR(20)", "message_id": "VARCHAR(300)", "thread_id": "VARCHAR(100)", "send_error": "TEXT",
    },
}


def init_db() -> None:
    Base.metadata.create_all(engine)
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in _ADDED_COLUMNS.items():
            have = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in cols.items():
                if name not in have:
                    if engine.dialect.name == "sqlite":
                        ddl = ddl.replace(" WITH TIME ZONE", "")
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def get_session():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
