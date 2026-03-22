import logging
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

from .analytics import router as analytics_router



from dm_config import DATA_DIR, BACKUP_DIR, SCHEMA_FILE, API_HOST, API_PORT

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
        
    file_path = DATA_DIR / f"{table_name}.csv"
    
    # Backup existing
    if file_path.exists():
        backup_name = f"{table_name}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        shutil.copy2(file_path, BACKUP_DIR / backup_name)
        
        # Merge logic
        old_df = pd.read_csv(file_path)
        combined = pd.concat([old_df, new_df], ignore_index=True)
        if primary_keys:
            combined = combined.drop_duplicates(subset=primary_keys, keep='last')
        combined.to_csv(file_path, index=False)
        return {"message": f"Appended and deduplicated. Rows: {len(combined)}"}
    else:
        if primary_keys:
            new_df = new_df.drop_duplicates(subset=primary_keys, keep='last')
        new_df.to_csv(file_path, index=False)
        return {"message": f"Created new file. Rows: {len(new_df)}"}

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
    file_path = DATA_DIR / f"{table_name}.csv"
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Data file not found")
        
    df = pd.read_csv(file_path)
    initial_len = len(df)
    
    # Backup
    backup_name = f"{table_name}_prepurge_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    shutil.copy2(file_path, BACKUP_DIR / backup_name)
    
    if schema["deletion_strategy"] == "DATE_RANGE":
        # Assuming DateKey exists
        df['DateKey'] = pd.to_datetime(df['DateKey'])
        condition = pd.Series(True, index=df.index)
        
        if request.start_date:
            condition = condition & (df['DateKey'] >= pd.to_datetime(request.start_date))
        if request.end_date:
            condition = condition & (df['DateKey'] <= pd.to_datetime(request.end_date))
            
        df = df[~condition] # keep rows that DO NOT match the purge condition
        
    elif schema["deletion_strategy"] == "CATEGORY":
        # In DimProduct we have ClassName or BrandName, assume BrandName for now if Category not explicit
        if request.category and 'BrandName' in df.columns:
            df = df[df['BrandName'] != request.category]
            
    df.to_csv(file_path, index=False)
    
    return {
        "message": "Data purged successfully",
        "deleted_rows": initial_len - len(df),
        "remaining_rows": len(df)
    }

@app.get("/categories/{table_name}")
def get_categories(table_name: str):
    file_path = DATA_DIR / f"{table_name}.csv"
    if not file_path.exists():
        return []
    df = pd.read_csv(file_path)
    if 'BrandName' in df.columns:
        return df['BrandName'].dropna().unique().tolist()
    return []

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=API_HOST, port=API_PORT, reload=True)
