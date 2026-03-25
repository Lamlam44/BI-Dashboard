import logging
import threading
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="BI Data Management API")
app.include_router(analytics_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    SELECT column_name
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

class PurgeRequest(BaseModel):
    table_name: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    category: Optional[str] = None

@app.post("/purge")
def purge_data(request: PurgeRequest):
    schemas = load_schema()
    table_name = request.table_name
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
    engine = get_engine()
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT DISTINCT BrandName FROM {table_name} WHERE BrandName IS NOT NULL ORDER BY BrandName")
            ).mappings().all()
        return [row["BrandName"] for row in rows]
    except Exception:
        return []

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("data_management.main:app", host=API_HOST, port=API_PORT, reload=True)
