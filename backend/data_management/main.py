import logging
import threading
import time
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
import pandas as pd
import json
import os
from datetime import datetime
import shutil
import io
from sqlalchemy import text

from .analytics import router as analytics_router
from db_utils import get_engine, serialize_payload



try:
    from dm_config import BACKUP_DIR, SCHEMA_FILE, API_HOST, API_PORT
except ImportError:
    from .dm_config import BACKUP_DIR, SCHEMA_FILE, API_HOST, API_PORT

try:
    from config import (
        DW_HOST, DW_PORT, DW_USER, DW_PASSWORD, DW_DATABASE,
        POS_HOST, POS_PORT, POS_USER, POS_PASSWORD, POS_DATABASE,
    )
except ImportError:
    DW_HOST = DW_PORT = DW_USER = DW_PASSWORD = DW_DATABASE = None
    POS_HOST = POS_PORT = POS_USER = POS_PASSWORD = POS_DATABASE = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="BI Data Management API")
app.include_router(analytics_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    logger.info("Data Management startup ready.")


def _sanitize_df(df: pd.DataFrame) -> pd.DataFrame:
    return df.where(pd.notna(df), None)


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

@app.get("/schema")
def get_schemas():
    return load_schema()

@app.post("/schema")
def update_schemas(schema_data: Dict[str, Any]):
    save_schema(schema_data)
    return {"message": "Schema updated successfully"}

@app.get("/template/{table_name}")
def get_template(table_name: str):
    schemas = load_schema()
    if table_name not in schemas:
        raise HTTPException(status_code=404, detail="Table not found in schema")
    
    table_info = schemas[table_name]
    columns = [col["name"] for col in table_info["columns"]]
    
    df = pd.DataFrame(columns=columns)
    template_path = f"template_{table_name}.xlsx"
    df.to_excel(template_path, index=False)
    
    return FileResponse(template_path, filename=f"Template_{table_name}.xlsx", media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.post("/upload")
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

@app.post("/ingest")
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
    return {"message": f"Ingested into MySQL table '{table_name}'. Affected rows: {affected_rows}"}

ALLOWED_TABLES = {
    "FactSales", "FactOnlineSales", "FactInventory",
    "DimProduct", "DimStore", "DimEmployee", "DimChannel",
    "DimPromotion", "DimCurrency", "DimCustomer",
    "DimDate", "DimGeography", "DimProductCategory",
    "DimProductSubcategory", "summary_daily_sales",
}


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

@app.post("/purge")
def purge_data(request: PurgeRequest):
    schemas = load_schema()
    table_name = _validate_table_name(request.table_name)
    if table_name not in schemas:
        raise HTTPException(status_code=404, detail="Table schema not found")
        
    schema = schemas[table_name]
    backup_table = f"backup_{table_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    conditions = ["1=1"]
    params: Dict[str, Any] = {}

    if schema["deletion_strategy"] == "DATE_RANGE":
        if request.start_date:
            conditions.append("DateKey >= :start_date")
            params["start_date"] = request.start_date
        if request.end_date:
            conditions.append("DateKey <= :end_date")
            params["end_date"] = request.end_date
    elif schema["deletion_strategy"] == "CATEGORY" and request.category:
        conditions.append("BrandName = :category")
        params["category"] = request.category

    where_clause = " AND ".join(conditions)
    engine = get_engine()

    with engine.begin() as conn:
        total_before = conn.execute(text(f"SELECT COUNT(*) AS c FROM {table_name}")).scalar() or 0

        conn.execute(text(f"CREATE TABLE {backup_table} AS SELECT * FROM {table_name} WHERE {where_clause}"), params)
        conn.execute(text(f"DELETE FROM {table_name} WHERE {where_clause}"), params)

        total_after = conn.execute(text(f"SELECT COUNT(*) AS c FROM {table_name}")).scalar() or 0

    return {
        "message": "Data purged successfully",
        "backup_table": backup_table,
        "deleted_rows": int(total_before - total_after),
        "remaining_rows": int(total_after),
    }

@app.get("/categories/{table_name}")
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

@app.get("/dw-health")
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
        # Default: POS system connection
        default_sources = [
            {
                "id": "pos_system",
                "name": "POS System (pos_system)",
                "type": "mysql",
                "host": POS_HOST or "127.0.0.1",
                "port": POS_PORT or 3306,
                "database": POS_DATABASE or "pos_system",
                "user": POS_USER or "root",
                "status": "connected",
                "last_sync": None,
                "created_at": datetime.now().isoformat(),
            }
        ]
        _save_data_sources(default_sources)
        return default_sources
    with open(_DATA_SOURCES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_data_sources(sources: List[Dict[str, Any]]):
    with open(_DATA_SOURCES_FILE, "w", encoding="utf-8") as f:
        json.dump(sources, f, ensure_ascii=False, indent=2, default=str)


@app.get("/data-sources")
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


@app.post("/data-sources")
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


@app.post("/data-sources/{source_id}/test")
def test_data_source(source_id: str, password: Optional[str] = None):
    """Test if a data source connection is working."""
    sources = _load_data_sources()
    source = next((s for s in sources if s["id"] == source_id), None)
    if not source:
        raise HTTPException(status_code=404, detail="Data source not found")

    try:
        from sqlalchemy import create_engine as ce
        pwd = password or (POS_PASSWORD if source["database"] == POS_DATABASE else DW_PASSWORD) or "12345"
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

@app.post("/csv-upload-preview")
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


@app.post("/csv-transform-load")
async def csv_transform_load(
    target_table: str = Form(...),
    column_mapping: str = Form(...),
    file: UploadFile = File(...),
):
    """Transform CSV data using column mapping and load into DW target table."""
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

    # Sanitize
    df_mapped = _sanitize_df(df_mapped)
    if primary_keys:
        pk_in_df = [pk for pk in primary_keys if pk in df_mapped.columns]
        if pk_in_df:
            df_mapped = df_mapped.drop_duplicates(subset=pk_in_df, keep="last")

    rows = df_mapped.to_dict(orient="records")
    affected = _bulk_upsert(target_table, rows, primary_keys)

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


@app.get("/etl/status")
def etl_status():
    return serialize_payload(_ETL_STATUS)


@app.post("/etl/run")
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
            from etl_pipeline import run_etl
            run_etl()
            _ETL_STATUS["last_status"] = "success"
            _ETL_STATUS["tables_built"] = [
                "agg_inventory_metrics", "agg_product_performance",
                "agg_customer_rfm", "agg_kpi_summary", "agg_store_monthly_costs",
            ]

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


@app.post("/etl/refresh-segments")
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
