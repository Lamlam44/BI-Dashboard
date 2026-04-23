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

# ── Ingest background-refresh progress tracker ────────────────
# Updated by _post_ingest_sync() / _heavy_bg() so the frontend
# can poll /data/ingest-refresh-status and show a live progress bar.
_INGEST_REFRESH_STATUS: Dict[str, Any] = {
    "running": False,
    "percent": 0,
    "step": "idle",
    "last_completed": None,
    "error": None,
}
_INGEST_STATUS_LOCK = threading.Lock()


def _update_refresh_status(
    percent: int,
    step: str,
    running: bool = True,
    error: Optional[str] = None,
) -> None:
    with _INGEST_STATUS_LOCK:
        _INGEST_REFRESH_STATUS["running"] = running
        _INGEST_REFRESH_STATUS["percent"] = percent
        _INGEST_REFRESH_STATUS["step"] = step
        _INGEST_REFRESH_STATUS["error"] = error
        if not running:
            _INGEST_REFRESH_STATUS["last_completed"] = datetime.utcnow().isoformat()


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
                    INSERT INTO summary_daily_sales
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
                    ON DUPLICATE KEY UPDATE
                        total_sales_quantity  = total_sales_quantity  + VALUES(total_sales_quantity),
                        total_sales_amount    = total_sales_amount    + VALUES(total_sales_amount),
                        total_return_amount   = total_return_amount   + VALUES(total_return_amount),
                        total_discount_amount = total_discount_amount + VALUES(total_discount_amount),
                        total_cost            = total_cost            + VALUES(total_cost)
                """), {"wm": int(wm_sales)})
                logger.info(f"summary_daily_sales: refreshed FactSales rows > {wm_sales}")

            # Incrementally aggregate only new rows from FactOnlineSales
            if int(max_online) > int(wm_online):
                conn.execute(text("""
                    INSERT INTO summary_daily_sales
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
                    ON DUPLICATE KEY UPDATE
                        total_sales_quantity  = total_sales_quantity  + VALUES(total_sales_quantity),
                        total_sales_amount    = total_sales_amount    + VALUES(total_sales_amount),
                        total_return_amount   = total_return_amount   + VALUES(total_return_amount),
                        total_discount_amount = total_discount_amount + VALUES(total_discount_amount),
                        total_cost            = total_cost            + VALUES(total_cost)
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
                total_discount_amount DECIMAL(18,2) NOT NULL DEFAULT 0,
                order_count         INT NOT NULL DEFAULT 0,
                PRIMARY KEY (store_key, calendar_year, month_number)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))
        # Add total_discount_amount column to existing tables that pre-date this change
        try:
            conn.execute(text(
                "ALTER TABLE agg_store_monthly_sales "
                "ADD COLUMN total_discount_amount DECIMAL(18,2) NOT NULL DEFAULT 0"
            ))
        except Exception:
            pass  # column already exists
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
             total_sales_amount, total_sales_quantity, total_discount_amount, order_count)
        SELECT
            StoreKey, YEAR(DateKey), MONTH(DateKey),
            SUM(total_sales_amount), SUM(total_sales_quantity),
            SUM(COALESCE(total_discount_amount, 0)), COUNT(*)
        FROM summary_daily_sales
        GROUP BY StoreKey, YEAR(DateKey), MONTH(DateKey)
    """))
    logger.info("agg_store_monthly_sales rebuilt (full)")


def _upsert_agg_store_monthly_sales_from_factsales(conn, sales_wm: int) -> None:
    conn.execute(text(f"""
        INSERT INTO agg_store_monthly_sales
            (store_key, calendar_year, month_number,
             total_sales_amount, total_sales_quantity, total_discount_amount, order_count)
        SELECT
            COALESCE(StoreKey, 0), YEAR(DateKey), MONTH(DateKey),
            SUM(SalesAmount), SUM(SalesQuantity),
            SUM(COALESCE(DiscountAmount, 0)), COUNT(*)
        FROM FactSales
        WHERE SalesKey > {sales_wm}
        GROUP BY COALESCE(StoreKey, 0), YEAR(DateKey), MONTH(DateKey)
        ON DUPLICATE KEY UPDATE
            total_sales_amount    = total_sales_amount    + VALUES(total_sales_amount),
            total_sales_quantity  = total_sales_quantity  + VALUES(total_sales_quantity),
            total_discount_amount = total_discount_amount + VALUES(total_discount_amount),
            order_count           = order_count           + VALUES(order_count)
    """))
    logger.info(f"agg_store_monthly_sales updated (incremental, wm={sales_wm})")


# ── Startup migration: ensure total_discount_amount column exists ────────────
# Runs at module import time so all warmup queries (including employee_performance)
# can reference the column immediately.
try:
    _startup_engine = get_engine()
    with _startup_engine.begin() as _conn:
        _conn.execute(text(
            "ALTER TABLE agg_store_monthly_sales "
            "ADD COLUMN total_discount_amount DECIMAL(18,2) NOT NULL DEFAULT 0"
        ))
    logger.info("agg_store_monthly_sales: total_discount_amount column added")
except Exception:
    pass  # column already exists or table not yet created — both are fine


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
    "FactSales":       "SalesKey",
    "FactOnlineSales": "OnlineSalesKey",
    "FactInventory":   "InventoryKey",
    "FactExchangeRate": "ExchangeRateKey",
    "FactSalesQuota":  "SalesQuotaKey",
}

# ── Dimension tables: INSERT-only, skip duplicates by PK ─────────────────────
DIM_TABLE_PKS: Dict[str, str] = {
    "DimProduct":            "ProductKey",
    "DimStore":              "StoreKey",
    "DimEmployee":           "EmployeeKey",
    "DimCustomer":           "CustomerKey",
    "DimChannel":            "ChannelKey",
    "DimPromotion":          "PromotionKey",
    "DimCurrency":           "CurrencyKey",
    "DimGeography":          "GeographyKey",
    "DimProductCategory":    "ProductCategoryKey",
    "DimProductSubcategory": "ProductSubcategoryKey",
    "DimDate":               "DateKey",
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

def _detect_table_from_columns(columns: list) -> Optional[str]:
    """Auto-detect target table by matching uploaded column names against schema definitions.

    Returns the best-matching table name, or None if no confident match is found.
    A match is confident when all required (non-nullable, non-PK) columns of a table
    are present in the uploaded file.
    """
    schemas = load_schema()
    upload_cols = {c.lower() for c in columns}
    best_table: Optional[str] = None
    best_score = 0
    for table, info in schemas.items():
        table_cols = {c["name"].lower() for c in info.get("columns", [])}
        required = {
            c["name"].lower() for c in info.get("columns", [])
            if not c.get("nullable", True) and c["name"] not in info.get("primary_keys", [])
        }
        if not required:
            required = table_cols
        matched = required & upload_cols
        if matched == required and len(matched) > best_score:
            best_score = len(matched)
            best_table = table
    return best_table


@router.post("/upload")
async def upload_data(
    file: UploadFile = File(...),
    table_name: Optional[str] = Form(None),
):
    schemas = load_schema()

    contents = await file.read()
    if file.filename.endswith('.csv'):
        new_df = pd.read_csv(io.BytesIO(contents))
    else:
        new_df = pd.read_excel(io.BytesIO(contents))

    # Auto-detect table if not provided by client
    detected_table = _detect_table_from_columns(list(new_df.columns))
    resolved_table = table_name or detected_table

    if resolved_table and resolved_table not in schemas:
        resolved_table = None

    schema = schemas.get(resolved_table, {}) if resolved_table else {}
    primary_keys = schema.get("primary_keys", [])

    # Basic validation only when table is known
    missing_cols: list = []
    if schema:
        expected_cols = [c["name"] for c in schema.get("columns", [])]
        missing_cols = [c for c in expected_cols if c not in new_df.columns]

    # Data Quality: Simple NaN check
    null_counts = new_df.isnull().sum().to_dict()

    return {
        "message": "File parsed successfully",
        "preview": new_df.head(5).to_dict(orient="records"),
        "null_counts": null_counts,
        "rows": len(new_df),
        "suggested_table": resolved_table,
        "auto_detected": table_name is None and resolved_table is not None,
        "missing_columns": missing_cols,
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

    elif table_name in DIM_TABLE_PKS:
        # ── DIM tables: INSERT-only, skip if PK already exists ───
        pk_col = DIM_TABLE_PKS[table_name]
        if pk_col not in new_df.columns:
            raise HTTPException(
                status_code=400,
                detail=f"Thiếu cột khóa chính '{pk_col}'. Bảng DIM yêu cầu PK do người dùng cung cấp.",
            )
        # PK null rows are rejected
        if new_df[pk_col].isnull().any():
            raise HTTPException(
                status_code=400,
                detail=f"Cột khóa chính '{pk_col}' có giá trị NULL.",
            )

    else:
        # ── Other tables: validate PKs ─────────────────────────
        missing_pks = [pk for pk in primary_keys if pk not in new_df.columns]
        if missing_pks:
            raise HTTPException(
                status_code=400,
                detail=f"Thiếu cột khóa chính: {missing_pks}.",
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

    # ── DIM tables: INSERT-only with duplicate-skip reporting ────
    if table_name in DIM_TABLE_PKS:
        pk_col = DIM_TABLE_PKS[table_name]
        dim_result = _dim_insert_skip_duplicates(table_name, pk_col, rows)
        _post_ingest_sync()
        return {
            "message": (
                f"Ingest DIM '{table_name}': "
                f"{dim_result['inserted']} dòng được thêm mới, "
                f"{len(dim_result['skipped_ids'])} dòng bỏ qua (PK đã tồn tại)."
            ),
            "rows_inserted": dim_result["inserted"],
            "skipped_duplicate_ids": dim_result["skipped_ids"],
            "pk_auto_actions": {},
            "missing_columns_skipped": missing_non_pk if missing_non_pk else [],
        }

    # ── FACT and other tables: UPSERT ────────────────────────────
    affected_rows = _bulk_upsert(table_name, rows, primary_keys)
    _post_ingest_sync()
    return {
        "message": f"Ingested into MySQL table '{table_name}'. Affected rows: {affected_rows}",
        "pk_auto_actions": pk_actions,
        "missing_columns_skipped": missing_non_pk if missing_non_pk else [],
    }

ALLOWED_TABLES = (
    set(FACT_SURROGATE_PKS.keys()) | set(DIM_TABLE_PKS.keys()) | {"summary_daily_sales"}
)


def _validate_table_name(table_name: str) -> str:
    """Whitelist table names to prevent SQL injection."""
    if table_name not in ALLOWED_TABLES:
        raise HTTPException(status_code=400, detail=f"Table '{table_name}' is not allowed")
    return table_name

def _dim_insert_skip_duplicates(
    table_name: str, pk_col: str, rows: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Insert DIM rows, skipping any whose pk_col already exists in DB.
    Returns dict: {inserted, skipped_ids}.
    """
    if not rows:
        return {"inserted": 0, "skipped_ids": []}

    engine = get_engine()

    # Normalize PK values — pandas may produce floats like 1001.0
    def _norm(v):
        if v is None:
            return None
        try:
            return int(float(v))
        except (ValueError, TypeError):
            return v

    incoming_pks = [_norm(r.get(pk_col)) for r in rows]
    valid_pks = [p for p in incoming_pks if p is not None]

    existing_set: set = set()
    if valid_pks:
        chunk_size = 500
        try:
            with engine.connect() as conn:
                for i in range(0, len(valid_pks), chunk_size):
                    chunk = valid_pks[i: i + chunk_size]
                    existing_set.update(
                        int(v) for v in conn.execute(
                            text(f"SELECT `{pk_col}` FROM `{table_name}` WHERE `{pk_col}` IN :ids"),
                            {"ids": tuple(chunk)},
                        ).scalars()
                    )
        except Exception as ex:
            logger.warning("[%s] could not fetch existing PKs: %s", table_name, ex)

    to_insert: List[Dict[str, Any]] = []
    skipped_ids: List[Any] = []
    for row, pk_val in zip(rows, incoming_pks):
        if pk_val is not None and pk_val in existing_set:
            skipped_ids.append(pk_val)
        else:
            to_insert.append(row)

    inserted = 0
    if to_insert:
        columns = list(to_insert[0].keys())
        col_str = ", ".join(f"`{c}`" for c in columns)
        place_str = ", ".join(f":{c}" for c in columns)
        sql = f"INSERT IGNORE INTO `{table_name}` ({col_str}) VALUES ({place_str})"
        with engine.begin() as conn:
            result = conn.execute(text(sql), to_insert)
            inserted = max(0, int(result.rowcount or len(to_insert)))

    return {"inserted": inserted, "skipped_ids": skipped_ids}


def _post_ingest_sync() -> None:
    """Synchronous post-ingest refresh — runs FAST operations in the request thread
    so the response always reflects a consistent DW state, then offloads heavy
    parquet / agg-table rebuilds to a background thread.

    Synchronous (fast, < 5 s on local MySQL):
      1. Incrementally update summary_daily_sales from new DW rows (watermarked).
      2. Incrementally update agg_store_monthly_sales.
      3. Delta-update agg_kpi_summary (no full v_total_sales scan).
      4. Clear all in-memory TTL caches (sale_profit, employee_perf, analytics).

    All work runs in a background daemon thread so the HTTP response is never
    delayed. Progress is tracked via _INGEST_REFRESH_STATUS and polled by
    the frontend via GET /data/ingest-refresh-status.

    Steps (all in background):
      1. Incrementally update summary_daily_sales from new DW rows (watermarked).
      2. Incrementally update agg_store_monthly_sales.
      3. Delta-update agg_kpi_summary (no full v_total_sales scan).
      4. Clear all in-memory TTL caches.
      5. Rebuild sale_profit parquet cache from summary_daily_sales.
      6. Incremental update agg_inventory_metrics, agg_product_performance,
         agg_customer_rfm, agg_store_monthly_costs, agg_channel_summary via
         run_etl() watermark logic.
      7. Refresh item_trends customer segments cache.
      8. Rebuild demand forecasting parquet cache (daily_sales_snapshot + abc_xyz).
      9. Trigger realtime SSE snapshot refresh.
    """
    _update_refresh_status(0, "Bắt đầu cập nhật sau khi nạp dữ liệu...")

    def _heavy_bg() -> None:  # noqa: C901
        import time as _t
        t0 = _t.perf_counter()
        engine = get_engine()
        new_sales = False
        new_online = False
        wm_sales: int = 0
        wm_online: int = 0

        # ── Step 1: Incremental summary_daily_sales ─────────────
        _update_refresh_status(10, "Đang cập nhật bảng doanh số ngày...")
        try:
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

                new_sales  = int(max_sales)  > int(wm_sales)
                new_online = int(max_online) > int(wm_online)

                if new_sales:
                    conn.execute(text("""
                        INSERT INTO summary_daily_sales
                            (DateKey, StoreKey, ProductKey, PromotionKey,
                             total_sales_quantity, total_sales_amount,
                             total_return_amount, total_discount_amount, total_cost)
                        SELECT DATE(DateKey), COALESCE(StoreKey,0), ProductKey, COALESCE(PromotionKey,0),
                               SUM(SalesQuantity), SUM(SalesAmount),
                               SUM(COALESCE(ReturnAmount,0)), SUM(COALESCE(DiscountAmount,0)),
                               SUM(COALESCE(TotalCost,0))
                        FROM FactSales WHERE SalesKey > :wm
                        GROUP BY DATE(DateKey), COALESCE(StoreKey,0), ProductKey, COALESCE(PromotionKey,0)
                        ON DUPLICATE KEY UPDATE
                            total_sales_quantity  = total_sales_quantity  + VALUES(total_sales_quantity),
                            total_sales_amount    = total_sales_amount    + VALUES(total_sales_amount),
                            total_return_amount   = total_return_amount   + VALUES(total_return_amount),
                            total_discount_amount = total_discount_amount + VALUES(total_discount_amount),
                            total_cost            = total_cost            + VALUES(total_cost)
                    """), {"wm": int(wm_sales)})
                    conn.execute(text("""
                        INSERT INTO _summary_watermarks (source_table, last_key) VALUES ('FactSales', :v)
                        ON DUPLICATE KEY UPDATE last_key = :v
                    """), {"v": int(max_sales)})

                if new_online:
                    conn.execute(text("""
                        INSERT INTO summary_daily_sales
                            (DateKey, StoreKey, ProductKey, PromotionKey,
                             total_sales_quantity, total_sales_amount,
                             total_return_amount, total_discount_amount, total_cost)
                        SELECT DATE(DateKey), COALESCE(StoreKey,0), ProductKey, COALESCE(PromotionKey,0),
                               SUM(SalesQuantity), SUM(SalesAmount),
                               SUM(COALESCE(ReturnAmount,0)), SUM(COALESCE(DiscountAmount,0)),
                               SUM(COALESCE(TotalCost,0))
                        FROM FactOnlineSales WHERE OnlineSalesKey > :wm
                        GROUP BY DATE(DateKey), COALESCE(StoreKey,0), ProductKey, COALESCE(PromotionKey,0)
                        ON DUPLICATE KEY UPDATE
                            total_sales_quantity  = total_sales_quantity  + VALUES(total_sales_quantity),
                            total_sales_amount    = total_sales_amount    + VALUES(total_sales_amount),
                            total_return_amount   = total_return_amount   + VALUES(total_return_amount),
                            total_discount_amount = total_discount_amount + VALUES(total_discount_amount),
                            total_cost            = total_cost            + VALUES(total_cost)
                    """), {"wm": int(wm_online)})
                    conn.execute(text("""
                        INSERT INTO _summary_watermarks (source_table, last_key) VALUES ('FactOnlineSales', :v)
                        ON DUPLICATE KEY UPDATE last_key = :v
                    """), {"v": int(max_online)})

            logger.info("post-ingest bg: summary_daily_sales updated in %.2fs", _t.perf_counter() - t0)
        except Exception as exc:
            logger.warning("post-ingest bg summary_daily_sales update failed: %s", exc)

        _update_refresh_status(25, "Đang cập nhật bảng doanh số tổng hợp theo cửa hàng...")
        # ── Step 2: Incremental agg_store_monthly_sales ─────────
        try:
            if new_sales:
                with engine.begin() as conn:
                    _upsert_agg_store_monthly_sales_from_factsales(conn, int(wm_sales))
        except Exception as exc:
            logger.warning("post-ingest bg agg_store_monthly_sales update failed: %s", exc)

        # ── Step 3: Delta-update agg_kpi_summary ────────────────
        _update_refresh_status(35, "Đang cập nhật bảng KPI tổng hợp...")
        try:
            if new_sales or new_online:
                with engine.connect() as conn:
                    delta_sales = conn.execute(text("""
                        SELECT COUNT(*) AS cnt, COALESCE(SUM(SalesAmount),0) AS amt,
                               COALESCE(SUM(TotalCost),0) AS cost, COALESCE(SUM(SalesQuantity),0) AS qty
                        FROM FactSales WHERE SalesKey > :wm
                    """), {"wm": int(wm_sales)}).mappings().first()
                    delta_online = conn.execute(text("""
                        SELECT COUNT(*) AS cnt, COALESCE(SUM(SalesAmount),0) AS amt,
                               COALESCE(SUM(TotalCost),0) AS cost, COALESCE(SUM(SalesQuantity),0) AS qty
                        FROM FactOnlineSales WHERE OnlineSalesKey > :wm
                    """), {"wm": int(wm_online)}).mappings().first()
                    existing = {
                        row["kpi_key"]: float(row["kpi_value"])
                        for row in conn.execute(text(
                            "SELECT kpi_key, kpi_value FROM agg_kpi_summary"
                        )).mappings().all()
                    }
                total_cnt  = int(delta_sales["cnt"])   + int(delta_online["cnt"])
                total_amt  = float(delta_sales["amt"])  + float(delta_online["amt"])
                total_cost = float(delta_sales["cost"]) + float(delta_online["cost"])
                total_qty  = float(delta_sales["qty"])  + float(delta_online["qty"])
                if total_cnt > 0:
                    new_cnt  = existing.get("total_transactions", 0) + total_cnt
                    new_amt  = existing.get("total_revenue", 0) + total_amt
                    prev_cost = (existing.get("total_revenue", 0)
                                 * (1 - existing.get("gross_margin", 0) / 100)
                                 if existing.get("total_revenue", 0) > 0 else 0)
                    new_cost = prev_cost + total_cost
                    new_qty  = (existing.get("avg_basket_size", 0)
                                * existing.get("total_transactions", 1) + total_qty)
                    with engine.begin() as conn:
                        conn.execute(text("""
                            REPLACE INTO agg_kpi_summary
                                (kpi_key, kpi_label, kpi_value, kpi_unit, period)
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
            logger.info("post-ingest bg: agg_kpi_summary updated in %.2fs", _t.perf_counter() - t0)
        except Exception as exc:
            logger.warning("post-ingest bg agg_kpi_summary update failed: %s", exc)

        # ── Step 4: Clear all in-memory caches ──────────────────
        _update_refresh_status(45, "Đang xóa cache bộ nhớ...")
        try:
            from modules.sale_profit.service import clear_all_caches as _sp_clear
            _sp_clear()
        except Exception:
            pass
        try:
            from modules.employee_performance.service import clear_all_caches as _ep_clear
            _ep_clear()
        except Exception:
            pass
        try:
            from modules.data_management.analytics import clear_all_caches as _an_clear
            _an_clear()
        except Exception:
            pass

        logger.info("post-ingest bg: sync steps done in %.2fs, continuing heavy tasks", _t.perf_counter() - t0)

        _update_refresh_status(55, "Đang xây dựng lại cache dữ liệu trong nền...")
        # 5. Rebuild sale_profit parquet from updated summary_daily_sales
        _update_refresh_status(60, "Đang xây dựng lại cache Doanh thu & Lợi nhuận...")
        try:
            from modules.sale_profit.service import refresh_sales_profit_cache
            refresh_sales_profit_cache()
            logger.info("post-ingest bg: sale_profit parquet rebuilt")
        except Exception as _e:
            logger.warning("post-ingest bg parquet rebuild failed: %s", _e)
        # 6. Incremental update of all agg tables via ETL watermarks (never full rebuild)
        _update_refresh_status(72, "Đang cập nhật bảng tổng hợp tồn kho & sản phẩm...")
        try:
            from migrations.etl_pipeline import run_etl
            run_etl()
            logger.info("post-ingest bg: ETL incremental complete")
        except Exception as _e:
            logger.warning("post-ingest bg ETL failed: %s", _e)
        # 7. Refresh item_trends customer segments from updated agg_customer_rfm
        _update_refresh_status(84, "Đang cập nhật cache phân khúc khách hàng...")
        try:
            from modules.item_trends.service import build_customer_segments_cache
            build_customer_segments_cache(force_refresh=True)
        except Exception as _e:
            logger.warning("post-ingest bg item_trends cache failed: %s", _e)
        # 8. Rebuild demand forecasting parquet cache (daily_sales_snapshot + abc_xyz)
        _update_refresh_status(90, "Đang xây dựng lại cache dự báo nhu cầu (có thể mất vài phút)...")
        try:
            from modules.demand_forecasting.data.data_loader import ensure_parquet_cache
            ensure_parquet_cache(force_refresh=True)
            logger.info("post-ingest bg: demand forecasting parquet rebuilt")
        except Exception as _e:
            logger.warning("post-ingest bg demand forecasting cache failed: %s", _e)
        # 9. Trigger realtime SSE snapshot refresh
        try:
            from modules.realtime.router import _poll_dw_once
            _poll_dw_once()
        except Exception as _e:
            logger.warning("post-ingest bg realtime poll failed: %s", _e)
        # Clear analytics cache AFTER all agg tables rebuilt
        try:
            from modules.data_management.analytics import clear_all_caches as _an_clear2
            _an_clear2()
        except Exception:
            pass
        # Signal frontend via SSE that all charts data is now fresh
        try:
            from modules.realtime.router import notify_charts_refreshed
            notify_charts_refreshed()
        except Exception as _e:
            logger.warning("post-ingest bg: notify_charts_refreshed failed: %s", _e)
        _update_refresh_status(100, "Cập nhật hoàn tất — tất cả dữ liệu đã được làm mới.", running=False)

    threading.Thread(target=_heavy_bg, daemon=True).start()


@router.get("/ingest-refresh-status")
def ingest_refresh_status():
    """Return the current progress of the post-ingest background refresh.
    Poll this endpoint after a successful /csv-transform-load call
    to display a live progress bar on the frontend.
    """
    with _INGEST_STATUS_LOCK:
        return dict(_INGEST_REFRESH_STATUS)


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

    # Get DW table columns for mapping suggestions (all allowed DIM + FACT)
    engine = get_engine()
    dw_tables = {}
    with engine.connect() as conn:
        target_tables = sorted(FACT_SURROGATE_PKS.keys()) + sorted(DIM_TABLE_PKS.keys())
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

    # ── DIM tables: INSERT-only with duplicate-skip reporting ────
    if target_table in DIM_TABLE_PKS:
        pk_col = DIM_TABLE_PKS[target_table]
        if pk_col not in df_mapped.columns:
            raise HTTPException(
                status_code=400,
                detail=f"Thiếu cột khóa chính '{pk_col}' trong dữ liệu đã mapping.",
            )
        try:
            dim_result = _dim_insert_skip_duplicates(target_table, pk_col, rows)
        except Exception as exc:
            logger.error(f"[csv-transform-load] DIM upsert error for {target_table}: {exc}")
            raise HTTPException(status_code=400, detail=f"Bảng '{target_table}': {_parse_db_error(exc)}")
        _post_ingest_sync()
        return serialize_payload({
            "status": "success",
            "target_table": target_table,
            "rows_processed": len(rows),
            "rows_affected": dim_result["inserted"],
            "skipped_duplicate_ids": dim_result["skipped_ids"],
            "columns_mapped": list(mapping.keys()),
        })

    # ── Wrap DB write so errors return 400 with detail, not 500 ──
    try:
        affected = _bulk_upsert(target_table, rows, primary_keys)
    except Exception as exc:
        logger.error(f"[csv-transform-load] DB error for {target_table}: {exc}")
        raise HTTPException(
            status_code=400,
            detail=f"Bảng '{target_table}': {_parse_db_error(exc)}"
        )

    _post_ingest_sync()
    return serialize_payload({
        "status": "success",
        "target_table": target_table,
        "rows_processed": len(rows),
        "rows_affected": affected,
        "skipped_duplicate_ids": [],
        "columns_mapped": list(mapping.keys()),
    })


# ═══════════════════════════════════════════════════════════════
# Export table structure template (CSV / Excel)
# ═══════════════════════════════════════════════════════════════

@router.get("/table-structure-template")
def table_structure_template(table_name: str, format: str = "csv"):
    """
    Xuất file CSV hoặc Excel chứa cấu trúc cột (column name + data type + nullable)
    của bảng được chọn. Chỉ cho phép bảng DIM và FACT.
    """
    engine = get_engine()
    with engine.connect() as conn:
        # Validate: bảng phải tồn tại và là DIM/FACT
        exists = conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = DATABASE() AND LOWER(table_name) = :t
        """), {"t": table_name.lower()}).scalar()
        if not exists:
            raise HTTPException(status_code=404, detail=f"Bảng '{table_name}' không tồn tại")

        lower_name = table_name.lower()
        if not (lower_name.startswith("fact") or lower_name.startswith("dim")):
            raise HTTPException(status_code=400, detail="Chỉ xuất template cho bảng DIM và FACT")

        cols = conn.execute(text("""
            SELECT
                column_name    AS `column_name`,
                data_type      AS `data_type`,
                character_maximum_length AS `max_length`,
                numeric_precision        AS `precision`,
                numeric_scale            AS `scale`,
                is_nullable    AS `is_nullable`,
                column_default AS `default_value`,
                column_comment AS `description`
            FROM information_schema.columns
            WHERE table_schema = DATABASE() AND LOWER(table_name) = :t
            ORDER BY ordinal_position
        """), {"t": table_name.lower()}).mappings().all()

    if not cols:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy cột nào trong bảng '{table_name}'")

    # Build dataframe: header row = column names, row 1 = sample types, row 2+ = type hints
    col_names      = [r["column_name"]   for r in cols]
    col_types      = [r["data_type"]     for r in cols]
    col_nullable   = [r["is_nullable"]   for r in cols]
    col_default    = [str(r["default_value"]) if r["default_value"] is not None else "" for r in cols]
    col_desc       = [r["description"] or "" for r in cols]

    # Build size hint string
    def _size_hint(r):
        if r["max_length"]:
            return f"max {r['max_length']} chars"
        if r["precision"] is not None and r["scale"] is not None:
            return f"({r['precision']},{r['scale']})"
        if r["precision"] is not None:
            return f"precision {r['precision']}"
        return ""

    col_size = [_size_hint(r) for r in cols]

    # Meta dataframe: info rows (grayed out in reader)
    meta_df = pd.DataFrame({
        "# Thông tin cột": col_names,
        "Kiểu dữ liệu":    col_types,
        "Kích thước":       col_size,
        "Cho phép NULL":    col_nullable,
        "Giá trị mặc định": col_default,
        "Mô tả":            col_desc,
    })

    # Empty data template: just the column headers as one empty row
    data_df = pd.DataFrame(columns=col_names)
    data_df.loc[0] = ["" for _ in col_names]  # 1 empty row as example

    safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", table_name)
    filename  = f"template_{safe_name}"

    if format.lower() == "excel":
        buf = _io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            # Sheet 1: cấu trúc cột
            meta_df.to_excel(writer, sheet_name="Cấu trúc cột", index=False)
            # Sheet 2: template nhập liệu (chỉ headers + 1 dòng trống)
            data_df.to_excel(writer, sheet_name="Template nhập liệu", index=False)
            # Auto-width columns sheet 2
            ws = writer.sheets["Template nhập liệu"]
            for col_cells in ws.columns:
                max_len = max(len(str(cell.value or "")) for cell in col_cells)
                ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 4, 40)
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}.xlsx"'},
        )
    else:
        # CSV: 2-section file — metadata block + empty data template
        lines = []
        lines.append("# === CẤU TRÚC BẢNG: " + table_name + " ===")
        lines.append("# Cột,Kiểu,Kích thước,Nullable,Mặc định,Mô tả")
        for r, sz in zip(cols, col_size):
            lines.append(
                f"# {r['column_name']},{r['data_type']},{sz},{r['is_nullable']},"
                f"{r['default_value'] or ''},{r['description'] or ''}"
            )
        lines.append("# === TEMPLATE NHẬP LIỆU (xóa các dòng # ở trên trước khi nạp) ===")
        lines.append(",".join(col_names))
        lines.append(",".join("" for _ in col_names))  # 1 empty data row
        csv_content = "\n".join(lines) + "\n"

        return StreamingResponse(
            _io.StringIO(csv_content),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
        )


@router.get("/dim-fact-tables")
def list_dim_fact_tables():
    """Trả về danh sách tên tất cả bảng DIM và FACT trong database."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT table_name AS table_name, table_rows AS table_rows
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
              AND (LOWER(table_name) LIKE 'dim%' OR LOWER(table_name) LIKE 'fact%')
            ORDER BY table_name
        """)).mappings().all()
    return serialize_payload([
        {"table_name": r["table_name"], "row_count": int(r["table_rows"] or 0)}
        for r in rows
    ])

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
            wm_inventory = conn.execute(text(
                "SELECT COALESCE((SELECT last_key FROM _summary_watermarks WHERE source_table='FactInventory'),0)"
            )).scalar() or 0
            max_sales     = conn.execute(text("SELECT COALESCE(MAX(SalesKey),0) FROM FactSales")).scalar() or 0
            max_online    = conn.execute(text("SELECT COALESCE(MAX(OnlineSalesKey),0) FROM FactOnlineSales")).scalar() or 0
            max_inventory = conn.execute(text("SELECT COALESCE(MAX(InventoryKey),0) FROM FactInventory")).scalar() or 0

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

            # Cập nhật watermark FactInventory (không cần thay đổi summary_daily_sales)
            if int(max_inventory) > int(wm_inventory):
                conn.execute(text("""
                    INSERT INTO _summary_watermarks (source_table, last_key) VALUES ('FactInventory', :v)
                    ON DUPLICATE KEY UPDATE last_key = :v
                """), {"v": int(max_inventory)})

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

        # ── Bước 3: Clear sale_profit + employee_performance cache ────
        # Analytics cache (agg tables) sẽ được clear SAU KHI background rebuild hoàn tất
        from modules.sale_profit.service import clear_all_caches as _sp_clear, refresh_sales_profit_cache
        _sp_clear()
        try:
            from modules.employee_performance.service import clear_all_caches as _ep_clear
            _ep_clear()
        except Exception:
            pass

        # ── Bước 4 & 5: Background tasks (không block response) ────
        # Capture watermark values cho closure
        _wm_sales      = int(wm_sales)
        _wm_online     = int(wm_online)
        _wm_inventory  = int(wm_inventory)
        _max_sales     = int(max_sales)
        _max_online    = int(max_online)
        _max_inventory = int(max_inventory)

        def _bg_refresh():
            # 4a. Rebuild sale_profit parquet snapshot
            try:
                refresh_sales_profit_cache()
            except Exception as _e:
                logger.warning("bg refresh_sales_profit_cache failed: %s", _e)

            # 4b. Incremental update agg_inventory_metrics
            #     Chỉ tính lại các combo (product, store, month) bị ảnh hưởng bởi rows mới
            if _max_sales > _wm_sales or _max_inventory > _wm_inventory:
                _tmp_tables = ("_tmp_fr_new_combos", "_tmp_fr_inv_agg", "_tmp_fr_sales_agg")
                try:
                    with engine.begin() as _c:
                        for _t in _tmp_tables:
                            _c.execute(text(f"DROP TABLE IF EXISTS {_t}"))
                    with engine.begin() as _c:
                        _c.execute(text(f"""
                            CREATE TABLE _tmp_fr_new_combos AS
                            SELECT DISTINCT ProductKey, COALESCE(StoreKey,0) AS StoreKey,
                                CONCAT(YEAR(DateKey),'-',LPAD(MONTH(DateKey),2,'0')) AS ym
                            FROM FactSales WHERE SalesKey > {_wm_sales}
                            UNION
                            SELECT DISTINCT ProductKey, COALESCE(StoreKey,0) AS StoreKey,
                                CONCAT(YEAR(DateKey),'-',LPAD(MONTH(DateKey),2,'0')) AS ym
                            FROM FactInventory WHERE InventoryKey > {_wm_inventory}
                        """))
                        _c.execute(text("""
                            CREATE TABLE _tmp_fr_inv_agg AS
                            SELECT fi.ProductKey, fi.StoreKey,
                                CONCAT(YEAR(fi.DateKey),'-',LPAD(MONTH(fi.DateKey),2,'0')) AS ym,
                                AVG(fi.OnHandQuantity)              AS avg_on_hand,
                                AVG(fi.OnHandQuantity * fi.UnitCost) AS avg_inv_cost
                            FROM FactInventory fi
                            JOIN _tmp_fr_new_combos nc
                              ON nc.ProductKey = fi.ProductKey AND nc.StoreKey = fi.StoreKey
                             AND nc.ym = CONCAT(YEAR(fi.DateKey),'-',LPAD(MONTH(fi.DateKey),2,'0'))
                            GROUP BY fi.ProductKey, fi.StoreKey,
                                     CONCAT(YEAR(fi.DateKey),'-',LPAD(MONTH(fi.DateKey),2,'0'))
                        """))
                        _c.execute(text("""
                            CREATE TABLE _tmp_fr_sales_agg AS
                            SELECT fs.ProductKey, fs.StoreKey,
                                CONCAT(YEAR(fs.DateKey),'-',LPAD(MONTH(fs.DateKey),2,'0')) AS ym,
                                SUM(fs.SalesQuantity) AS total_qty,
                                SUM(fs.TotalCost)     AS total_cost,
                                SUM(fs.SalesAmount)   AS total_revenue,
                                SUM(fs.SalesQuantity) / NULLIF(COUNT(DISTINCT DATE(fs.DateKey)),0) AS daily_avg_sold
                            FROM FactSales fs
                            JOIN _tmp_fr_new_combos nc
                              ON nc.ProductKey = fs.ProductKey AND nc.StoreKey = fs.StoreKey
                             AND nc.ym = CONCAT(YEAR(fs.DateKey),'-',LPAD(MONTH(fs.DateKey),2,'0'))
                            GROUP BY fs.ProductKey, fs.StoreKey,
                                     CONCAT(YEAR(fs.DateKey),'-',LPAD(MONTH(fs.DateKey),2,'0'))
                        """))
                        _c.execute(text("""
                            REPLACE INTO agg_inventory_metrics
                                (product_key, store_key, period_month,
                                 avg_on_hand, total_sold, total_cost_sold, total_revenue,
                                 gross_profit, inventory_turnover, sell_through_rate,
                                 gmroi, days_of_supply)
                            SELECT
                                inv.ProductKey, inv.StoreKey, inv.ym,
                                inv.avg_on_hand,
                                COALESCE(s.total_qty, 0),
                                COALESCE(s.total_cost, 0),
                                COALESCE(s.total_revenue, 0),
                                COALESCE(s.total_revenue, 0) - COALESCE(s.total_cost, 0),
                                CASE WHEN inv.avg_inv_cost > 0
                                     THEN COALESCE(s.total_cost, 0) / inv.avg_inv_cost ELSE 0 END,
                                CASE WHEN (COALESCE(s.total_qty,0) + inv.avg_on_hand) > 0
                                     THEN COALESCE(s.total_qty,0)
                                          / (COALESCE(s.total_qty,0) + inv.avg_on_hand) ELSE 0 END,
                                CASE WHEN inv.avg_inv_cost > 0
                                     THEN (COALESCE(s.total_revenue,0) - COALESCE(s.total_cost,0))
                                          / inv.avg_inv_cost ELSE 0 END,
                                CASE WHEN COALESCE(s.daily_avg_sold,0) > 0
                                     THEN inv.avg_on_hand / s.daily_avg_sold ELSE 0 END
                            FROM _tmp_fr_inv_agg inv
                            LEFT JOIN _tmp_fr_sales_agg s
                              ON s.ProductKey = inv.ProductKey AND s.StoreKey = inv.StoreKey
                             AND s.ym = inv.ym
                        """))
                    with engine.begin() as _c:
                        for _t in _tmp_tables:
                            _c.execute(text(f"DROP TABLE IF EXISTS {_t}"))
                    logger.info("bg agg_inventory_metrics: incremental update done")
                except Exception as _e:
                    logger.warning("bg agg_inventory_metrics update failed: %s", _e)
                    try:
                        with engine.begin() as _c:
                            for _t in _tmp_tables:
                                _c.execute(text(f"DROP TABLE IF EXISTS {_t}"))
                    except Exception:
                        pass

            # 4c. Rebuild agg_product_performance (ABC)
            #     Dùng summary_daily_sales (đã updated ở Bước 1) thay vì v_total_sales 10M rows
            #     → nhanh (~300ms). Sau đó chạy lại window function RANK()/cumulative_pct
            #     trên bảng ~2K sản phẩm.
            try:
                with engine.begin() as _c:
                    _c.execute(text("DELETE FROM agg_product_performance"))
                    _c.execute(text("""
                        INSERT INTO agg_product_performance
                            (product_key, product_name, brand_name, category_name, subcategory_name,
                             total_revenue, total_quantity, total_cost, gross_profit, profit_margin,
                             revenue_rank, abc_class, cumulative_pct)
                        SELECT
                            p.ProductKey, p.ProductName, p.BrandName,
                            COALESCE(pc.ProductCategoryName, ''),
                            COALESCE(psc.ProductSubcategoryName, ''),
                            COALESCE(agg.total_revenue, 0),
                            COALESCE(agg.total_quantity, 0),
                            COALESCE(agg.total_cost, 0),
                            COALESCE(agg.total_revenue, 0) - COALESCE(agg.total_cost, 0),
                            CASE WHEN COALESCE(agg.total_revenue, 0) > 0
                                 THEN (COALESCE(agg.total_revenue,0) - COALESCE(agg.total_cost,0))
                                      / agg.total_revenue
                                 ELSE 0 END,
                            RANK() OVER (ORDER BY COALESCE(agg.total_revenue,0) DESC),
                            'C',
                            SUM(COALESCE(agg.total_revenue,0))
                                OVER (ORDER BY COALESCE(agg.total_revenue,0) DESC)
                                / NULLIF(SUM(COALESCE(agg.total_revenue,0)) OVER (), 0)
                        FROM (
                            SELECT sds.ProductKey,
                                SUM(sds.total_sales_amount
                                    - COALESCE(sds.total_return_amount, 0)
                                    - COALESCE(sds.total_discount_amount, 0)) AS total_revenue,
                                SUM(sds.total_sales_quantity)                 AS total_quantity,
                                SUM(sds.total_sales_quantity
                                    * COALESCE(p2.UnitCost, 0))               AS total_cost
                            FROM summary_daily_sales sds
                            LEFT JOIN DimProduct p2 ON p2.ProductKey = sds.ProductKey
                            GROUP BY sds.ProductKey
                        ) agg
                        JOIN DimProduct p ON p.ProductKey = agg.ProductKey
                        LEFT JOIN DimProductSubcategory psc
                          ON psc.ProductSubcategoryKey = p.ProductSubcategoryKey
                        LEFT JOIN DimProductCategory pc
                          ON pc.ProductCategoryKey = psc.ProductCategoryKey
                    """))
                    _c.execute(text("""
                        UPDATE agg_product_performance SET abc_class =
                            CASE WHEN cumulative_pct <= 0.80 THEN 'A'
                                 WHEN cumulative_pct <= 0.95 THEN 'B'
                                 ELSE 'C' END
                    """))
                logger.info("bg agg_product_performance: rebuild done (via summary_daily_sales)")
            except Exception as _e:
                logger.warning("bg agg_product_performance rebuild failed: %s", _e)

            # 4d. Incremental update agg_customer_rfm
            #     Bước 1: Update metrics thô của các customers có giao dịch mới
            #     Bước 2: Chạy lại NTILE(5) trên bảng agg_customer_rfm (~21K rows) — nhanh
            if _max_online > _wm_online:
                try:
                    with engine.begin() as _c:
                        # Bước 1: Upsert metrics của customers bị ảnh hưởng
                        _c.execute(text("""
                            REPLACE INTO agg_customer_rfm
                                (customer_key, last_order_date, recency_days,
                                 frequency, monetary, r_score, f_score, m_score, rfm_segment)
                            SELECT
                                f.CustomerKey,
                                MAX(DATE(f.DateKey)),
                                DATEDIFF(
                                    (SELECT MAX(DATE(DateKey)) FROM FactOnlineSales),
                                    MAX(DATE(f.DateKey))
                                ),
                                COUNT(DISTINCT f.SalesOrderNumber),
                                SUM(f.SalesAmount),
                                1, 1, 1, 'Unknown'
                            FROM FactOnlineSales f
                            WHERE f.CustomerKey IN (
                                SELECT DISTINCT CustomerKey FROM FactOnlineSales
                                WHERE OnlineSalesKey > :wm AND CustomerKey IS NOT NULL
                            ) AND f.CustomerKey IS NOT NULL
                            GROUP BY f.CustomerKey
                        """), {"wm": _wm_online})
                        # Bước 2: Rescore toàn bộ bảng bằng NTILE trên ~21K rows (nhanh)
                        _c.execute(text("DROP TEMPORARY TABLE IF EXISTS _tmp_rfm_scores"))
                        _c.execute(text("""
                            CREATE TEMPORARY TABLE _tmp_rfm_scores AS
                            SELECT customer_key,
                                NTILE(5) OVER (ORDER BY recency_days ASC) AS r_score,
                                NTILE(5) OVER (ORDER BY frequency    ASC) AS f_score,
                                NTILE(5) OVER (ORDER BY monetary     ASC) AS m_score
                            FROM agg_customer_rfm
                        """))
                        _c.execute(text("""
                            UPDATE agg_customer_rfm a
                            JOIN _tmp_rfm_scores s ON s.customer_key = a.customer_key
                            SET a.r_score = s.r_score,
                                a.f_score = s.f_score,
                                a.m_score = s.m_score,
                                a.rfm_segment = CASE
                                    WHEN s.r_score >= 4 AND s.f_score >= 4 AND s.m_score >= 4 THEN 'Champion'
                                    WHEN s.r_score >= 3 AND s.f_score >= 3 AND s.m_score >= 3 THEN 'Loyal'
                                    WHEN s.r_score >= 4 AND s.f_score <= 2                    THEN 'New Customer'
                                    WHEN s.r_score <= 2 AND s.f_score >= 3 AND s.m_score >= 3 THEN 'At Risk'
                                    WHEN s.r_score <= 2 AND s.f_score <= 2                    THEN 'Lost'
                                    WHEN s.r_score >= 3 AND s.m_score >= 3                    THEN 'Potential Loyalist'
                                    ELSE 'Need Attention'
                                END
                        """))
                        _c.execute(text("DROP TEMPORARY TABLE IF EXISTS _tmp_rfm_scores"))
                    logger.info("bg agg_customer_rfm: incremental update + NTILE rescore done")
                except Exception as _e:
                    logger.warning("bg agg_customer_rfm update failed: %s", _e)

            # 4e. Rebuild item_trends parquet SAU KHI agg_customer_rfm đã được cập nhật
            try:
                from modules.item_trends.service import build_customer_segments_cache
                build_customer_segments_cache(force_refresh=True)
            except Exception as _e:
                logger.warning("bg item_trends cache refresh failed: %s", _e)

            # 4f. Clear analytics cache SAU KHI tất cả bảng aggregate đã được rebuild
            #     (tránh serve stale data từ DB trong lúc rebuild chưa xong)
            try:
                from modules.data_management.analytics import clear_all_caches as _an_clear
                _an_clear()
            except Exception:
                pass

            # 4g. Trigger realtime DW poll
            try:
                from modules.realtime.router import _poll_dw_once
                _poll_dw_once()
            except Exception as _e:
                logger.warning("bg realtime poll failed: %s", _e)

        threading.Thread(target=_bg_refresh, daemon=True).start()

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


