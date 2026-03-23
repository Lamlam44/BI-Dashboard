"""
Data loading module for the Demand Forecasting system.
Handles loading and merging FactSales, DimProduct, and DimDate datasets.
"""

import pandas as pd
import numpy as np
from typing import Tuple, Optional
import logging
import sys
from pathlib import Path
from sqlalchemy import text
from datetime import datetime, timedelta

import df_config as config

backend_root = Path(__file__).resolve().parents[2]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from db_utils import get_engine

logger = logging.getLogger(__name__)

CACHE_DIR = config.PROJECT_ROOT / "cache"
DAILY_SNAPSHOT_FILE = CACHE_DIR / "daily_sales_snapshot.parquet"
ABC_XYZ_FILE = CACHE_DIR / "abc_xyz_snapshot.parquet"
META_FILE = CACHE_DIR / "snapshot_meta.json"


UNIFIED_FACT_SQL = """
    SELECT
        DateKey,
        ProductKey,
        SalesQuantity,
        SalesAmount,
        UnitPrice,
        DiscountAmount
    FROM FactSales
    UNION ALL
    SELECT
        DateKey,
        ProductKey,
        SalesQuantity,
        SalesAmount,
        UnitPrice,
        DiscountAmount
    FROM FactOnlineSales
"""


def load_raw_data() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Load raw data from MySQL tables.
    
    Returns:
        Tuple containing:
        - fact_sales: FactSales DataFrame
        - dim_product: DimProduct DataFrame
        - dim_date: DimDate DataFrame
    """
    try:
        engine = get_engine()

        logger.info("Loading FactSales + FactOnlineSales data from MySQL...")
        fact_sales = pd.read_sql_query(text(UNIFIED_FACT_SQL), engine)

        logger.info("Loading DimProduct data from MySQL...")
        dim_product = pd.read_sql_query(
            text(
                """
                SELECT
                    ProductKey,
                    ProductName,
                    UnitPrice
                FROM DimProduct
                """
            ),
            engine,
        )

        logger.info("Loading DimDate data from MySQL...")
        dim_date = pd.read_sql_query(
            text(
                """
                SELECT DateKey
                FROM DimDate
                """
            ),
            engine,
        )
        
        logger.info(f"FactSales shape: {fact_sales.shape}")
        logger.info(f"DimProduct shape: {dim_product.shape}")
        logger.info(f"DimDate shape: {dim_date.shape}")
        
        return fact_sales, dim_product, dim_date
    
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        raise
    except Exception as e:
        logger.error(f"Error loading data: {e}")
        raise


def prepare_sales_data(
    fact_sales: pd.DataFrame,
    dim_product: pd.DataFrame,
    dim_date: pd.DataFrame
) -> pd.DataFrame:
    """
    Merge and prepare sales data from fact and dimension tables.
    
    Args:
        fact_sales: FactSales DataFrame
        dim_product: DimProduct DataFrame
        dim_date: DimDate DataFrame
    
    Returns:
        Merged and prepared sales DataFrame
    """
    try:
        # Create copies to avoid modifying original data
        sales = fact_sales.copy()
        products = dim_product[["ProductKey", "ProductName", "UnitPrice"]].copy()
        dates = dim_date.copy()
        
        # Ensure DateKey is string for merging
        dates["DateKey"] = pd.to_datetime(dates["DateKey"])
        sales["DateKey"] = pd.to_datetime(sales["DateKey"])

        # Merge with product information
        sales = sales.merge(
            products,
            left_on="ProductKey",
            right_on="ProductKey",
            how="left",
            suffixes=('', '_dim')
        )
        
        # Resolve column names when merging created duplicates
        if "UnitPrice_dim" in sales.columns:
            # Prefer the UnitPrice from DimProduct if conflicting
            sales["UnitPrice"] = sales["UnitPrice_dim"].fillna(sales.get("UnitPrice_x", sales.get("UnitPrice", 0)))
            sales = sales.drop(columns=["UnitPrice_dim", "UnitPrice_x", "UnitPrice_y"], errors="ignore")
        elif "UnitPrice_x" in sales.columns:
            sales["UnitPrice"] = sales["UnitPrice_x"]
            sales = sales.drop(columns=["UnitPrice_x", "UnitPrice_y"], errors="ignore")

        # Merge with date information
        sales = sales.merge(
            dates,
            left_on="DateKey",
            right_on="DateKey",
            how="left"
        )
        
        # Điền tên cho các sản phẩm không có trong DimProduct (như 915)
        sales["ProductName"] = sales["ProductName"].fillna("Unknown Product " + sales["ProductKey"].astype(str))

        # Sort by ProductKey and DateKey
        sales = sales.sort_values(by=["ProductKey", "DateKey"]).reset_index(drop=True)
        
        logger.info(f"Prepared sales data shape: {sales.shape}")
        
        return sales
    
    except Exception as e:
        logger.error(f"Error preparing sales data: {e}")
        raise


def aggregate_daily_sales(sales_data: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate sales data to daily level by product with exogenous variables.
    
    Args:
        sales_data: Prepared sales DataFrame
    
    Returns:
        Daily aggregated sales DataFrame with columns:
        - DateKey: Date
        - ProductKey: Product ID
        - ProductName: Product name
        - SalesQuantity: Total quantity sold
        - SalesAmount: Total sales amount
        - UnitPrice: Mean unit price
        - DiscountAmount: Total discount applied
    """
    try:
        daily_sales = sales_data.groupby(
            ["DateKey", "ProductKey", "ProductName"]
        ).agg({
            "SalesQuantity": "sum",
            "SalesAmount": "sum",
            "UnitPrice": "mean",
            "DiscountAmount": "sum"
        }).reset_index()
        
        # Handle missing DiscountAmount column gracefully
        if "DiscountAmount" not in daily_sales.columns:
            daily_sales["DiscountAmount"] = 0.0
        
        daily_sales = daily_sales.sort_values(
            by=["ProductKey", "DateKey"]
        ).reset_index(drop=True)
        
        logger.info(f"Aggregated daily sales shape: {daily_sales.shape}")
        logger.info(f"Columns: {daily_sales.columns.tolist()}")
        
        return daily_sales
    
    except Exception as e:
        logger.error(f"Error aggregating daily sales: {e}")
        raise


def get_product_time_series(
    daily_sales: pd.DataFrame,
    product_id: int,
    min_observations: int = 30
) -> Optional[pd.DataFrame]:
    """
    Extract time series for a specific product.
    
    Args:
        daily_sales: Daily aggregated sales DataFrame
        product_id: Product key/ID
        min_observations: Minimum number of observations required
    
    Returns:
        Time series DataFrame for the product, or None if insufficient data
    """
    try:
        product_ts = daily_sales[
            daily_sales["ProductKey"] == product_id
        ].copy().reset_index(drop=True)
        
        if len(product_ts) < min_observations:
            logger.warning(
                f"Product {product_id} has only {len(product_ts)} observations "
                f"(minimum required: {min_observations})"
            )
            return None
        
        return product_ts
    
    except Exception as e:
        logger.error(f"Error extracting product time series: {e}")
        raise


def load_product_time_series_from_db(product_id: int) -> pd.DataFrame:
    """Load one product daily time series from MySQL (offline + online merged)."""
    engine = get_engine()
    sql = text(
        f"""
        SELECT
            d.DateKey,
            d.ProductKey,
            COALESCE(p.ProductName, CONCAT('Unknown Product ', d.ProductKey)) AS ProductName,
            d.SalesQuantity,
            d.SalesAmount,
            COALESCE(p.UnitPrice, d.UnitPrice, 0) AS UnitPrice,
            d.DiscountAmount
        FROM (
            SELECT
                DATE(DateKey) AS DateKey,
                ProductKey,
                SUM(SalesQuantity) AS SalesQuantity,
                SUM(SalesAmount) AS SalesAmount,
                AVG(UnitPrice) AS UnitPrice,
                SUM(DiscountAmount) AS DiscountAmount
            FROM (
                {UNIFIED_FACT_SQL}
            ) f
            WHERE ProductKey = :product_id
            GROUP BY DATE(DateKey), ProductKey
        ) d
        LEFT JOIN DimProduct p ON p.ProductKey = d.ProductKey
        ORDER BY d.DateKey
        """
    )
    df = pd.read_sql_query(sql, engine, params={"product_id": product_id})
    if not df.empty:
        df["DateKey"] = pd.to_datetime(df["DateKey"])
    return df


def load_products_summary_from_db(limit: int = 10) -> pd.DataFrame:
    """Load product overview metrics directly from aggregated SQL."""
    engine = get_engine()
    sql = text(
        f"""
        WITH daily AS (
            SELECT
                DATE(DateKey) AS DateKey,
                ProductKey,
                SUM(SalesQuantity) AS SalesQuantity
            FROM (
                {UNIFIED_FACT_SQL}
            ) f
            GROUP BY DATE(DateKey), ProductKey
        )
        SELECT
            d.ProductKey,
            COALESCE(p.ProductName, CONCAT('Unknown Product ', d.ProductKey)) AS ProductName,
            SUM(d.SalesQuantity) AS total_quantity,
            AVG(d.SalesQuantity) AS avg_daily_quantity,
            MAX(d.SalesQuantity) AS max_daily_quantity
        FROM daily d
        LEFT JOIN DimProduct p ON p.ProductKey = d.ProductKey
        GROUP BY d.ProductKey, p.ProductName
        ORDER BY total_quantity DESC
        LIMIT :limit_val
        """
    )
    return pd.read_sql_query(sql, engine, params={"limit_val": limit})


def build_daily_snapshot_parquet(force_refresh: bool = False) -> Path:
    """Build and persist daily SKU demand snapshot to parquet for fast serving."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if DAILY_SNAPSHOT_FILE.exists() and not force_refresh:
        if get_snapshot_row_count() > 0:
            return DAILY_SNAPSHOT_FILE

    engine = get_engine()
    lookback_days = int(getattr(config, "PARQUET_LOOKBACK_DAYS", 730))

    with engine.connect() as conn:
        has_summary = bool(
            conn.execute(
                text(
                    """
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = DATABASE()
                      AND table_name = 'summary_daily_sales'
                    LIMIT 1
                    """
                )
            ).fetchone()
        )

    if has_summary:
        sql = text(
            f"""
            SELECT
                DATE(sds.DateKey) AS DateKey,
                sds.ProductKey,
                COALESCE(p.ProductName, CONCAT('Unknown Product ', sds.ProductKey)) AS ProductName,
                SUM(sds.total_sales_quantity) AS SalesQuantity,
                SUM(sds.total_sales_amount) AS SalesAmount,
                COALESCE(MAX(p.UnitPrice), 0) AS UnitPrice,
                0 AS DiscountAmount,
                MAX(COALESCE(sc.ProductSubcategoryKey, 0)) AS ProductSubcategoryKey,
                MAX(COALESCE(sc.ProductCategoryKey, 0)) AS ProductCategoryKey
            FROM summary_daily_sales sds
            LEFT JOIN DimProduct p ON p.ProductKey = sds.ProductKey
            LEFT JOIN DimProductSubcategory sc ON sc.ProductSubcategoryKey = p.ProductSubcategoryKey
            WHERE DATE(sds.DateKey) >= (
                SELECT DATE_SUB(MAX(DATE(DateKey)), INTERVAL {lookback_days} DAY)
                FROM summary_daily_sales
            )
            GROUP BY DATE(sds.DateKey), sds.ProductKey, COALESCE(p.ProductName, CONCAT('Unknown Product ', sds.ProductKey))
            """
        )
    else:
        sql = text(
            f"""
            SELECT
                DATE(f.DateKey) AS DateKey,
                f.ProductKey,
                COALESCE(p.ProductName, CONCAT('Unknown Product ', f.ProductKey)) AS ProductName,
                SUM(f.SalesQuantity) AS SalesQuantity,
                SUM(f.SalesAmount) AS SalesAmount,
                AVG(COALESCE(f.UnitPrice, p.UnitPrice, 0)) AS UnitPrice,
                SUM(COALESCE(f.DiscountAmount, 0)) AS DiscountAmount,
                MAX(COALESCE(s.ProductSubcategoryKey, 0)) AS ProductSubcategoryKey,
                MAX(COALESCE(s.ProductCategoryKey, 0)) AS ProductCategoryKey
            FROM (
                {UNIFIED_FACT_SQL}
            ) f
            LEFT JOIN DimProduct p ON p.ProductKey = f.ProductKey
            LEFT JOIN DimProductSubcategory s ON s.ProductSubcategoryKey = p.ProductSubcategoryKey
            WHERE DATE(f.DateKey) >= (
                SELECT DATE_SUB(MAX(DATE(u.DateKey)), INTERVAL {lookback_days} DAY)
                FROM (
                    {UNIFIED_FACT_SQL}
                ) u
            )
            GROUP BY DATE(f.DateKey), f.ProductKey, COALESCE(p.ProductName, CONCAT('Unknown Product ', f.ProductKey))
            """
        )

    snapshot_df = pd.read_sql_query(sql, engine)
    snapshot_df["DateKey"] = pd.to_datetime(snapshot_df["DateKey"])
    snapshot_df.to_parquet(DAILY_SNAPSHOT_FILE, index=False)
    _write_meta(snapshot_df)
    return DAILY_SNAPSHOT_FILE


def _write_meta(snapshot_df: pd.DataFrame) -> None:
    try:
        import json

        meta = {
            "rows": int(len(snapshot_df)),
            "generated_at": datetime.utcnow().isoformat(),
            "min_date": str(snapshot_df["DateKey"].min().date()) if not snapshot_df.empty else None,
            "max_date": str(snapshot_df["DateKey"].max().date()) if not snapshot_df.empty else None,
        }
        with open(META_FILE, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception:
        logger.warning("Could not write snapshot metadata", exc_info=True)


def get_snapshot_row_count() -> int:
    try:
        if META_FILE.exists():
            import json

            with open(META_FILE, "r", encoding="utf-8") as f:
                meta = json.load(f)
            return int(meta.get("rows", 0) or 0)

        if DAILY_SNAPSHOT_FILE.exists():
            df = pd.read_parquet(DAILY_SNAPSHOT_FILE, columns=["ProductKey"])
            return int(len(df))
    except Exception:
        logger.warning("Could not read snapshot row count", exc_info=True)

    return 0


def build_abc_xyz_snapshot(force_refresh: bool = False) -> Path:
    """Build ABC (revenue contribution) and XYZ (demand variability) segmentation snapshot."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if ABC_XYZ_FILE.exists() and not force_refresh:
        return ABC_XYZ_FILE

    if not DAILY_SNAPSHOT_FILE.exists() or force_refresh:
        build_daily_snapshot_parquet(force_refresh=force_refresh)

    df = pd.read_parquet(DAILY_SNAPSHOT_FILE)
    if df.empty:
        pd.DataFrame(columns=["ProductKey", "abc_class", "xyz_class", "revenue", "cv", "ProductCategoryKey"]).to_parquet(
            ABC_XYZ_FILE,
            index=False,
        )
        return ABC_XYZ_FILE

    revenue = (
        df.groupby("ProductKey", as_index=False)
        .agg(
            revenue=("SalesAmount", "sum"),
            demand_mean=("SalesQuantity", "mean"),
            demand_std=("SalesQuantity", "std"),
            ProductCategoryKey=("ProductCategoryKey", "max"),
        )
        .fillna({"demand_std": 0})
    )

    revenue = revenue.sort_values("revenue", ascending=False).reset_index(drop=True)
    total_rev = max(float(revenue["revenue"].sum()), 1.0)
    revenue["cum_share"] = revenue["revenue"].cumsum() / total_rev
    revenue["abc_class"] = np.select(
        [revenue["cum_share"] <= 0.8, revenue["cum_share"] <= 0.95], ["A", "B"], default="C"
    )

    revenue["cv"] = revenue["demand_std"] / revenue["demand_mean"].replace(0, np.nan)
    revenue["cv"] = revenue["cv"].replace([np.inf, -np.inf], np.nan).fillna(999.0)
    revenue["xyz_class"] = np.select(
        [revenue["cv"] <= 0.5, revenue["cv"] <= 1.0], ["X", "Y"], default="Z"
    )

    revenue.to_parquet(ABC_XYZ_FILE, index=False)
    return ABC_XYZ_FILE


def ensure_parquet_cache(force_refresh: bool = False) -> None:
    refresh_needed = force_refresh or get_snapshot_row_count() == 0
    build_daily_snapshot_parquet(force_refresh=refresh_needed)
    build_abc_xyz_snapshot(force_refresh=refresh_needed)


def load_product_time_series_from_parquet(product_id: int) -> pd.DataFrame:
    if not DAILY_SNAPSHOT_FILE.exists():
        ensure_parquet_cache(force_refresh=False)

    df = pd.read_parquet(DAILY_SNAPSHOT_FILE, filters=[("ProductKey", "==", int(product_id))])
    if not df.empty:
        df["DateKey"] = pd.to_datetime(df["DateKey"])
    return df.sort_values("DateKey").reset_index(drop=True)


def load_overview_from_parquet(horizon_days: int = 14) -> dict:
    if not DAILY_SNAPSHOT_FILE.exists() or not ABC_XYZ_FILE.exists():
        ensure_parquet_cache(force_refresh=False)

    df = pd.read_parquet(DAILY_SNAPSHOT_FILE, columns=["DateKey", "ProductKey", "SalesQuantity", "SalesAmount"])
    seg = pd.read_parquet(ABC_XYZ_FILE, columns=["ProductKey", "abc_class", "xyz_class"])

    if df.empty:
        return {
            "forecast_total_demand": 0,
            "sku_count": 0,
            "abc_distribution": {},
            "xyz_distribution": {},
            "avg_daily_demand": 0,
            "horizon_days": horizon_days,
        }

    df["DateKey"] = pd.to_datetime(df["DateKey"])
    last_day = df["DateKey"].max()
    start_28 = last_day - timedelta(days=27)
    recent = df[df["DateKey"] >= start_28]
    by_sku = recent.groupby("ProductKey", as_index=False).agg(mean_28=("SalesQuantity", "mean"))
    forecast_total = float(by_sku["mean_28"].sum() * horizon_days)

    abc_dist = seg["abc_class"].value_counts().to_dict()
    xyz_dist = seg["xyz_class"].value_counts().to_dict()
    return {
        "forecast_total_demand": round(forecast_total, 2),
        "sku_count": int(df["ProductKey"].nunique()),
        "abc_distribution": abc_dist,
        "xyz_distribution": xyz_dist,
        "avg_daily_demand": round(float(recent["SalesQuantity"].mean()), 4),
        "horizon_days": horizon_days,
        "last_data_date": str(last_day.date()),
    }


def load_alerts_from_parquet(limit: int = 20, abc_class: str = "A") -> list:
    if not DAILY_SNAPSHOT_FILE.exists() or not ABC_XYZ_FILE.exists():
        ensure_parquet_cache(force_refresh=False)

    df = pd.read_parquet(DAILY_SNAPSHOT_FILE)
    seg = pd.read_parquet(ABC_XYZ_FILE)

    if df.empty:
        return []

    df["DateKey"] = pd.to_datetime(df["DateKey"])
    last_day = df["DateKey"].max()

    recent_14 = df[df["DateKey"] >= (last_day - timedelta(days=13))]
    recent_90 = df[df["DateKey"] >= (last_day - timedelta(days=89))]

    d14 = recent_14.groupby(["ProductKey", "ProductName"], as_index=False).agg(mean14=("SalesQuantity", "mean"))
    d90 = recent_90.groupby(["ProductKey", "ProductName"], as_index=False).agg(mean90=("SalesQuantity", "mean"), std90=("SalesQuantity", "std"))
    merged = d14.merge(d90, on=["ProductKey", "ProductName"], how="left").fillna({"std90": 0, "mean90": 0})
    merged = merged.merge(seg[["ProductKey", "abc_class", "xyz_class"]], on="ProductKey", how="left")

    merged["spike_score"] = (merged["mean14"] - merged["mean90"]) / merged["std90"].replace(0, 1)
    class_scope = merged[merged["abc_class"] == abc_class]
    alerts = class_scope[class_scope["spike_score"] > 2.0]
    critical_mode = not alerts.empty
    if alerts.empty:
        # Fallback: still return top movers so Layer 2 is actionable even when
        # no SKU crosses critical spike threshold.
        alerts = class_scope.sort_values("spike_score", ascending=False).head(limit)
    else:
        alerts = alerts.sort_values("spike_score", ascending=False).head(limit)

    return [
        {
            "product_id": int(r["ProductKey"]),
            "product_name": r["ProductName"],
            "abc_class": r.get("abc_class", "C"),
            "xyz_class": r.get("xyz_class", "Z"),
            "mean_14": float(r["mean14"]),
            "mean_90": float(r["mean90"]),
            "spike_score": float(r["spike_score"]),
            "message": "Demand spike risk vs 3-month baseline" if critical_mode else "Top movers (no critical spike > 2.0)",
        }
        for _, r in alerts.iterrows()
    ]


def query_bulk_from_parquet(
    abc_class: Optional[str] = None,
    xyz_class: Optional[str] = None,
    category_key: Optional[int] = None,
    limit: int = 200,
) -> list:
    if not DAILY_SNAPSHOT_FILE.exists() or not ABC_XYZ_FILE.exists():
        ensure_parquet_cache(force_refresh=False)

    df = pd.read_parquet(DAILY_SNAPSHOT_FILE, columns=["ProductKey", "ProductName", "ProductCategoryKey"]).drop_duplicates(
        subset=["ProductKey"]
    )
    seg = pd.read_parquet(ABC_XYZ_FILE, columns=["ProductKey", "abc_class", "xyz_class", "revenue", "cv"])
    merged = df.merge(seg, on="ProductKey", how="left")

    if abc_class:
        merged = merged[merged["abc_class"] == abc_class]
    if xyz_class:
        merged = merged[merged["xyz_class"] == xyz_class]
    if category_key is not None:
        merged = merged[merged["ProductCategoryKey"] == category_key]

    merged = merged.sort_values("revenue", ascending=False).head(limit)
    return [
        {
            "product_id": int(r["ProductKey"]),
            "product_name": r["ProductName"],
            "category_key": int(r["ProductCategoryKey"]) if not pd.isna(r["ProductCategoryKey"]) else 0,
            "abc_class": r.get("abc_class", "C"),
            "xyz_class": r.get("xyz_class", "Z"),
            "revenue": float(r.get("revenue", 0.0)),
            "cv": float(r.get("cv", 999.0)),
        }
        for _, r in merged.iterrows()
    ]


def fill_missing_dates(
    product_ts: pd.DataFrame
) -> pd.DataFrame:
    """
    Fill missing dates in product time series with zero sales.
    
    Args:
        product_ts: Time series DataFrame for a product
    
    Returns:
        Time series with all dates and zero-filled missing values
    """
    try:
        # Set DateKey as index
        product_ts = product_ts.set_index("DateKey")
        
        # Create complete date range
        date_range = pd.date_range(
            start=product_ts.index.min(),
            end=product_ts.index.max(),
            freq="D"
        )
        
        # Reindex to include all dates
        product_ts = product_ts.reindex(date_range)
        product_ts["DateKey"] = product_ts.index
        
        # Fill missing values for target and exogenous variables
        product_ts["SalesQuantity"] = product_ts["SalesQuantity"].fillna(0)
        product_ts["SalesAmount"] = product_ts["SalesAmount"].fillna(0)
        product_ts["UnitPrice"] = product_ts["UnitPrice"].fillna(
            product_ts["UnitPrice"].mean()
        )
        product_ts["DiscountAmount"] = product_ts["DiscountAmount"].fillna(0)
        
        # Fill categorical columns
        product_ts["ProductKey"] = product_ts["ProductKey"].fillna(
            product_ts["ProductKey"].iloc[0]
        )
        product_ts["ProductName"] = product_ts["ProductName"].fillna(
            product_ts["ProductName"].iloc[0]
        )
        
        product_ts = product_ts.reset_index(drop=True)
        
        return product_ts
    
    except Exception as e:
        logger.error(f"Error filling missing dates: {e}")
        raise
