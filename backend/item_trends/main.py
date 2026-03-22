import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import time
from typing import Optional
from pathlib import Path

# Import config
try:
    from it_config import DATA_DIR, SEGMENTS_FILE, API_HOST, API_PORT
except ImportError:
    from .it_config import DATA_DIR, SEGMENTS_FILE, API_HOST, API_PORT

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="BI Item Trends API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================
# LOAD DATA 1 LẦN (RAM)
# ==============================
print("🚀 [Item Trends] Đang nạp dữ liệu vào RAM...")
start_time = time.time()

# Paths
FACT_SALES_PATH = DATA_DIR / "FactSales.csv"
FACT_ONLINE_PATH = DATA_DIR / "FactOnlineSales.csv"
DIM_PRODUCT_PATH = DATA_DIR / "DimProduct.csv"
DIM_PROMO_PATH = DATA_DIR / "DimPromotion.csv"
DIM_SUBCAT_PATH = DATA_DIR / "DimProductSubcategory.csv"
DIM_CUST_PATH = DATA_DIR / "DimCustomer.csv"
DIM_GEO_PATH = DATA_DIR / "DimGeography.csv"
AI_RESULT_PATH = SEGMENTS_FILE

# Load Dimension
df_prod = pd.read_csv(DIM_PRODUCT_PATH, encoding='latin1')
df_promo = pd.read_csv(DIM_PROMO_PATH, encoding='latin1')
df_subcat = pd.read_csv(DIM_SUBCAT_PATH, encoding='latin1')
df_cust = pd.read_csv(DIM_CUST_PATH, encoding='latin1')
df_geo = pd.read_csv(DIM_GEO_PATH, encoding='latin1')
try:
    df_ai = pd.read_csv(AI_RESULT_PATH)
except FileNotFoundError:
    print("⚠️ [Warning] Customer_Segments_Final.csv not found! Using empty DataFrame.")
    df_ai = pd.DataFrame(columns=['CustomerKey', 'Segment'])

# Load Fact
common_cols = ['ProductKey', 'PromotionKey', 'SalesQuantity', 'SalesAmount', 'DateKey']
df_off = pd.read_csv(FACT_SALES_PATH, usecols=common_cols)
df_on = pd.read_csv(FACT_ONLINE_PATH, usecols=common_cols + ['CustomerKey'])

# Combine
DF_COMBINED = pd.concat([df_off[common_cols], df_on[common_cols]], ignore_index=True)
DF_ONLINE_ONLY = df_on

# Convert date (1 lần duy nhất)
# Optimize date parsing by specifying format and avoiding astype where possible
DF_COMBINED['OrderDate'] = pd.to_datetime(DF_COMBINED['DateKey'], format='%Y-%m-%d', errors='coerce')
DF_ONLINE_ONLY['OrderDate'] = pd.to_datetime(DF_ONLINE_ONLY['DateKey'], format='%Y-%m-%d', errors='coerce')

end_time = time.time()
print(f"✅ [Item Trends] Loaded {len(DF_COMBINED):,} rows in {end_time - start_time:.2f}s")


# ==============================
# HELPER
# ==============================
def filter_by_date(df: pd.DataFrame, start_date: Optional[str] = None, end_date: Optional[str] = None):
    filtered = df
    if start_date:
        filtered = filtered[filtered['OrderDate'] >= pd.to_datetime(start_date)]
    if end_date:
        filtered = filtered[filtered['OrderDate'] <= pd.to_datetime(end_date)]
    return filtered


# ==============================
# APIs
# ==============================

@app.get("/api/summary-stats")
def summary_stats(start_date: Optional[str] = None, end_date: Optional[str] = None):
    df_filtered = filter_by_date(DF_COMBINED, start_date, end_date)
    total_revenue = df_filtered['SalesAmount'].sum()

    df_on_filtered = filter_by_date(DF_ONLINE_ONLY, start_date, end_date)
    active_customers = df_on_filtered['CustomerKey'].unique()

    df_ai_active = df_ai[df_ai['CustomerKey'].isin(active_customers)]

    total_customers = len(active_customers)
    top_segment = df_ai_active['Segment'].value_counts().idxmax() if not df_ai_active.empty else "N/A"

    return {
        "total_revenue": f"${total_revenue:,.2f}",
        "total_customers": total_customers,
        "top_segment": top_segment
    }


@app.get("/api/sales-by-location")
def get_sales_by_location(start_date: Optional[str] = None, end_date: Optional[str] = None):
    try:
        df = filter_by_date(DF_ONLINE_ONLY, start_date, end_date).copy()
        
        if df.empty:
            return {"status": "success", "labels": [], "datasets": []}
            
        df['Quarter'] = df['OrderDate'].dt.to_period('Q').astype(str)
        
        df_temp = pd.merge(df, df_cust[['CustomerKey', 'GeographyKey']], on='CustomerKey')
        df_merged = pd.merge(df_temp, df_geo[['GeographyKey', 'RegionCountryName']], on='GeographyKey')
        
        top_5 = df_merged.groupby('RegionCountryName')['SalesAmount'].sum().nlargest(5).index.tolist()
        df_top = df_merged[df_merged['RegionCountryName'].isin(top_5)]
        
        grouped = df_top.groupby(['RegionCountryName', 'Quarter'])['SalesAmount'].sum().unstack(fill_value=0)
        
        quarters = sorted(grouped.columns.tolist())
        labels = grouped.index.tolist()
        
        colors = ['#3b82f6', '#a855f7', '#10b981', '#f97316', '#ef4444', '#14b8a6', '#ec4899'] 
        
        datasets = []
        for i, q in enumerate(quarters):
            datasets.append({
                "label": q,
                "data": grouped[q].tolist(),
                "backgroundColor": colors[i % len(colors)],
                "borderRadius": 5
            })
            
        return {
            "status": "success",
            "labels": labels,
            "datasets": datasets
        }
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return {"status": "error", "message": str(e)}


@app.get("/api/customer-segments")
def customer_segments(start_date: Optional[str] = None, end_date: Optional[str] = None):
    df_on_filtered = filter_by_date(DF_ONLINE_ONLY, start_date, end_date)
    active_customers = df_on_filtered['CustomerKey'].unique()

    df_filtered = df_ai[df_ai['CustomerKey'].isin(active_customers)] if (start_date or end_date) else df_ai

    segment_counts = df_filtered['Segment'].value_counts()

    return {
        "labels": segment_counts.index.tolist(),
        "data": segment_counts.values.tolist()
    }


@app.get("/api/trending-products")
def trending_products(start_date: Optional[str] = None, end_date: Optional[str] = None):
    df_filtered = filter_by_date(DF_COMBINED, start_date, end_date)
    if df_filtered.empty:
        return []

    df_merged = pd.merge(df_filtered, df_prod, on='ProductKey')
    grouped = df_merged.groupby('ProductName')['SalesQuantity'].sum().reset_index()

    top = grouped.sort_values(by='SalesQuantity', ascending=False).head(10)

    return [{"name": r['ProductName'], "qty": int(r['SalesQuantity'])} for _, r in top.iterrows()]


@app.get("/api/promotion-impact")
def get_promotion_impact(start_date: Optional[str] = None, end_date: Optional[str] = None):
    try:
        df_filtered = filter_by_date(DF_COMBINED, start_date, end_date)
        
        if df_filtered.empty:
            return {"labels": [], "datasets": []}

        df_merged = pd.merge(df_filtered, df_promo, on='PromotionKey', how='inner')
        df_merged = pd.merge(df_merged, df_prod, on='ProductKey', how='inner')
        df_merged = pd.merge(df_merged, df_subcat, on='ProductSubcategoryKey', how='inner')

        grouped = df_merged.groupby(['PromotionName', 'ProductCategoryKey'])['SalesAmount'].sum().reset_index()
        promotions = grouped['PromotionName'].unique().tolist()
        
        category_mapping = {1: "Audio Devices", 2: "TV & Video", 3: "Computers", 4: "Cameras & Imaging", 
                            5: "Mobile Phones & Accessories", 6: "Media & Entertainment Content", 
                            7: "Gaming", 8: "Home Appliances"}

        color_mapping = {"Audio Devices": "#3b82f6", "TV & Video": "#8b5cf6", "Computers": "#10b981", 
                         "Cameras & Imaging": "#f59e0b", "Mobile Phones & Accessories": "#ef4444", 
                         "Media & Entertainment Content": "#14b8a6", "Gaming": "#ec4899", "Home Appliances": "#eab308"}

        datasets = []
        existing_keys = sorted(grouped['ProductCategoryKey'].unique().tolist())
        
        for cat_key in existing_keys:
            cat_name = category_mapping.get(cat_key, f"Category {cat_key}")
            cat_data = []
            for promo in promotions:
                val = grouped[(grouped['PromotionName'] == promo) & (grouped['ProductCategoryKey'] == cat_key)]['SalesAmount']
                cat_data.append(float(val.values[0]) if not val.empty else 0)
                
            datasets.append({
                "label": cat_name,
                "data": cat_data,
                "backgroundColor": color_mapping.get(cat_name, "#9ca3af")
            })

        return {"labels": promotions, "datasets": datasets}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=API_HOST, port=API_PORT, reload=True)