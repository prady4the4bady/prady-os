from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import DateTime, Float, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def _default_database_url() -> str:
    local_db = Path(__file__).resolve().parents[1] / "data" / "model_registry.db"
    local_db.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{local_db}"


DATABASE_URL = os.getenv("DATABASE_URL", _default_database_url())


class Base(DeclarativeBase):
    pass


class ModelRecord(Base):
    __tablename__ = "models"

    model_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    quantization: Mapped[str] = mapped_column(String(32), default="unknown")
    size_gb: Mapped[float] = mapped_column(Float, default=0.0)
    pulled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    status: Mapped[str] = mapped_column(String(32), default="downloading")
    benchmark_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    tokens_per_sec: Mapped[float | None] = mapped_column(Float, nullable=True)


engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
