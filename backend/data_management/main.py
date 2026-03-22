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
    try:
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
            if not request.start_date and not request.end_date:
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=400, content={"detail": "Vui lòng chọn [Từ ngày] hoặc [Đến ngày] để có thể lọc dữ liệu cần xóa."})
                
            if 'DateKey' not in df.columns:
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=400, content={"detail": "Bảng không có cột DateKey để xóa theo định dạng ngày tháng."})
                
            df['DateKey'] = pd.to_datetime(df['DateKey'], errors='coerce', dayfirst=True)
            condition = pd.Series(True, index=df.index)
            
            if request.start_date:
                condition = condition & (df['DateKey'] >= pd.to_datetime(request.start_date))
            if request.end_date:
                condition = condition & (df['DateKey'] <= pd.to_datetime(request.end_date))
                
            df = df[~condition] # keep rows that DO NOT match the purge condition
            
        elif schema["deletion_strategy"] == "CATEGORY":
            if not request.category:
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=400, content={"detail": "Vui lòng chọn Category/Brand cần xóa từ danh sách thả xuống."})
                
            cat_col = 'BrandName' if 'BrandName' in df.columns else 'StoreName' if 'StoreName' in df.columns else None
            if cat_col:
                df = df[df[cat_col] != request.category]
            else:
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=400, content={"detail": "Bảng này chưa hỗ trợ cấu hình cột xóa theo Category."})
                
        deleted = initial_len - len(df)
        if deleted == 0:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=400, content={"detail": "Không có dòng dữ liệu nào khớp với thông tin/ngày tháng bạn vừa cung cấp để xóa. Vui lòng kiểm tra lại Dữ liệu Gốc!"})
            
        df.to_csv(file_path, index=False)
        
        return {
            "message": "Data purged successfully",
            "deleted_rows": initial_len - len(df),
            "remaining_rows": len(df)
        }
    except Exception as e:
        logger.error(f"Purge error: {e}")
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=400, content={"detail": f"Purge thất bại: {str(e)}"})

@app.get("/categories/{table_name}")
def get_categories(table_name: str):
    file_path = DATA_DIR / f"{table_name}.csv"
    if not file_path.exists():
        return {"categories": []}
    df = pd.read_csv(file_path)
    if 'BrandName' in df.columns:
        return {"categories": df['BrandName'].dropna().unique().tolist()}
    elif 'StoreName' in df.columns:
        return {"categories": df['StoreName'].dropna().unique().tolist()}
    return {"categories": []}

@app.get("/api/dashboard/sales")
def get_sales_dashboard():
    try:
        fact_path = DATA_DIR / "FactSales.csv"
        prod_path = DATA_DIR / "DimProduct.csv"
        store_path = DATA_DIR / "DimStore.csv"
        date_path = DATA_DIR / "DimDate.csv"
        
        if not fact_path.exists() or os.path.getsize(fact_path) == 0:
            return {"status": "empty", "message": "Chưa có dữ liệu FactSales."}
            
        df_fact = pd.read_csv(fact_path)
        if len(df_fact) == 0:
            return {"status": "empty", "message": "FactSales rỗng."}
            
        # Merge if columns exist
        df_store = pd.read_csv(store_path) if store_path.exists() else pd.DataFrame(columns=['StoreKey', 'StoreName'])
        
        if 'StoreKey' in df_fact.columns and 'StoreKey' in df_store.columns:
            # Drop everything but StoreKey and StoreName from DimStore to avoid suffix collisions and memory bloat
            cols_to_keep = ['StoreKey'] + ([c for c in ['StoreName'] if c in df_store.columns])
            df_store_slim = df_store[cols_to_keep].drop_duplicates()
            
            if 'StoreName' in df_fact.columns:
                df_fact = df_fact.drop(columns=['StoreName'])
                
            df_fact = pd.merge(df_fact, df_store_slim, on='StoreKey', how='left')
            
        # Calculation
        df_fact['TotalSales'] = df_fact.get('SalesQuantity', 0) * df_fact.get('UnitPrice', 0) - df_fact.get('DiscountAmount', 0)
        
        # Time processing
        if 'DateKey' in df_fact.columns:
            df_fact['DateKey'] = pd.to_datetime(df_fact['DateKey'], errors='coerce', dayfirst=True)
        else:
            return {"status": "error", "message": "Thiếu DateKey trong FactSales"}
            
        # Summaries
        max_date = df_fact['DateKey'].max()
        if pd.isna(max_date):
            return {"status": "empty", "message": "Không có dữ liệu Date hợp lệ"}
            
        ytd_mask = (df_fact['DateKey'].dt.year == max_date.year) & (df_fact['DateKey'] <= max_date)
        mtd_mask = ytd_mask & (df_fact['DateKey'].dt.month == max_date.month)
        
        ytd_sales = float(df_fact.loc[ytd_mask, 'TotalSales'].fillna(0).sum())
        mtd_sales = float(df_fact.loc[mtd_mask, 'TotalSales'].fillna(0).sum())
        total_sales = float(df_fact['TotalSales'].fillna(0).sum())
        
        # Line chart
        trend = df_fact.groupby(df_fact['DateKey'].dt.strftime('%Y-%m-%d'))['TotalSales'].sum().reset_index()
        trend_data = {
            "labels": trend['DateKey'].tolist(),
            "data": trend['TotalSales'].fillna(0).tolist()
        }
        
        # Pie chart
        store_col = 'StoreName' if 'StoreName' in df_fact.columns else 'StoreKey'
        pie = df_fact.groupby(store_col)['TotalSales'].sum().reset_index()
        pie_data = {
            "labels": pie[store_col].astype(str).tolist(),
            "data": pie['TotalSales'].fillna(0).tolist()
        }
        
        return {
            "status": "success",
            "ytd": ytd_sales,
            "mtd": mtd_sales,
            "total": total_sales,
            "trend": trend_data,
            "store_pie": pie_data,
            "last_updated": max_date.strftime('%Y-%m-%d')
        }
        
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=API_HOST, port=API_PORT, reload=True)
