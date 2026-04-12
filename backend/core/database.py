"""
Database utilities for BI Dashboard Backend.
Single source of truth for DW engine, query helpers, and serialization.
"""

import os
import sys
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core.config as config  # Import file config đã sửa để lấy thông số SSL

# ── Use centralized configuration ──────────────────────────────────────────
DB_HOST = config.DW_HOST
DB_PORT = config.DW_PORT
DB_USER = config.DW_USER
DB_PASSWORD = config.DW_PASSWORD
DB_NAME = config.DW_DATABASE

# [CLOUD - COMMENTED OUT] Cấu hình SSL bắt buộc cho TiDB Cloud Serverless
# CONNECT_ARGS = {
#     "ssl": {
#         "ca": config.DW_SSL_CA
#     },
#     "connect_timeout": 10
# }

# [LOCAL] Không cần SSL cho MySQL local
CONNECT_ARGS = {
    "connect_timeout": 10
}

_ENGINE: Optional[Engine] = None
_RESOLVED_DB_NAME: Optional[str] = None


def _build_url(database: str) -> str:
    # Không để SSL trong URL để tránh xung đột với connect_args
    return f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{database}?charset=utf8mb4"


def resolve_database_name() -> str:
    global _RESOLVED_DB_NAME
    if _RESOLVED_DB_NAME:
        return _RESOLVED_DB_NAME

    preferred = [DB_NAME, "retails_datasets", "retails_dataset"]
    
    # Thêm CONNECT_ARGS (SSL) vào đây để có thể truy cập information_schema
    discovery_engine = create_engine(
        _build_url("information_schema"),
        pool_pre_ping=True,
        connect_args=CONNECT_ARGS,
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
        # Nếu không tìm thấy, trả về DB_NAME mặc định để tránh lỗi logic
        return DB_NAME

    _RESOLVED_DB_NAME = str(db_rows[0][0])
    return _RESOLVED_DB_NAME


def get_engine() -> Engine:
    global _ENGINE
    if _ENGINE is None:
        db_name = resolve_database_name()
        _ENGINE = create_engine(
            _build_url(db_name),
            pool_size=5,        # Giảm pool_size để tiết kiệm RAM trên Render
            max_overflow=10,
            pool_recycle=3600,
            pool_pre_ping=True,
            connect_args=CONNECT_ARGS, # Áp dụng SSL
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
    # Chế độ stream_results rất quan trọng với database 2.4GB để tránh tràn RAM
    with engine.connect().execution_options(stream_results=True) as conn:
        result = conn.execute(text(sql), params or {})
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