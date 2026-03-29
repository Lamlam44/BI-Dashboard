from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging
import time
import threading

import pandas as pd
from sqlalchemy import text

try:
    from db_utils import get_engine
except ImportError:
    from ..db_utils import get_engine

logger = logging.getLogger(__name__)


CACHE_DIR = Path(__file__).parent / "cache"
SALES_PROFIT_SNAPSHOT = CACHE_DIR / "sales_profit_daily_snapshot.parquet"
_BUILD_LOCK = threading.Lock()


def _to_date(date_key: Any) -> Optional[datetime]:
    if date_key is None:
        return None
    raw = str(date_key)
    if len(raw) != 8 or not raw.isdigit():
        return None
    try:
        return datetime.strptime(raw, "%Y%m%d")
    except ValueError:
        return None


def _parquet_has_data() -> bool:
    if not SALES_PROFIT_SNAPSHOT.exists() or SALES_PROFIT_SNAPSHOT.stat().st_size == 0:
        return False
    try:
        pd.read_parquet(SALES_PROFIT_SNAPSHOT)
        return True
    except Exception:
        return False


def _parse_dates(date_key_series: pd.Series) -> pd.Series:
    raw = date_key_series.astype("string").str.strip()

    # Path 1: parse date-like strings directly (for DATE/DATETIME values).
    parsed_direct = pd.to_datetime(raw, errors="coerce")

    # Path 2: fallback for numeric keys (e.g. 20240131 or 20240131.0).
    normalized_digits = (
        raw.str.replace(r"\.0+$", "", regex=True)
        .str.replace(r"\D", "", regex=True)
        .str[:8]
    )
    parsed_from_digits = pd.to_datetime(normalized_digits, format="%Y%m%d", errors="coerce")

    return parsed_direct.fillna(parsed_from_digits)


def _build_sales_profit_snapshot() -> pd.DataFrame:
    if not _BUILD_LOCK.acquire(blocking=False):
        logger.info("Snapshot build already in progress; skipping duplicate build")
        if _parquet_has_data():
            return pd.read_parquet(SALES_PROFIT_SNAPSHOT)
        return pd.DataFrame()

    started_at = time.perf_counter()
    try:
        logger.info("Building sales_profit snapshot from database...")
        engine = get_engine()
        query = text(
            """
            SELECT
                s.DateKey                   AS DateKey,
                CAST(s.StoreKey AS SIGNED)  AS StoreKey,
                COALESCE(ds.StoreName, CONCAT('Store ', s.StoreKey)) AS StoreName,
                SUM(s.total_sales_amount)
                  - COALESCE(SUM(s.total_return_amount), 0)
                  - COALESCE(SUM(s.total_discount_amount), 0) AS total_sales,
                SUM(s.total_sales_quantity * p.UnitCost)   AS total_cost,
                SUM(s.total_sales_amount)
                  - COALESCE(SUM(s.total_return_amount), 0)
                  - COALESCE(SUM(s.total_discount_amount), 0)
                  - SUM(s.total_sales_quantity * p.UnitCost) AS gross_profit,
                CASE
                    WHEN SUM(s.total_sales_amount)
                         - COALESCE(SUM(s.total_return_amount), 0)
                         - COALESCE(SUM(s.total_discount_amount), 0) = 0 THEN 0
                    ELSE (SUM(s.total_sales_amount)
                          - COALESCE(SUM(s.total_return_amount), 0)
                          - COALESCE(SUM(s.total_discount_amount), 0)
                          - SUM(s.total_sales_quantity * p.UnitCost))
                         / (SUM(s.total_sales_amount)
                            - COALESCE(SUM(s.total_return_amount), 0)
                            - COALESCE(SUM(s.total_discount_amount), 0))
                END AS profit_margin
            FROM summary_daily_sales s
            LEFT JOIN DimStore ds  ON ds.StoreKey = s.StoreKey
            LEFT JOIN DimProduct p ON p.ProductKey = s.ProductKey
            GROUP BY s.DateKey, s.StoreKey, StoreName
            ORDER BY s.DateKey
            """
        )

        with engine.connect() as conn:
            df = pd.read_sql(query, conn)

        logger.info(f"Query returned {len(df)} rows")

        if df.empty:
            logger.warning("Query returned empty DataFrame, no cache created")
            return df

        df["Date"] = _parse_dates(df["DateKey"])
        df = df.dropna(subset=["Date"]).copy()

        if df.empty:
            logger.warning("All DateKey values failed parsing; cache file will not be overwritten with empty data")
            return df

        logger.info(f"Processing {len(df)} rows, creating cache...")
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(SALES_PROFIT_SNAPSHOT, index=False)
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        logger.info(f"Cache created at {SALES_PROFIT_SNAPSHOT} with {len(df)} rows in {elapsed_ms:.2f} ms")
        return df
    finally:
        _BUILD_LOCK.release()


def load_sales_profit_snapshot(force_refresh: bool = False) -> pd.DataFrame:
    # Read existing parquet when it is readable to avoid repeated heavy DB rebuilds.
    if not force_refresh and _parquet_has_data():
        return pd.read_parquet(SALES_PROFIT_SNAPSHOT)

    # If a rebuild is already running, return current cached snapshot (if any)
    # so API can still respond quickly.
    if not force_refresh and _BUILD_LOCK.locked() and SALES_PROFIT_SNAPSHOT.exists():
        try:
            return pd.read_parquet(SALES_PROFIT_SNAPSHOT)
        except Exception:
            pass

    return _build_sales_profit_snapshot()


def get_sales_profit_dashboard(start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
    snapshot = load_sales_profit_snapshot(force_refresh=False)
    if snapshot.empty:
        return {
            "status": "empty",
            "message": "No sales/profit data found.",
            "ytd": 0.0,
            "mtd": 0.0,
            "total": 0.0,
            "ytd_profit": 0.0,
            "mtd_profit": 0.0,
            "total_profit": 0.0,
            "avg_profit_margin": 0.0,
            "trend": {"labels": [], "data": []},
            "profit_trend": {"labels": [], "data": []},
            "store_pie": {"labels": [], "data": []},
            "last_updated": None,
        }

    df = snapshot.copy()
    if "Date" not in df.columns:
        df["Date"] = _parse_dates(df["DateKey"])
    df = df.dropna(subset=["Date"])

    if start_date:
        df = df[df["Date"] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df["Date"] <= pd.to_datetime(end_date)]

    if df.empty:
        return {
            "status": "empty",
            "message": "No data found for selected date range.",
            "ytd": 0.0,
            "mtd": 0.0,
            "total": 0.0,
            "ytd_profit": 0.0,
            "mtd_profit": 0.0,
            "total_profit": 0.0,
            "avg_profit_margin": 0.0,
            "trend": {"labels": [], "data": []},
            "profit_trend": {"labels": [], "data": []},
            "store_pie": {"labels": [], "data": []},
            "last_updated": None,
        }

    daily = (
        df.groupby("Date", as_index=False)[["total_sales", "gross_profit", "total_cost"]]
        .sum()
        .sort_values("Date")
    )

    max_date = daily["Date"].max()
    ytd_mask = daily["Date"].dt.year == max_date.year
    mtd_mask = ytd_mask & (daily["Date"].dt.month == max_date.month)

    ytd = float(daily.loc[ytd_mask, "total_sales"].sum())
    mtd = float(daily.loc[mtd_mask, "total_sales"].sum())
    total = float(daily["total_sales"].sum())

    ytd_profit = float(daily.loc[ytd_mask, "gross_profit"].sum())
    mtd_profit = float(daily.loc[mtd_mask, "gross_profit"].sum())
    total_profit = float(daily["gross_profit"].sum())
    avg_profit_margin = (total_profit / total) if total else 0.0

    # ── YoY / MoM comparison ─────────────────────────────────────
    prev_year = max_date.year - 1
    prev_ytd_mask = daily["Date"].dt.year == prev_year
    prev_ytd = float(daily.loc[prev_ytd_mask, "total_sales"].sum())
    yoy_growth = ((ytd - prev_ytd) / prev_ytd * 100) if prev_ytd else 0.0

    current_month = max_date.month
    current_year = max_date.year
    if current_month == 1:
        prev_m_year, prev_m_month = current_year - 1, 12
    else:
        prev_m_year, prev_m_month = current_year, current_month - 1
    prev_mtd_mask = (daily["Date"].dt.year == prev_m_year) & (daily["Date"].dt.month == prev_m_month)
    prev_mtd = float(daily.loc[prev_mtd_mask, "total_sales"].sum())
    mom_growth = ((mtd - prev_mtd) / prev_mtd * 100) if prev_mtd else 0.0

    # ── Monthly aggregation for trend ────────────────────────────
    monthly = (
        df.assign(month=df["Date"].dt.to_period("M"))
        .groupby("month", as_index=False)[["total_sales", "gross_profit"]]
        .sum()
        .sort_values("month")
    )
    monthly["month_str"] = monthly["month"].astype(str)

    store = (
        df.groupby("StoreName", as_index=False)["total_sales"]
        .sum()
        .sort_values("total_sales", ascending=False)
        .head(10)
    )

    return {
        "status": "success",
        "ytd": ytd,
        "mtd": mtd,
        "total": total,
        "ytd_profit": ytd_profit,
        "mtd_profit": mtd_profit,
        "total_profit": total_profit,
        "avg_profit_margin": float(avg_profit_margin),
        "yoy_growth": round(yoy_growth, 2),
        "mom_growth": round(mom_growth, 2),
        "trend": {
            "labels": monthly["month_str"].tolist(),
            "data": monthly["total_sales"].astype(float).tolist(),
        },
        "profit_trend": {
            "labels": monthly["month_str"].tolist(),
            "data": monthly["gross_profit"].astype(float).tolist(),
        },
        "store_pie": {
            "labels": store["StoreName"].astype(str).tolist(),
            "data": store["total_sales"].astype(float).tolist(),
        },
        "last_updated": max_date.strftime("%Y-%m-%d"),
    }


def get_channel_breakdown(start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
    """Revenue split between offline and online channels (from pre-aggregated table)."""
    engine = get_engine()

    query = text("SELECT channel, revenue, profit, transactions FROM agg_channel_summary")

    with engine.connect() as conn:
        df = pd.read_sql(query, conn)

    df = df.fillna(0)
    total_rev = float(df["revenue"].sum())
    rows = []
    for _, r in df.iterrows():
        rev = float(r["revenue"])
        rows.append({
            "channel": r["channel"],
            "revenue": rev,
            "profit": float(r["profit"]),
            "transactions": int(r["transactions"]),
            "share_pct": round((rev / total_rev * 100) if total_rev else 0, 2),
        })
    return {"status": "success", "channels": rows, "total_revenue": total_rev}


def get_kpi_summary() -> Dict[str, Any]:
    """Return pre-computed KPI summary from aggregate table (fallback to live query)."""
    engine = get_engine()
    try:
        query = text("SELECT kpi_key, kpi_value FROM agg_kpi_summary ORDER BY kpi_key")
        with engine.connect() as conn:
            df = pd.read_sql(query, conn)
        if not df.empty:
            kpis = {row["kpi_key"]: float(row["kpi_value"]) for _, row in df.iterrows()}
            return {"status": "success", "source": "aggregate", "kpis": kpis}
    except Exception:
        pass

    # Fallback: compute live from snapshot
    snapshot = load_sales_profit_snapshot(force_refresh=False)
    if snapshot.empty:
        return {"status": "empty", "kpis": {}}

    total_rev = float(snapshot["total_sales"].sum())
    total_cost = float(snapshot["total_cost"].sum())
    total_profit = total_rev - total_cost
    n_stores = int(snapshot["StoreKey"].nunique())

    return {
        "status": "success",
        "source": "live",
        "kpis": {
            "total_revenue": total_rev,
            "total_profit": total_profit,
            "gross_margin": round((total_profit / total_rev * 100) if total_rev else 0, 2),
            "active_stores": n_stores,
        },
    }


def refresh_sales_profit_cache() -> Dict[str, Any]:
    snapshot = load_sales_profit_snapshot(force_refresh=True)
    return {
        "status": "success" if not snapshot.empty else "empty",
        "rows": int(len(snapshot)),
        "parquet_file": str(SALES_PROFIT_SNAPSHOT),
    }


def get_sales_per_sqft(start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
    """VĐ-2: Sales per Square Foot by store."""
    engine = get_engine()
    params: Dict[str, Any] = {}
    where = "1=1"
    if start_date:
        where += " AND s.DateKey >= :start_date"
        params["start_date"] = start_date
    if end_date:
        where += " AND s.DateKey <= :end_date"
        params["end_date"] = end_date

    query = text(f"""
        SELECT
            ds.StoreKey,
            ds.StoreName,
            ds.SellingAreaSize,
            SUM(s.total_sales_amount)
              - COALESCE(SUM(s.total_return_amount), 0)
              - COALESCE(SUM(s.total_discount_amount), 0) AS net_sales,
            CASE WHEN ds.SellingAreaSize > 0
                 THEN (SUM(s.total_sales_amount)
                       - COALESCE(SUM(s.total_return_amount), 0)
                       - COALESCE(SUM(s.total_discount_amount), 0)) / ds.SellingAreaSize
                 ELSE 0
            END AS sales_per_sqft
        FROM summary_daily_sales s
        JOIN DimStore ds ON ds.StoreKey = s.StoreKey
        WHERE {where} AND ds.SellingAreaSize > 0
        GROUP BY ds.StoreKey, ds.StoreName, ds.SellingAreaSize
        ORDER BY sales_per_sqft DESC
    """)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params=params)

    if df.empty:
        return {"status": "empty", "stores": [], "avg_sales_per_sqft": 0}

    stores = []
    for _, r in df.iterrows():
        stores.append({
            "store_key": int(r["StoreKey"]),
            "store_name": str(r["StoreName"]),
            "selling_area_size": int(r["SellingAreaSize"]),
            "net_sales": float(r["net_sales"]),
            "sales_per_sqft": round(float(r["sales_per_sqft"]), 2),
        })

    avg = float(df["sales_per_sqft"].mean())
    return {"status": "success", "stores": stores, "avg_sales_per_sqft": round(avg, 2)}


def get_budget_vs_actual(start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
    """VĐ-8: Budget vs Actual from FactSalesQuota vs summary_daily_sales."""
    engine = get_engine()
    params: Dict[str, Any] = {}
    where_actual = "1=1"
    where_quota = "1=1"
    if start_date:
        where_actual += " AND s.DateKey >= :start_date"
        where_quota += " AND q.DateKey >= :start_date"
        params["start_date"] = start_date
    if end_date:
        where_actual += " AND s.DateKey <= :end_date"
        where_quota += " AND q.DateKey <= :end_date"
        params["end_date"] = end_date

    query = text(f"""
        SELECT
            a.StoreKey,
            ds.StoreName,
            a.actual_sales,
            COALESCE(b.budget_sales, 0) AS budget_sales,
            CASE WHEN COALESCE(b.budget_sales, 0) > 0
                 THEN (a.actual_sales / b.budget_sales) * 100
                 ELSE 0
            END AS attainment_pct
        FROM (
            SELECT s.StoreKey,
                   SUM(s.total_sales_amount)
                     - COALESCE(SUM(s.total_return_amount), 0)
                     - COALESCE(SUM(s.total_discount_amount), 0) AS actual_sales
            FROM summary_daily_sales s
            WHERE {where_actual}
            GROUP BY s.StoreKey
        ) a
        LEFT JOIN (
            SELECT q.StoreKey, SUM(q.SalesAmountQuota) AS budget_sales
            FROM FactSalesQuota q
            WHERE {where_quota}
            GROUP BY q.StoreKey
        ) b ON b.StoreKey = a.StoreKey
        LEFT JOIN DimStore ds ON ds.StoreKey = a.StoreKey
        ORDER BY attainment_pct DESC
    """)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params=params)

    if df.empty:
        return {"status": "empty", "stores": [], "overall_attainment": 0}

    stores = []
    for _, r in df.iterrows():
        stores.append({
            "store_key": int(r["StoreKey"]),
            "store_name": str(r["StoreName"] or f"Store {r['StoreKey']}"),
            "actual_sales": float(r["actual_sales"]),
            "budget_sales": float(r["budget_sales"]),
            "attainment_pct": round(float(r["attainment_pct"]), 2),
        })

    total_actual = float(df["actual_sales"].sum())
    total_budget = float(df["budget_sales"].sum())
    overall = round((total_actual / total_budget * 100) if total_budget else 0, 2)

    return {"status": "success", "stores": stores, "overall_attainment": overall}
