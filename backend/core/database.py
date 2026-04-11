"""
Database utilities for BI Dashboard Backend.
Single source of truth for DW engine, query helpers, and serialization.
"""

import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "12345")
DB_NAME = os.getenv("DB_NAME", "retails_dataset")


_ENGINE: Optional[Engine] = None
_RESOLVED_DB_NAME: Optional[str] = None


def _build_url(database: str) -> str:
    return f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{database}?charset=utf8mb4"


def resolve_database_name() -> str:
    global _RESOLVED_DB_NAME
    if _RESOLVED_DB_NAME:
        return _RESOLVED_DB_NAME

    preferred = [DB_NAME, "retails_datasets", "retails_dataset"]
    discovery_engine = create_engine(
        _build_url("information_schema"),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5},
    )

    with discovery_engine.connect() as conn:
        db_rows = conn.execute(
            text(
                """
                SELECT schema_name
                FROM schemata
                WHERE LOWER(schema_name) LIKE '%retail%'
                ORDER BY CASE
                    WHEN LOWER(schema_name) = LOWER(:db1) THEN 0
                    WHEN LOWER(schema_name) = LOWER(:db2) THEN 1
                    WHEN LOWER(schema_name) = LOWER(:db3) THEN 2
                    ELSE 3
                END,
                schema_name
                """
            ),
            {"db1": preferred[0], "db2": preferred[1], "db3": preferred[2]},
        ).all()

    if not db_rows:
        raise RuntimeError("No MySQL database containing 'retail' was found.")

    _RESOLVED_DB_NAME = str(db_rows[0][0])
    return _RESOLVED_DB_NAME


def get_engine() -> Engine:
    global _ENGINE
    if _ENGINE is None:
        db_name = resolve_database_name()
        _ENGINE = create_engine(
            _build_url(db_name),
            pool_size=10,
            max_overflow=20,
            pool_recycle=3600,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 5},
        )
    return _ENGINE


def normalize_filter_value(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = str(value).strip()
    if stripped == "" or stripped.upper() == "ALL":
        return None
    return stripped


def build_date_filter(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    alias: str = "s",
) -> Tuple[str, Dict[str, Any]]:
    clauses: List[str] = ["1=1"]
    params: Dict[str, Any] = {}

    start = normalize_filter_value(start_date)
    end = normalize_filter_value(end_date)

    if start:
        clauses.append(f"{alias}.DateKey >= :start_date")
        params["start_date"] = start
    if end:
        clauses.append(f"{alias}.DateKey <= :end_date")
        params["end_date"] = end

    return " AND ".join(clauses), params


def serialize_scalar(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def serialize_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {k: serialize_payload(v) for k, v in payload.items()}
    if isinstance(payload, list):
        return [serialize_payload(v) for v in payload]
    if isinstance(payload, tuple):
        return [serialize_payload(v) for v in payload]
    return serialize_scalar(payload)


def fetch_all(sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params or {}).mappings().all()
    return [dict(row) for row in rows]


def fetch_one(sql: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text(sql), params or {}).mappings().first()
    return dict(row) if row else None


def iter_rows(
    sql: str,
    params: Optional[Dict[str, Any]] = None,
    chunk_threshold: int = 10000,
) -> Iterable[Dict[str, Any]]:
    engine = get_engine()
    with engine.connect().execution_options(stream_results=True) as conn:
        result = conn.execute(text(sql), params or {})
        row_count = result.rowcount if result.rowcount is not None else -1
        if row_count != -1 and row_count < chunk_threshold:
            for row in result.mappings().all():
                yield dict(row)
        else:
            for row in result.mappings():
                yield dict(row)


def table_exists(table_name: str) -> bool:
    sql = """
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = :schema_name
      AND table_name = :table_name
    LIMIT 1
    """
    return fetch_one(sql, {"schema_name": resolve_database_name(), "table_name": table_name}) is not None
