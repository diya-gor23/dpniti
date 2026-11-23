from __future__ import annotations

import os
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

_TABLES = {"faculty", "student", "timetable"}


def _database_url() -> str:
    url = os.getenv("ACADEMIC_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "Set ACADEMIC_DATABASE_URL to the PostgreSQL connection URL for academic data."
        )
    # Support common provider URLs while making the driver explicit.
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def make_engine() -> Engine:
    return create_engine(
        _database_url(),
        pool_pre_ping=True,
        pool_size=int(os.getenv("PG_POOL_SIZE", "5")),
        max_overflow=int(os.getenv("PG_MAX_OVERFLOW", "5")),
        pool_timeout=30,
        connect_args={"connect_timeout": 10},
    )


engine = make_engine()


def fetch_rows(table: str, *, semester: int | None = None) -> list[dict[str, Any]]:
    """Fetch academic rows from PostgreSQL; table names are allow-listed."""
    if table not in _TABLES:
        raise ValueError(f"Unsupported academic table: {table}")
    if table in {"student", "timetable"} and semester is not None:
        statement = text(f'SELECT * FROM "{table}" WHERE semester = :semester')
        params = {"semester": str(semester)}
    else:
        statement = text(f'SELECT * FROM "{table}"')
        params = {}
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(statement, params).mappings().all()]


def check_database() -> dict[str, Any]:
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version() ")).scalar_one()
        counts = {}
        for table in sorted(_TABLES):
            exists = connection.execute(
                text("SELECT to_regclass(:table_name)"), {"table_name": f"public.{table}"}
            ).scalar_one()
            if exists:
                counts[table] = connection.execute(
                    text(f'SELECT COUNT(*) FROM "{table}"')
                ).scalar_one()
            else:
                counts[table] = None
    return {"version": version, "counts": counts}
