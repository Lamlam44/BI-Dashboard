import logging
import re
import threading
import time
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
import pandas as pd
import json
import os
import io as _io
from datetime import datetime
import shutil
import io
from sqlalchemy import text

from .analytics import router as analytics_router
from core.database import get_engine, serialize_payload
from core.config import (
    DW_HOST, DW_PORT, DW_USER, DW_PASSWORD, DW_DATABASE,
)
from .config import BACKUP_DIR, SCHEMA_FILE

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["data-management"])
router.include_router(analytics_router)


def _refresh_summary_and_cache() -> None:
    """Incrementally refresh summary_daily_sales for new rows, then rebuild parquet cache."""
    engine = get_engine()
    with engine.begin() as conn:
        # Ensure watermark table exists
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS _summary_watermarks (
                source_table VARCHAR(64) PRIMARY KEY,
                last_key BIGINT NOT NULL DEFAULT 0
            ) ENGINE=InnoDB
        """))

        # Get current watermarks
        wm_sales = conn.execute(text(
            "SELECT COALESCE((SELECT last_key FROM _summary_watermarks WHERE source_table='FactSales'),0)"
        )).scalar() or 0
        wm_online = conn.execute(text(
            "SELECT COALESCE((SELECT last_key FROM _summary_watermarks WHERE source_table='FactOnlineSales'),0)"
        )).scalar() or 0

        # Get current max keys
        max_sales = conn.execute(text("SELECT COALESCE(MAX(SalesKey),0) FROM FactSales")).scalar() or 0
        max_online = conn.execute(text("SELECT COALESCE(MAX(OnlineSalesKey),0) FROM FactOnlineSales")).scalar() or 0

        has_new = int(max_sales) > int(wm_sales) or int(max_online) > int(wm_online)

        if has_new:
            # Incrementally aggregate only new rows from FactSales
            if int(max_sales) > int(wm_sales):
                conn.execute(text("""
                    REPLACE INTO summary_daily_sales
                        (DateKey, StoreKey, ProductKey, PromotionKey,
                         total_sales_quantity, total_sales_amount,
                         total_return_amount, total_discount_amount, total_cost)
                    SELECT
                        DATE(DateKey), COALESCE(StoreKey,0), ProductKey,
                        COALESCE(PromotionKey,0),
                        SUM(SalesQuantity), SUM(SalesAmount),
                        SUM(COALESCE(ReturnAmount,0)), SUM(COALESCE(DiscountAmount,0)),
                        SUM(COALESCE(TotalCost,0))
                    FROM FactSales
                    WHERE SalesKey > :wm
                    GROUP BY DATE(DateKey), COALESCE(StoreKey,0), ProductKey, COALESCE(PromotionKey,0)
                """), {"wm": int(wm_sales)})
                logger.info(f"summary_daily_sales: refreshed FactSales rows > {wm_sales}")

            # Incrementally aggregate only new rows from FactOnlineSales
            if int(max_online) > int(wm_online):
                conn.execute(text("""
                    REPLACE INTO summary_daily_sales
                        (DateKey, StoreKey, ProductKey, PromotionKey,
                         total_sales_quantity, total_sales_amount,
                         total_return_amount, total_discount_amount, total_cost)
                    SELECT
                        DATE(DateKey), COALESCE(StoreKey,0), ProductKey,
                        COALESCE(PromotionKey,0),
                        SUM(SalesQuantity), SUM(SalesAmount),
                        SUM(COALESCE(ReturnAmount,0)), SUM(COALESCE(DiscountAmount,0)),
                        SUM(COALESCE(TotalCost,0))
                    FROM FactOnlineSales
                    WHERE OnlineSalesKey > :wm
                    GROUP BY DATE(DateKey), COALESCE(StoreKey,0), ProductKey, COALESCE(PromotionKey,0)
                """), {"wm": int(wm_online)})
                logger.info(f"summary_daily_sales: refreshed FactOnlineSales rows > {wm_online}")

            # Update watermarks
            conn.execute(text("""
                INSERT INTO _summary_watermarks (source_table, last_key) VALUES ('FactSales', :v)
                ON DUPLICATE KEY UPDATE last_key = :v
            """), {"v": int(max_sales)})
            conn.execute(text("""
                INSERT INTO _summary_watermarks (source_table, last_key) VALUES ('FactOnlineSales', :v)
                ON DUPLICATE KEY UPDATE last_key = :v
            """), {"v": int(max_online)})
        else:
            logger.info("summary_daily_sales: no new rows to process")

        # ── agg_store_monthly_sales: monthly sales per store ─────
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS agg_store_monthly_sales (
                store_key           INT NOT NULL,
                calendar_year       INT NOT NULL,
                month_number        INT NOT NULL,
                total_sales_amount  DECIMAL(18,2) NOT NULL DEFAULT 0,
                total_sales_quantity DECIMAL(14,2) NOT NULL DEFAULT 0,
                order_count         INT NOT NULL DEFAULT 0,
                PRIMARY KEY (store_key, calendar_year, month_number)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))
        if not _agg_store_monthly_sales_has_data(conn):
            _rebuild_agg_store_monthly_sales(conn)
        elif has_new and int(max_sales) > int(wm_sales):
            _upsert_agg_store_monthly_sales_from_factsales(conn, int(wm_sales))

    # Rebuild parquet cache and clear in-memory caches
    from modules.sale_profit.service import refresh_sales_profit_cache, clear_all_caches
    clear_all_caches()
    refresh_sales_profit_cache()
    logger.info("Parquet cache and in-memory caches refreshed")


def _agg_store_monthly_sales_has_data(conn) -> bool:
    row = conn.execute(text("SELECT COUNT(*) FROM agg_store_monthly_sales")).scalar()
    return bool(row)


def _rebuild_agg_store_monthly_sales(conn) -> None:
    conn.execute(text("DELETE FROM agg_store_monthly_sales"))
    conn.execute(text("""
        INSERT INTO agg_store_monthly_sales
            (store_key, calendar_year, month_number,
             total_sales_amount, total_sales_quantity, order_count)
        SELECT
            StoreKey, YEAR(DateKey), MONTH(DateKey),
            SUM(total_sales_amount), SUM(total_sales_quantity), COUNT(*)
        FROM summary_daily_sales
        GROUP BY StoreKey, YEAR(DateKey), MONTH(DateKey)
    """))
    logger.info("agg_store_monthly_sales rebuilt (full)")


def _upsert_agg_store_monthly_sales_from_factsales(conn, sales_wm: int) -> None:
    conn.execute(text(f"""
        INSERT INTO agg_store_monthly_sales
            (store_key, calendar_year, month_number,
             total_sales_amount, total_sales_quantity, order_count)
        SELECT
            COALESCE(StoreKey, 0), YEAR(DateKey), MONTH(DateKey),
            SUM(SalesAmount), SUM(SalesQuantity), COUNT(*)
        FROM FactSales
        WHERE SalesKey > {sales_wm}
        GROUP BY COALESCE(StoreKey, 0), YEAR(DateKey), MONTH(DateKey)
        ON DUPLICATE KEY UPDATE
            total_sales_amount   = total_sales_amount   + VALUES(total_sales_amount),
            total_sales_quantity = total_sales_quantity + VALUES(total_sales_quantity),
            order_count          = order_count          + VALUES(order_count)
    """))
    logger.info(f"agg_store_monthly_sales updated (incremental, wm={sales_wm})")


def _refresh_summary_for_purge(table_name: str, start_date: str = None, end_date: str = None) -> None:
    """After purge, rebuild summary_daily_sales for affected date range and refresh cache."""
    if table_name not in ("FactSales", "FactOnlineSales"):
        # Purge on dim tables doesn't affect summary
        return
    engine = get_engine()
    with engine.begin() as conn:
        # Delete affected summary rows for the date range
        conditions = ["1=1"]
        params: Dict[str, Any] = {}
        if start_date:
            conditions.append("DateKey >= :sd")
            params["sd"] = start_date
        if end_date:
            conditions.append("DateKey <= :ed")
            params["ed"] = end_date
        where = " AND ".join(conditions)
        conn.execute(text(f"DELETE FROM summary_daily_sales WHERE {where}"), params)

        # Re-aggregate from the source fact table for the affected range
        date_filter = ""
        if start_date or end_date:
            parts = []
            if start_date:
                parts.append("DATE(DateKey) >= :sd")
            if end_date:
                parts.append("DATE(DateKey) <= :ed")
            date_filter = "WHERE " + " AND ".join(parts)

        conn.execute(text(f"""
            REPLACE INTO summary_daily_sales
                (DateKey, StoreKey, ProductKey, PromotionKey,
                 total_sales_quantity, total_sales_amount,
                 total_return_amount, total_discount_amount, total_cost)
            SELECT
                DATE(DateKey), COALESCE(StoreKey,0), ProductKey,
                COALESCE(PromotionKey,0),
                SUM(SalesQuantity), SUM(SalesAmount),
                SUM(COALESCE(ReturnAmount,0)), SUM(COALESCE(DiscountAmount,0)),
                SUM(COALESCE(TotalCost,0))
            FROM v_total_sales
            {date_filter}
            GROUP BY DATE(DateKey), COALESCE(StoreKey,0), ProductKey, COALESCE(PromotionKey,0)
        """), params)
    logger.info(f"summary_daily_sales rebuilt for purge on {table_name}")
    from modules.sale_profit.service import refresh_sales_profit_cache, clear_all_caches
    clear_all_caches()
    refresh_sales_profit_cache()
    logger.info("Parquet cache refreshed after purge")


logger.info("Data Management startup ready.")


def _parse_db_error(exc: Exception) -> str:
    """Convert raw MySQL/SQLAlchemy exception into a short Vietnamese message."""
    raw = str(exc)
    # Extract MySQL error code from pattern (NNNN, "...") or [NNNN]
    code_match = re.search(r'\((\d{4}),', raw)
    code = int(code_match.group(1)) if code_match else 0

    # Helper: pull quoted column name from message
    def _col(pattern: str) -> str:
        m = re.search(pattern, raw)
        return f" '{m.group(1)}'" if m else ""

    if code == 1265 or code == 1366 or code == 1292:
        col = _col(r"column '([^']+)'")
        return f"Giá trị không hợp lệ cho cột{col} (sai kiểu dữ liệu hoặc chứa ký tự lạ)"
    if code == 1048:
        col = _col(r"Column '([^']+)'")
        return f"Cột{col} không được để trống (NOT NULL)"
    if code == 1062:
        val = _col(r"Duplicate entry '([^']+)'")
        return f"Trùng khóa chính{val} — bản ghi đã tồn tại trong bảng"
    if code == 1406:
        col = _col(r"column '([^']+)'")
        return f"Độ dài dữ liệu vượt quá giới hạn cho cột{col}"
    if code == 1452:
        # FK error — try to extract referenced table
        m = re.search(r'REFERENCES `([^`]+)`', raw)
        ref = f" (tham chiếu bảng '{m.group(1)}')" if m else ""
        return f"Khóa ngoại không hợp lệ{ref} — giá trị không tồn tại trong bảng cha"
    if code == 1054:
        col = _col(r"Unknown column '([^']+)'")
        return f"Cột{col} không tồn tại trong bảng đích"
    if code == 1146:
        tbl = _col(r"Table '[^']*\.([^']+)'")
        return f"Bảng{tbl} không tồn tại trong database"
    # Fallback: first sentence of the error only
    first_line = raw.split('\n')[0][:200]
    return f"Lỗi database: {first_line}"


def _sanitize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Replace NaN with None and coerce dirty numeric strings to proper numbers.

    Handles values like '237.50*', '342.00**' by stripping non-numeric
    trailing characters before attempting numeric conversion.
    """
    for col in df.columns:
        if df[col].dtype == object:
            # Strip whitespace, then try to clean and coerce to numeric
            cleaned = (
                df[col]
                .astype(str)
                .str.strip()
                .str.replace(r"[^\d.\-eE+]", "", regex=True)  # keep digits, dot, sign, exponent
            )
            converted = pd.to_numeric(cleaned, errors="ignore")
            # Only apply numeric conversion if it worked for most non-null values
            if converted.dtype != object:
                df[col] = converted
    return df.where(pd.notna(df), None)


# ── Fact tables whose surrogate PK should be auto-managed ────────────────────
# Maps table_name → single surrogate PK column name.
# These keys have NO business meaning — they are generated IDs only.
FACT_SURROGATE_PKS: Dict[str, str] = {
    "FactSales": "SalesKey",
    "FactOnlineSales": "OnlineSalesKey",
    "FactInventory": "InventoryKey",
}


def _resolve_fact_pk(df: pd.DataFrame, table_name: str, pk_col: str) -> pd.DataFrame:
    """
    Auto-assign surrogate primary key values for Fact table ingestion.

    Rules (applied in order):
      1. PK column absent  → create it, fill every row with new sequential IDs.
      2. PK column present but some values are NULL → fill only the NULL rows.
      3. PK column present and fully populated but some values conflict with
         existing DB rows → reassign only the conflicting rows.

    All new IDs start from  MAX(pk_col) + 1  in the target table.
    """
    engine = get_engine()

    # Current max PK in DB
    try:
        with engine.connect() as conn:
            db_max = conn.execute(
                text(f"SELECT COALESCE(MAX(`{pk_col}`), 0) FROM `{table_name}`")
            ).scalar() or 0
    except Exception:
        db_max = 0

    next_id = int(db_max) + 1

    df = df.copy()

    # ── Case 1: column completely missing ────────────────────────
    if pk_col not in df.columns:
        df.insert(0, pk_col, range(next_id, next_id + len(df)))
        logger.info(
            f"[{table_name}] '{pk_col}' column absent — assigned IDs "
            f"{next_id}…{next_id + len(df) - 1}"
        )
        return df

    # Convert to nullable Int64 so we can detect NaN vs 0
    df[pk_col] = pd.to_numeric(df[pk_col], errors="coerce")

    # ── Case 2: some rows have NULL PK ───────────────────────────
    null_mask = df[pk_col].isnull()
    if null_mask.any():
        null_count = int(null_mask.sum())
        new_ids = list(range(next_id, next_id + null_count))
        df.loc[null_mask, pk_col] = new_ids
        next_id += null_count
        logger.info(f"[{table_name}] Filled {null_count} NULL '{pk_col}' values.")

    # ── Case 3: check for conflicts with existing DB keys ────────
    incoming_ids = df[pk_col].dropna().astype(int).tolist()
    if not incoming_ids:
        return df

    # Fetch existing keys that overlap with incoming IDs (batch query)
    # Use a temp table approach to avoid huge IN() lists
    try:
        with engine.connect() as conn:
            # Load only the PK column fast — no full table scan
            existing_set = set(
                conn.execute(
                    text(
                        f"SELECT `{pk_col}` FROM `{table_name}` "
                        f"WHERE `{pk_col}` IN :ids"
                    ),
                    {"ids": tuple(incoming_ids)},
                ).scalars()
            )
    except Exception:
        existing_set = set()

    if existing_set:
        conflict_mask = df[pk_col].isin(existing_set)
        conflict_count = int(conflict_mask.sum())
        new_ids = list(range(next_id, next_id + conflict_count))
        df.loc[conflict_mask, pk_col] = new_ids
        next_id += conflict_count
        logger.info(
            f"[{table_name}] Reassigned {conflict_count} conflicting '{pk_col}' "
            f"values (were: {sorted(existing_set)[:10]}{'...' if len(existing_set) > 10 else ''})"
        )

    df[pk_col] = df[pk_col].astype(int)
    return df


def _fetch_table_columns(table_name: str) -> List[str]:
    sql = """
    SELECT column_name AS column_name
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = :table_name
    ORDER BY ordinal_position
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text(sql), {"table_name": table_name}).mappings().all()
    return [row["column_name"] for row in rows]


def _bulk_upsert(table_name: str, rows: List[Dict[str, Any]], primary_keys: List[str]) -> int:
    if not rows:
        return 0

    columns = list(rows[0].keys())
    placeholders = ", ".join(f":{col}" for col in columns)
    update_cols = [col for col in columns if col not in primary_keys]
    update_clause = ", ".join(f"{col} = VALUES({col})" for col in update_cols)

    if update_clause:
        sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {update_clause}"
    else:
        sql = f"INSERT IGNORE INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"

    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(text(sql), rows)
    return int(result.rowcount or 0)

def load_schema():
    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_schema(schema_data):
    with open(SCHEMA_FILE, "w", encoding="utf-8") as f:
        json.dump(schema_data, f, ensure_ascii=False, indent=4)

@router.get("/schema")
def get_schemas():
    return load_schema()

@router.post("/schema")
def update_schemas(schema_data: Dict[str, Any]):
    save_schema(schema_data)
    return {"message": "Schema updated successfully"}

@router.get("/template/{table_name}")
def get_template(table_name: str):
    schemas = load_schema()
    if table_name not in schemas:
        raise HTTPException(status_code=404, detail="Table not found in schema")

    table_info = schemas[table_name]
    columns = [col["name"] for col in table_info["columns"]]

    df = pd.DataFrame(columns=columns)

    # Write Excel to memory — no temp file needed, no disk permission issues
    buffer = _io.BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")
    buffer.seek(0)

    headers = {
        "Content-Disposition": f'attachment; filename="Template_{table_name}.xlsx"'
    }
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )

@router.post("/upload")
async def upload_data(table_name: str = Form(...), file: UploadFile = File(...)):
    schemas = load_schema()
    if table_name not in schemas:
        raise HTTPException(status_code=404, detail="Table not found")
        
    schema = schemas[table_name]
    primary_keys = schema.get("primary_keys", [])
    
    contents = await file.read()
    if file.filename.endswith('.csv'):
        new_df = pd.read_csv(io.BytesIO(contents))
    else:
        new_df = pd.read_excel(io.BytesIO(contents))
        
    # Basic validation
    expected_cols = [c["name"] for c in schema["columns"]]
    missing_cols = [c for c in expected_cols if c not in new_df.columns]
    if missing_cols:
        raise HTTPException(status_code=400, detail=f"Missing columns: {missing_cols}")
        
    # Data Quality: Simple NaN check
    null_counts = new_df.isnull().sum().to_dict()
    
    return {
        "message": "File parsed successfully",
        "preview": new_df.head(5).to_dict(orient="records"),
        "null_counts": null_counts,
        "rows": len(new_df)
    }

@router.post("/ingest")
async def ingest_data(table_name: str = Form(...), file: UploadFile = File(...)):
    schemas = load_schema()
    if table_name not in schemas:
        raise HTTPException(status_code=404, detail="Table not found")

    schema = schemas[table_name]
    primary_keys = schema.get("primary_keys", [])

    contents = await file.read()
    if file.filename.endswith('.csv'):
        new_df = pd.read_csv(io.BytesIO(contents))
    else:
        new_df = pd.read_excel(io.BytesIO(contents))

    table_columns = _fetch_table_columns(table_name)
    if not table_columns:
        raise HTTPException(status_code=404, detail=f"MySQL table '{table_name}' not found")

    pk_actions: Dict[str, str] = {}   # summary reported back to caller

    # ── Fact tables: auto-manage surrogate PK, don't block ───────
    if table_name in FACT_SURROGATE_PKS:
        surrogate_pk = FACT_SURROGATE_PKS[table_name]
        before_ids = new_df[surrogate_pk].tolist() if surrogate_pk in new_df.columns else []
        new_df = _resolve_fact_pk(new_df, table_name, surrogate_pk)

        if surrogate_pk not in (before_ids and new_df.columns.tolist()):
            pk_actions[surrogate_pk] = "auto-generated (column was absent)"
        elif new_df[surrogate_pk].isnull().sum() == 0 and any(
            pd.isna(v) for v in before_ids
        ):
            pk_actions[surrogate_pk] = "null values filled with sequential IDs"
        else:
            pk_actions[surrogate_pk] = "conflicts resolved with new sequential IDs"

    else:
        # ── Dim / other tables: validate PK exists and is not null ──
        missing_pks = [pk for pk in primary_keys if pk not in new_df.columns]
        if missing_pks:
            raise HTTPException(
                status_code=400,
                detail=f"Thiếu cột khóa chính: {missing_pks}. Bảng Dim yêu cầu PK do người dùng cung cấp.",
            )
        pk_null_cols = [
            pk for pk in primary_keys
            if pk in new_df.columns and new_df[pk].isnull().any()
        ]
        if pk_null_cols:
            raise HTTPException(
                status_code=400,
                detail=f"Cột khóa chính có giá trị NULL: {pk_null_cols}.",
            )

    # ── Warn about missing non-key columns ───────────────────────
    expected_cols = [c["name"] for c in schema.get("columns", [])]
    missing_non_pk = [
        c for c in expected_cols
        if c not in primary_keys and c not in new_df.columns
    ]
    if missing_non_pk:
        logger.warning(f"[{table_name}] Ingest: cột thiếu (bỏ qua): {missing_non_pk}")

    valid_columns = [col for col in new_df.columns if col in table_columns]
    if not valid_columns:
        raise HTTPException(status_code=400, detail="No valid columns found for target table")

    db_df = _sanitize_df(new_df[valid_columns].copy())
    if primary_keys:
        primary_in_df = [pk for pk in primary_keys if pk in db_df.columns]
        if primary_in_df:
            db_df = db_df.drop_duplicates(subset=primary_in_df, keep="last")

    rows = db_df.to_dict(orient="records")
    affected_rows = _bulk_upsert(table_name, rows, primary_keys)

    return {
        "message": f"Ingested into MySQL table '{table_name}'. Affected rows: {affected_rows}",
        "pk_auto_actions": pk_actions,
        "missing_columns_skipped": missing_non_pk if missing_non_pk else [],
    }

ALLOWED_TABLES = {
    "FactSales", "FactOnlineSales", "FactInventory",
    "DimProduct", "DimStore", "DimEmployee", "DimChannel",
    "DimPromotion", "DimCurrency", "DimCustomer",
    "DimDate", "DimGeography", "DimProductCategory",
    "DimProductSubcategory", "summary_daily_sales",
}

# Only these tables support DATE_RANGE purge
PURGEABLE_TABLES = {"FactSales", "FactOnlineSales"}


def _validate_table_name(table_name: str) -> str:
    """Whitelist table names to prevent SQL injection."""
    if table_name not in ALLOWED_TABLES:
        raise HTTPException(status_code=400, detail=f"Table '{table_name}' is not allowed")
    return table_name


class PurgeRequest(BaseModel):
    table_name: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    category: Optional[str] = None

@router.post("/purge")
def purge_data(request: PurgeRequest):
    schemas = load_schema()
    table_name = _validate_table_name(request.table_name)
    if table_name not in schemas:
        raise HTTPException(status_code=404, detail="Table schema not found")
        
    if table_name not in PURGEABLE_TABLES:
        raise HTTPException(status_code=400, detail=f"Table '{table_name}' does not support purge. Only FactSales and FactOnlineSales are allowed.")

    schema = schemas[table_name]
    backup_table = f"backup_{table_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    conditions = ["1=1"]
    params: Dict[str, Any] = {}

    if not request.start_date or not request.end_date:
        raise HTTPException(status_code=400, detail="start_date and end_date are required for DATE_RANGE purge.")

    conditions.append("DateKey >= :start_date")
    params["start_date"] = request.start_date
    conditions.append("DateKey <= :end_date")
    params["end_date"] = request.end_date

    where_clause = " AND ".join(conditions)
    engine = get_engine()

    with engine.begin() as conn:
        total_before = conn.execute(text(f"SELECT COUNT(*) AS c FROM {table_name}")).scalar() or 0

        conn.execute(text(f"CREATE TABLE {backup_table} AS SELECT * FROM {table_name} WHERE {where_clause}"), params)
        conn.execute(text(f"DELETE FROM {table_name} WHERE {where_clause}"), params)

        total_after = conn.execute(text(f"SELECT COUNT(*) AS c FROM {table_name}")).scalar() or 0

    deleted = int(total_before - total_after)
    # Refresh summary + cache in background if fact table data changed
    if deleted > 0 and table_name in ("FactSales", "FactOnlineSales"):
        threading.Thread(
            target=_refresh_summary_for_purge,
            args=(table_name, request.start_date, request.end_date),
            daemon=True,
        ).start()

    return {
        "message": "Data purged successfully",
        "backup_table": backup_table,
        "deleted_rows": deleted,
        "remaining_rows": int(total_after),
    }

@router.get("/categories/{table_name}")
def get_categories(table_name: str):
    table_name = _validate_table_name(table_name)
    engine = get_engine()
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT DISTINCT BrandName FROM {table_name} WHERE BrandName IS NOT NULL ORDER BY BrandName")
            ).mappings().all()
        return [row["BrandName"] for row in rows]
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════
# Data Warehouse Health & Overview
# ═══════════════════════════════════════════════════════════════

@router.get("/dw-health")
def dw_health():
    """Return DW table row counts, aggregate table status, and last-updated timestamps."""
    engine = get_engine()
    with engine.connect() as conn:
        tables_sql = text("""
            SELECT table_name AS table_name, table_rows AS table_rows, update_time AS update_time
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
            ORDER BY table_name
        """)
        rows = conn.execute(tables_sql).mappings().all()

    fact_tables = []
    dim_tables = []
    agg_tables = []
    other_tables = []

    for r in rows:
        name = r["table_name"]
        lower_name = name.lower()
        entry = {
            "table_name": name,
            "row_count": int(r["table_rows"] or 0),
            "last_updated": r["update_time"].isoformat() if r["update_time"] else None,
        }
        if lower_name.startswith("fact") or lower_name == "summary_daily_sales":
            fact_tables.append(entry)
        elif lower_name.startswith("dim"):
            dim_tables.append(entry)
        elif lower_name.startswith("agg_") or lower_name.startswith("v_") or lower_name == "customer_segments":
            agg_tables.append(entry)
        else:
            other_tables.append(entry)

    return serialize_payload({
        "status": "success",
        "fact_tables": fact_tables,
        "dim_tables": dim_tables,
        "agg_tables": agg_tables,
        "other_tables": other_tables,
        "total_tables": len(rows),
    })


# ═══════════════════════════════════════════════════════════════
# Data Source Connections
# ═══════════════════════════════════════════════════════════════

_DATA_SOURCES_FILE = os.path.join(os.path.dirname(__file__), "data_sources.json")


def _load_data_sources() -> List[Dict[str, Any]]:
    if not os.path.exists(_DATA_SOURCES_FILE):
        _save_data_sources([])
        return []
    with open(_DATA_SOURCES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_data_sources(sources: List[Dict[str, Any]]):
    with open(_DATA_SOURCES_FILE, "w", encoding="utf-8") as f:
        json.dump(sources, f, ensure_ascii=False, indent=2, default=str)


@router.get("/data-sources")
def list_data_sources():
    return serialize_payload(_load_data_sources())


class DataSourceCreate(BaseModel):
    name: str
    type: str = "mysql"
    host: str = "127.0.0.1"
    port: int = 3306
    database: str
    user: str = "root"
    password: Optional[str] = None


@router.post("/data-sources")
def add_data_source(body: DataSourceCreate):
    sources = _load_data_sources()
    new_source = {
        "id": f"src_{int(time.time())}",
        "name": body.name,
        "type": body.type,
        "host": body.host,
        "port": body.port,
        "database": body.database,
        "user": body.user,
        "status": "pending",
        "last_sync": None,
        "created_at": datetime.now().isoformat(),
    }
    sources.append(new_source)
    _save_data_sources(sources)
    return serialize_payload({"status": "created", "source": new_source})


@router.post("/data-sources/{source_id}/test")
def test_data_source(source_id: str, password: Optional[str] = None):
    """Test if a data source connection is working."""
    sources = _load_data_sources()
    source = next((s for s in sources if s["id"] == source_id), None)
    if not source:
        raise HTTPException(status_code=404, detail="Data source not found")

    try:
        from sqlalchemy import create_engine as ce
        pwd = password or DW_PASSWORD or "12345"
        url = f"mysql+pymysql://{source['user']}:{pwd}@{source['host']}:{source['port']}/{source['database']}?charset=utf8mb4"
        eng = ce(url, pool_pre_ping=True)
        with eng.connect() as conn:
            tables = conn.execute(text(
                "SELECT table_name AS table_name, table_rows AS table_rows FROM information_schema.tables WHERE table_schema = DATABASE()"
            )).mappings().all()
        eng.dispose()

        source["status"] = "connected"
        _save_data_sources(sources)

        return serialize_payload({
            "status": "connected",
            "tables": [{"name": t["table_name"], "rows": int(t["table_rows"] or 0)} for t in tables],
        })
    except Exception as e:
        source["status"] = "error"
        _save_data_sources(sources)
        return serialize_payload({"status": "error", "message": str(e)})


# ═══════════════════════════════════════════════════════════════
# CSV Upload → Star Schema Transform → Load
# ═══════════════════════════════════════════════════════════════

@router.post("/csv-upload-preview")
async def csv_upload_preview(file: UploadFile = File(...)):
    """Parse uploaded CSV/Excel and return preview + column mapping suggestions."""
    contents = await file.read()
    if file.filename and file.filename.endswith('.csv'):
        df = pd.read_csv(io.BytesIO(contents))
    else:
        df = pd.read_excel(io.BytesIO(contents))

    if df.empty:
        raise HTTPException(status_code=400, detail="File is empty")

    # Get DW table columns for mapping suggestions
    engine = get_engine()
    dw_tables = {}
    with engine.connect() as conn:
        target_tables = ["FactSales", "FactOnlineSales", "DimProduct", "DimCustomer", "DimStore"]
        for tbl in target_tables:
            cols = conn.execute(text(
                "SELECT column_name AS column_name FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = :t ORDER BY ordinal_position"
            ), {"t": tbl}).mappings().all()
            dw_tables[tbl] = [c["column_name"] for c in cols]

    return serialize_payload({
        "filename": file.filename,
        "rows": len(df),
        "columns": list(df.columns),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "preview": df.head(10).where(pd.notna(df.head(10)), None).to_dict(orient="records"),
        "null_counts": df.isnull().sum().to_dict(),
        "dw_tables": dw_tables,
    })


@router.post("/csv-transform-load")
async def csv_transform_load(
    target_table: str = Form(...),
    column_mapping: str = Form(...),
    file: UploadFile = File(...),
):
    """Transform CSV data using column mapping and load into DW target table."""

    # ── Security: whitelist table name ───────────────────────────
    target_table = _validate_table_name(target_table)

    contents = await file.read()
    if file.filename and file.filename.endswith('.csv'):
        df = pd.read_csv(io.BytesIO(contents))
    else:
        df = pd.read_excel(io.BytesIO(contents))

    # Parse column mapping: JSON string {"csv_col": "dw_col", ...}
    try:
        mapping = json.loads(column_mapping)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid column_mapping JSON")

    # Rename columns according to mapping
    df_mapped = df.rename(columns=mapping)
    dw_cols = list(mapping.values())
    df_mapped = df_mapped[[c for c in dw_cols if c in df_mapped.columns]]

    if df_mapped.empty:
        raise HTTPException(status_code=400, detail="No valid columns after mapping")

    # Get primary keys from schema
    schemas = load_schema()
    primary_keys = schemas.get(target_table, {}).get("primary_keys", [])

    # ── Fact tables: auto-resolve surrogate PK conflicts ─────────
    if target_table in FACT_SURROGATE_PKS:
        surrogate_pk = FACT_SURROGATE_PKS[target_table]
        df_mapped = _resolve_fact_pk(df_mapped, target_table, surrogate_pk)

    # Sanitize + dedup
    df_mapped = _sanitize_df(df_mapped)
    if primary_keys:
        pk_in_df = [pk for pk in primary_keys if pk in df_mapped.columns]
        if pk_in_df:
            df_mapped = df_mapped.drop_duplicates(subset=pk_in_df, keep="last")

    rows = df_mapped.to_dict(orient="records")

    # ── Wrap DB write so errors return 400 with detail, not 500 ──
    try:
        affected = _bulk_upsert(target_table, rows, primary_keys)
    except Exception as exc:
        logger.error(f"[csv-transform-load] DB error for {target_table}: {exc}")
        raise HTTPException(
            status_code=400,
            detail=f"Bảng '{target_table}': {_parse_db_error(exc)}"
        )

    return serialize_payload({
        "status": "success",
        "target_table": target_table,
        "rows_processed": len(rows),
        "rows_affected": affected,
        "columns_mapped": list(mapping.keys()),
    })


# ═══════════════════════════════════════════════════════════════
# ETL Pipeline Control
# ═══════════════════════════════════════════════════════════════

_ETL_STATUS: Dict[str, Any] = {
    "running": False,
    "last_run": None,
    "last_status": "idle",
    "last_error": None,
    "last_duration_seconds": None,
    "tables_built": [],
}


@router.get("/etl/status")
def etl_status():
    return serialize_payload(_ETL_STATUS)


@router.post("/etl/run")
def etl_run_trigger():
    """Trigger ETL pipeline in background."""
    if _ETL_STATUS["running"]:
        return serialize_payload({"status": "already_running", "message": "ETL pipeline is already running."})

    def _run_etl():
        _ETL_STATUS["running"] = True
        _ETL_STATUS["last_status"] = "running"
        _ETL_STATUS["last_error"] = None
        _ETL_STATUS["tables_built"] = []
        start = time.time()
        try:
            # 1. Run aggregate ETL (non-critical – errors are logged but don't block)
            try:
                from migrations.etl_pipeline import run_etl
                run_etl()
                _ETL_STATUS["tables_built"] = [
                    "agg_inventory_metrics", "agg_product_performance",
                    "agg_customer_rfm", "agg_kpi_summary", "agg_store_monthly_costs",
                ]
            except Exception as etl_err:
                logger.warning(f"Aggregate ETL had errors (non-critical): {etl_err}")

            # 2. Always refresh summary_daily_sales + parquet cache
            _refresh_summary_and_cache()
            _ETL_STATUS["last_status"] = "success"

        except Exception as e:
            logger.error(f"ETL failed: {e}")
            _ETL_STATUS["last_status"] = "error"
            _ETL_STATUS["last_error"] = str(e)
        finally:
            _ETL_STATUS["running"] = False
            _ETL_STATUS["last_run"] = datetime.now().isoformat()
            _ETL_STATUS["last_duration_seconds"] = round(time.time() - start, 1)

    threading.Thread(target=_run_etl, daemon=True).start()
    return serialize_payload({"status": "started", "message": "ETL pipeline started in background."})


@router.post("/etl/fast-refresh")
def etl_fast_refresh():
    """Đồng bộ fast refresh — hoàn tất trong <3 giây.

    Các bước đồng bộ (blocking, chỉ đọc rows mới kể từ watermark):
      1. Cập nhật summary_daily_sales (incremental, watermarked)
      2. Cập nhật agg_kpi_summary (incremental delta, không scan toàn bộ)
      3. Xóa TTL cache in-memory

    Các bước không đồng bộ (background, không block response):
      4. Rebuild parquet cache
      5. Realtime snapshot poll
    """
    import time as _time
    t0 = _time.perf_counter()
    try:
        engine = get_engine()

        # ── Bước 1: Incremental update summary_daily_sales ─────────
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS _summary_watermarks (
                    source_table VARCHAR(64) PRIMARY KEY,
                    last_key BIGINT NOT NULL DEFAULT 0
                ) ENGINE=InnoDB
            """))
            wm_sales = conn.execute(text(
                "SELECT COALESCE((SELECT last_key FROM _summary_watermarks WHERE source_table='FactSales'),0)"
            )).scalar() or 0
            wm_online = conn.execute(text(
                "SELECT COALESCE((SELECT last_key FROM _summary_watermarks WHERE source_table='FactOnlineSales'),0)"
            )).scalar() or 0
            max_sales  = conn.execute(text("SELECT COALESCE(MAX(SalesKey),0) FROM FactSales")).scalar() or 0
            max_online = conn.execute(text("SELECT COALESCE(MAX(OnlineSalesKey),0) FROM FactOnlineSales")).scalar() or 0

            # Delta stats from new FactSales rows (chỉ rows mới → rất nhanh)
            delta_sales = conn.execute(text("""
                SELECT
                    COUNT(*)                      AS delta_cnt,
                    COALESCE(SUM(SalesAmount), 0) AS delta_amt,
                    COALESCE(SUM(TotalCost), 0)   AS delta_cost,
                    COALESCE(SUM(SalesQuantity),0) AS delta_qty
                FROM FactSales WHERE SalesKey > :wm
            """), {"wm": int(wm_sales)}).mappings().first()

            # Delta stats from new FactOnlineSales rows
            delta_online = conn.execute(text("""
                SELECT
                    COUNT(*)                      AS delta_cnt,
                    COALESCE(SUM(SalesAmount), 0) AS delta_amt,
                    COALESCE(SUM(TotalCost), 0)   AS delta_cost,
                    COALESCE(SUM(SalesQuantity),0) AS delta_qty
                FROM FactOnlineSales WHERE OnlineSalesKey > :wm
            """), {"wm": int(wm_online)}).mappings().first()

            if int(max_sales) > int(wm_sales):
                conn.execute(text("""
                    REPLACE INTO summary_daily_sales
                        (DateKey, StoreKey, ProductKey, PromotionKey,
                         total_sales_quantity, total_sales_amount,
                         total_return_amount, total_discount_amount, total_cost)
                    SELECT DATE(DateKey), COALESCE(StoreKey,0), ProductKey, COALESCE(PromotionKey,0),
                           SUM(SalesQuantity), SUM(SalesAmount),
                           SUM(COALESCE(ReturnAmount,0)), SUM(COALESCE(DiscountAmount,0)),
                           SUM(COALESCE(TotalCost,0))
                    FROM FactSales WHERE SalesKey > :wm
                    GROUP BY DATE(DateKey), COALESCE(StoreKey,0), ProductKey, COALESCE(PromotionKey,0)
                """), {"wm": int(wm_sales)})
                conn.execute(text("""
                    INSERT INTO _summary_watermarks (source_table, last_key) VALUES ('FactSales', :v)
                    ON DUPLICATE KEY UPDATE last_key = :v
                """), {"v": int(max_sales)})

            if int(max_online) > int(wm_online):
                conn.execute(text("""
                    REPLACE INTO summary_daily_sales
                        (DateKey, StoreKey, ProductKey, PromotionKey,
                         total_sales_quantity, total_sales_amount,
                         total_return_amount, total_discount_amount, total_cost)
                    SELECT DATE(DateKey), COALESCE(StoreKey,0), ProductKey, COALESCE(PromotionKey,0),
                           SUM(SalesQuantity), SUM(SalesAmount),
                           SUM(COALESCE(ReturnAmount,0)), SUM(COALESCE(DiscountAmount,0)),
                           SUM(COALESCE(TotalCost,0))
                    FROM FactOnlineSales WHERE OnlineSalesKey > :wm
                    GROUP BY DATE(DateKey), COALESCE(StoreKey,0), ProductKey, COALESCE(PromotionKey,0)
                """), {"wm": int(wm_online)})
                conn.execute(text("""
                    INSERT INTO _summary_watermarks (source_table, last_key) VALUES ('FactOnlineSales', :v)
                    ON DUPLICATE KEY UPDATE last_key = :v
                """), {"v": int(max_online)})

        # ── Bước 2: Incremental update agg_kpi_summary ─────────────
        # Dùng delta từ rows mới thay vì scan toàn bộ v_total_sales
        total_delta_cnt  = int(delta_sales["delta_cnt"])  + int(delta_online["delta_cnt"])
        total_delta_amt  = float(delta_sales["delta_amt"]) + float(delta_online["delta_amt"])
        total_delta_cost = float(delta_sales["delta_cost"]) + float(delta_online["delta_cost"])
        total_delta_qty  = float(delta_sales["delta_qty"])  + float(delta_online["delta_qty"])

        if total_delta_cnt > 0:
            with engine.connect() as conn:
                # Đọc giá trị hiện tại từ agg_kpi_summary
                existing = {
                    row["kpi_key"]: float(row["kpi_value"])
                    for row in conn.execute(text(
                        "SELECT kpi_key, kpi_value FROM agg_kpi_summary"
                    )).mappings().all()
                }
            new_cnt  = existing.get("total_transactions", 0) + total_delta_cnt
            new_amt  = existing.get("total_revenue", 0)      + total_delta_amt
            new_cost = (existing.get("total_revenue", 0) * (1 - existing.get("gross_margin", 0) / 100)
                        if existing.get("total_revenue", 0) > 0 else 0) + total_delta_cost
            new_qty  = existing.get("avg_basket_size", 0) * existing.get("total_transactions", 1) + total_delta_qty
            with engine.begin() as conn:
                conn.execute(text("""
                    REPLACE INTO agg_kpi_summary (kpi_key, kpi_label, kpi_value, kpi_unit, period)
                    VALUES
                      ('total_revenue',        'Total Revenue',             :rev,    'USD',   'ALL'),
                      ('total_transactions',   'Total Transactions',        :cnt,    'count', 'ALL'),
                      ('avg_transaction_value','Average Transaction Value', :avg_rv, 'USD',   'ALL'),
                      ('avg_basket_size',      'Average Basket Size',       :avg_bs, 'units', 'ALL'),
                      ('gross_margin',         'Gross Profit Margin',       :margin, 'pct',   'ALL')
                """), {
                    "rev":    new_amt,
                    "cnt":    new_cnt,
                    "avg_rv": new_amt / new_cnt if new_cnt else 0,
                    "avg_bs": new_qty / new_cnt if new_cnt else 0,
                    "margin": (new_amt - new_cost) / new_amt * 100 if new_amt else 0,
                })

        # ── Bước 3: Clear in-memory TTL cache ──────────────────────
        from modules.sale_profit.service import clear_all_caches, refresh_sales_profit_cache
        clear_all_caches()

        # ── Bước 4 & 5: Background tasks (không block response) ────
        threading.Thread(target=refresh_sales_profit_cache, daemon=True).start()
        try:
            from modules.realtime.router import _poll_dw_once
            threading.Thread(target=_poll_dw_once, daemon=True).start()
        except Exception:
            pass

        elapsed = round((_time.perf_counter() - t0) * 1000)
        logger.info("Fast refresh completed in %d ms", elapsed)
        return serialize_payload({"status": "ok", "elapsed_ms": elapsed})

    except Exception as exc:
        logger.error("Fast refresh failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/etl/refresh-segments")
def etl_refresh_segments():
    """Check customer_segments table health."""
    try:
        from item_trends.it_cache import ensure_segments_table_from_csv
        result = ensure_segments_table_from_csv()
        return serialize_payload({"status": "success", "rows": result.get("rows", 0)})
    except Exception as e:
        return serialize_payload({"status": "error", "message": str(e)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("data_management.main:app", host=API_HOST, port=API_PORT, reload=True)


