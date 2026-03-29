"""Item Trends segment cache layer (MySQL → Parquet)."""

import logging
from pathlib import Path
from typing import Dict

import pandas as pd
from sqlalchemy import text

try:
    from db_utils import get_engine
except ImportError:
    from ..db_utils import get_engine

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / "cache"
CUSTOMER_SEGMENTS_FILE = CACHE_DIR / "customer_segments.parquet"
SEGMENT_TABLE_NAME = "customer_segments"


def _table_exists(table_name: str) -> bool:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT 1 AS ok
                FROM information_schema.tables
                WHERE table_schema = DATABASE()
                  AND LOWER(table_name) = :table_name
                LIMIT 1
                """
            ),
            {"table_name": table_name.lower()},
        ).mappings().first()
    return bool(row)


def _table_row_count(table_name: str) -> int:
    engine = get_engine()
    with engine.connect() as conn:
        count = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
        return int(count.scalar() or 0)


def ensure_segments_table_from_csv(force_reload: bool = False) -> Dict[str, int]:
    """Ensure `customer_segments` table exists. Data lives in DB; CSV fallback removed."""
    if _table_exists(SEGMENT_TABLE_NAME):
        existing_rows = _table_row_count(SEGMENT_TABLE_NAME)
        if existing_rows > 0:
            return {"rows": existing_rows}

    raise RuntimeError(
        "customer_segments table is empty or missing. "
        "Run the ETL pipeline to populate it from the data warehouse."
    )


def _load_raw_segments_from_parquet() -> pd.DataFrame:
    if not CUSTOMER_SEGMENTS_FILE.exists():
        return pd.DataFrame()
    if CUSTOMER_SEGMENTS_FILE.stat().st_size == 0:
        return pd.DataFrame()

    try:
        df = pd.read_parquet(CUSTOMER_SEGMENTS_FILE)
    except Exception:
        return pd.DataFrame()

    if df.empty or "Segment" not in df.columns:
        return pd.DataFrame()
    return df


def _load_raw_segments_from_db() -> pd.DataFrame:
    if not _table_exists(SEGMENT_TABLE_NAME):
        return pd.DataFrame()

    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(f"SELECT * FROM {SEGMENT_TABLE_NAME}"), conn)


def _aggregate_segments(raw_df: pd.DataFrame) -> pd.DataFrame:
    if raw_df.empty or "Segment" not in raw_df.columns:
        return pd.DataFrame(columns=["Segment", "total"])
    aggregated = raw_df.groupby("Segment", dropna=False).size().reset_index(name="total")
    return aggregated.sort_values("total", ascending=False).reset_index(drop=True)


def _write_raw_segments_to_parquet(raw_df: pd.DataFrame) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    raw_df.to_parquet(CUSTOMER_SEGMENTS_FILE, index=False)


def build_customer_segments_cache(force_refresh: bool = False) -> pd.DataFrame:
    """Build/load parquet cache and return aggregated segments for API."""
    if not force_refresh:
        parquet_df = _load_raw_segments_from_parquet()
        if not parquet_df.empty:
            return _aggregate_segments(parquet_df)

    ensure_segments_table_from_csv(force_reload=False)
    db_df = _load_raw_segments_from_db()

    if db_df.empty:
        return pd.DataFrame(columns=["Segment", "total"])

    _write_raw_segments_to_parquet(db_df)
    return _aggregate_segments(db_df)


def load_customer_segments_cached() -> pd.DataFrame:
    """Read from parquet if exists+non-empty, otherwise build parquet first."""
    return build_customer_segments_cache(force_refresh=False)


def refresh_customer_segments_cache() -> Dict[str, object]:
    """Force refresh parquet from MySQL `customer_segments` table."""
    try:
        ensure_segments_table_from_csv(force_reload=False)
        aggregated_df = build_customer_segments_cache(force_refresh=True)
        return {
            "status": "success",
            "message": "Customer segments cache refreshed",
            "rows": int(aggregated_df["total"].sum()) if not aggregated_df.empty else 0,
            "segments": len(aggregated_df),
        }
    except Exception as exc:
        logger.error(f"Error refreshing customer segments cache: {exc}")
        return {"status": "error", "message": str(exc)}
