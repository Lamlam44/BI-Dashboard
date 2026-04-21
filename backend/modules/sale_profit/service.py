from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import logging
import time
import threading

import pandas as pd
from sqlalchemy import text

from core.database import get_engine

logger = logging.getLogger(__name__)


CACHE_DIR = Path(__file__).parent / "cache"
SALES_PROFIT_SNAPSHOT = CACHE_DIR / "sales_profit_daily_snapshot.parquet"
_BUILD_LOCK = threading.Lock()

# ── Simple TTL cache for heavy direct-DB queries ──────────────
_SIMPLE_CACHE: Dict[str, Tuple[float, Any]] = {}
_SIMPLE_CACHE_LOCK = threading.Lock()
_SIMPLE_CACHE_TTL = 600  # 10 minutes


def _simple_cache_get(key: str) -> Optional[Any]:
    with _SIMPLE_CACHE_LOCK:
        entry = _SIMPLE_CACHE.get(key)
        if entry and time.time() - entry[0] < _SIMPLE_CACHE_TTL:
            return entry[1]
    return None


def _simple_cache_set(key: str, value: Any) -> None:
    with _SIMPLE_CACHE_LOCK:
        _SIMPLE_CACHE[key] = (time.time(), value)


def clear_all_caches() -> None:
    """Clear in-memory TTL cache so next request fetches fresh data."""
    with _SIMPLE_CACHE_LOCK:
        _SIMPLE_CACHE.clear()


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
                SUM(s.total_sales_amount
                  - COALESCE(s.total_return_amount, 0)
                  - COALESCE(s.total_discount_amount, 0)) AS total_sales,
                SUM(COALESCE(s.total_cost, 0))            AS total_cost,
                SUM(s.total_sales_amount
                  - COALESCE(s.total_return_amount, 0)
                  - COALESCE(s.total_discount_amount, 0))
                  - SUM(COALESCE(s.total_cost, 0))        AS gross_profit,
                CASE
                    WHEN SUM(s.total_sales_amount
                         - COALESCE(s.total_return_amount, 0)
                         - COALESCE(s.total_discount_amount, 0)) = 0 THEN 0
                    ELSE (SUM(s.total_sales_amount
                          - COALESCE(s.total_return_amount, 0)
                          - COALESCE(s.total_discount_amount, 0))
                          - SUM(COALESCE(s.total_cost, 0)))
                         / SUM(s.total_sales_amount
                            - COALESCE(s.total_return_amount, 0)
                            - COALESCE(s.total_discount_amount, 0))
                END AS profit_margin
            FROM summary_daily_sales s
            LEFT JOIN DimStore ds ON ds.StoreKey = s.StoreKey
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


def get_sales_profit_dashboard(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    store_key: Optional[int] = None,
    rls_store_keys: Optional[List[int]] = None,
) -> Dict[str, Any]:
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

    # RLS filter
    if rls_store_keys is not None:
        df = df[df["StoreKey"].isin(rls_store_keys)]
    if store_key is not None:
        df = df[df["StoreKey"] == store_key]

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

    # â”€â”€ YoY / MoM comparison â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

    # â”€â”€ Monthly aggregation for trend â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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


def get_channel_breakdown(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    rls_store_keys: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Revenue split between offline and online channels.
    When date filters are provided, queries live from fact tables.
    Otherwise falls back to pre-aggregated agg_channel_summary.
    """
    engine = get_engine()

    if start_date or end_date or rls_store_keys is not None:
        # Live query with date filter / RLS
        params: Dict[str, Any] = {}
        where_offline = "1=1"
        where_online = "1=1"
        if start_date:
            where_offline += " AND s.DateKey >= :start_date"
            where_online += " AND o.DateKey >= :start_date"
            params["start_date"] = start_date
        if end_date:
            where_offline += " AND s.DateKey <= :end_date"
            where_online += " AND o.DateKey <= :end_date"
            params["end_date"] = end_date
        if rls_store_keys is not None:
            keys_csv = ",".join(str(k) for k in rls_store_keys) if rls_store_keys else "0"
            where_offline += f" AND s.StoreKey IN ({keys_csv})"
            where_online += f" AND o.StoreKey IN ({keys_csv})"

        query = text(f"""
            SELECT 'Offline' AS channel,
                   SUM(s.total_sales_amount) AS revenue,
                   SUM(s.total_sales_amount) - SUM(s.total_sales_quantity * p.UnitCost) AS profit,
                   SUM(s.total_sales_quantity) AS transactions
            FROM summary_daily_sales s
            LEFT JOIN DimProduct p ON p.ProductKey = s.ProductKey
            WHERE {where_offline}
            UNION ALL
            SELECT 'Online' AS channel,
                   SUM(o.SalesAmount) AS revenue,
                   SUM(o.SalesAmount) - SUM(o.SalesQuantity * p.UnitCost) AS profit,
                   SUM(o.SalesQuantity) AS transactions
            FROM FactOnlineSales o
            LEFT JOIN DimProduct p ON p.ProductKey = o.ProductKey
            WHERE {where_online}
        """)
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params=params)
    else:
        # No filter â€” use pre-aggregated table (fast path)
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


def get_kpi_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    rls_store_keys: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Return KPI summary.
    - Without filters: uses pre-aggregated agg_kpi_summary (fast).
    - With date/RLS filter: queries summary_daily_sales+DimProduct for revenue/cost/margin
      and FactOnlineSales for unique_customers. Metrics that require full FactSales scan
      (total_transactions, avg_transaction_value, avg_basket_size) are omitted because
      they cannot be computed accurately in acceptable time on the filtered dataset.
    """
    engine = get_engine()

    if start_date or end_date or rls_store_keys is not None:
        cache_key = f"kpi_filtered|{start_date}|{end_date}|{sorted(rls_store_keys) if rls_store_keys else None}"
        cached = _simple_cache_get(cache_key)
        if cached is not None:
            return cached

        where = "1=1"
        params: Dict[str, Any] = {}
        if start_date:
            where += " AND sds.DateKey >= :start_date"
            params["start_date"] = start_date
        if end_date:
            where += " AND sds.DateKey <= :end_date"
            params["end_date"] = end_date
        if rls_store_keys is not None:
            keys_csv = ",".join(str(k) for k in rls_store_keys) if rls_store_keys else "0"
            where += f" AND sds.StoreKey IN ({keys_csv})"

        q_main = text(f"""
            SELECT
                SUM(sds.total_sales_amount
                    - COALESCE(sds.total_return_amount, 0)
                    - COALESCE(sds.total_discount_amount, 0))     AS net_sales,
                SUM(sds.total_sales_quantity * COALESCE(p.UnitCost, 0)) AS total_cost,
                COUNT(DISTINCT sds.ProductKey)                    AS product_count,
                COUNT(DISTINCT sds.StoreKey)                      AS active_stores
            FROM summary_daily_sales sds
            LEFT JOIN DimProduct p ON p.ProductKey = sds.ProductKey
            WHERE {where}
        """)

        where_online = "CustomerKey IS NOT NULL"
        params_online: Dict[str, Any] = {}
        if start_date:
            where_online += " AND DateKey >= :start_date"
            params_online["start_date"] = start_date
        if end_date:
            where_online += " AND DateKey <= :end_date"
            params_online["end_date"] = end_date

        q_customers = text(f"""
            SELECT COUNT(DISTINCT CustomerKey) AS unique_customers
            FROM FactOnlineSales
            WHERE {where_online}
        """)

        try:
            with engine.connect() as conn:
                row = conn.execute(q_main, params).mappings().first()
                cust_row = conn.execute(q_customers, params_online).mappings().first()
        except Exception as exc:
            logger.warning("get_kpi_summary filtered query failed: %s", exc)
            return {"status": "empty", "source": "live", "kpis": {}}

        if not row or row["net_sales"] is None:
            return {"status": "empty", "source": "live", "kpis": {}}

        net_sales = float(row["net_sales"] or 0)
        total_cost = float(row["total_cost"] or 0)
        gross_profit = net_sales - total_cost
        gross_margin = round((gross_profit / net_sales * 100) if net_sales else 0, 2)

        result = {
            "status": "success",
            "source": "live",
            "kpis": {
                "total_revenue":    net_sales,
                "total_profit":     gross_profit,
                "gross_margin":     gross_margin,
                "active_stores":    int(row["active_stores"] or 0),
                "product_count":    int(row["product_count"] or 0),
                "unique_customers": int(cust_row["unique_customers"] or 0) if cust_row else 0,
            },
        }
        _simple_cache_set(cache_key, result)
        return result

    # No filter -- use pre-aggregated table for speed
    try:
        query = text("SELECT kpi_key, kpi_value FROM agg_kpi_summary ORDER BY kpi_key")
        with engine.connect() as conn:
            df = pd.read_sql(query, conn)
        if not df.empty:
            kpis = {row["kpi_key"]: float(row["kpi_value"]) for _, row in df.iterrows()}
            return {"status": "success", "source": "aggregate", "kpis": kpis}
    except Exception:
        pass

    return {"status": "empty", "kpis": {}}


def refresh_sales_profit_cache() -> Dict[str, Any]:
    snapshot = load_sales_profit_snapshot(force_refresh=True)
    return {
        "status": "success" if not snapshot.empty else "empty",
        "rows": int(len(snapshot)),
        "parquet_file": str(SALES_PROFIT_SNAPSHOT),
    }


def micro_refresh_parquet(date_keys: Optional[List[str]] = None) -> pd.DataFrame:
    """Fast incremental parquet update using PyArrow — for Micro-ETL after invoice ingest.

    Instead of rebuilding the full snapshot from the DB, this function:
      1. Loads the existing parquet with PyArrow (fast columnar I/O).
      2. Removes rows whose DateKey falls in *date_keys* (those need fresh values).
      3. Queries ONLY those dates from summary_daily_sales (tiny result set).
      4. Combines the filtered base with the fresh delta.
      5. Writes back using PyArrow/Snappy (faster than pandas for large files).

    Falls back to a full rebuild when the parquet doesn't exist yet or date_keys is empty.
    """
    import pyarrow as pa  # noqa: F401 — already in requirements.txt
    import pyarrow.parquet as pq

    if not date_keys or not _parquet_has_data():
        return _build_sales_profit_snapshot()

    # If full rebuild is already running, skip rather than race.
    if _BUILD_LOCK.locked():
        try:
            return pd.read_parquet(SALES_PROFIT_SNAPSHOT)
        except Exception:
            return pd.DataFrame()

    if not _BUILD_LOCK.acquire(blocking=False):
        try:
            return pd.read_parquet(SALES_PROFIT_SNAPSHOT)
        except Exception:
            return pd.DataFrame()

    started_at = time.perf_counter()
    try:
        # ── Step 1: load existing parquet with PyArrow ──────────────────
        existing_table = pq.read_table(str(SALES_PROFIT_SNAPSHOT))
        existing_df = existing_table.to_pandas()

        if "Date" not in existing_df.columns:
            existing_df["Date"] = _parse_dates(existing_df["DateKey"])

        # Normalise supplied date_keys → datetime.date for comparison.
        date_set = set()
        for dk in date_keys:
            try:
                date_set.add(pd.to_datetime(dk).date())
            except Exception:
                pass

        if not date_set:
            return existing_df

        # ── Step 2: keep rows that are NOT in the refresh window ─────────
        base_df = existing_df[~existing_df["Date"].dt.date.isin(date_set)].copy()

        # ── Step 3: query only the affected dates from DB ────────────────
        engine = get_engine()
        # Use parameterised IN via a CTE-style UNION to avoid injection risk.
        date_filter_union = " UNION ALL ".join(
            f"SELECT CAST('{d}' AS DATE) AS d" for d in sorted(date_set)
        )
        query = text(f"""
            SELECT
                s.DateKey                   AS DateKey,
                CAST(s.StoreKey AS SIGNED)  AS StoreKey,
                COALESCE(ds.StoreName, CONCAT('Store ', s.StoreKey)) AS StoreName,
                SUM(s.total_sales_amount
                  - COALESCE(s.total_return_amount, 0)
                  - COALESCE(s.total_discount_amount, 0)) AS total_sales,
                SUM(COALESCE(s.total_cost, 0))            AS total_cost,
                SUM(s.total_sales_amount
                  - COALESCE(s.total_return_amount, 0)
                  - COALESCE(s.total_discount_amount, 0))
                  - SUM(COALESCE(s.total_cost, 0))        AS gross_profit,
                CASE
                    WHEN SUM(s.total_sales_amount
                         - COALESCE(s.total_return_amount, 0)
                         - COALESCE(s.total_discount_amount, 0)) = 0 THEN 0
                    ELSE (SUM(s.total_sales_amount
                          - COALESCE(s.total_return_amount, 0)
                          - COALESCE(s.total_discount_amount, 0))
                          - SUM(COALESCE(s.total_cost, 0)))
                         / SUM(s.total_sales_amount
                            - COALESCE(s.total_return_amount, 0)
                            - COALESCE(s.total_discount_amount, 0))
                END AS profit_margin
            FROM summary_daily_sales s
            JOIN ({date_filter_union}) _dates ON DATE(s.DateKey) = _dates.d
            LEFT JOIN DimStore ds ON ds.StoreKey = s.StoreKey
            GROUP BY s.DateKey, s.StoreKey, StoreName
            ORDER BY s.DateKey
        """)

        with engine.connect() as conn:
            delta_df = pd.read_sql(query, conn)

        if delta_df.empty:
            logger.info("micro_refresh_parquet: no delta rows for %s", date_keys)
            return existing_df

        delta_df["Date"] = _parse_dates(delta_df["DateKey"])
        delta_df = delta_df.dropna(subset=["Date"])

        # ── Step 4: combine base + delta ─────────────────────────────────
        combined_df = pd.concat([base_df, delta_df], ignore_index=True)
        combined_df = combined_df.sort_values("Date").reset_index(drop=True)

        # ── Step 5: write back with PyArrow/Snappy ───────────────────────
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        out_table = pa.Table.from_pandas(combined_df, preserve_index=False)
        pq.write_table(out_table, str(SALES_PROFIT_SNAPSHOT), compression="snappy")

        elapsed_ms = (time.perf_counter() - started_at) * 1000
        logger.info(
            "micro_refresh_parquet: wrote %d rows (delta %d rows for %s) in %.1f ms",
            len(combined_df), len(delta_df), date_keys, elapsed_ms,
        )
        _simple_cache_set("sales_profit_snapshot", combined_df)
        return combined_df

    except Exception as exc:
        logger.warning("micro_refresh_parquet failed (%s); falling back to full rebuild", exc)
        return _build_sales_profit_snapshot()
    finally:
        _BUILD_LOCK.release()


def get_sales_per_sqft(
    start_date=None,
    end_date=None,
    rls_store_keys=None,
):
    """Sales per Square Foot by store."""
    cache_key = f"sales_per_sqft|{start_date}|{end_date}|{sorted(rls_store_keys) if rls_store_keys else None}"
    cached = _simple_cache_get(cache_key)
    if cached is not None:
        return cached
    engine = get_engine()
    params = {}

    if not start_date and not end_date:
        where = "1=1"
        if rls_store_keys is not None:
            keys_csv = ",".join(str(k) for k in rls_store_keys) if rls_store_keys else "0"
            where += f" AND agg.StoreKey IN ({keys_csv})"
        query = text(f"""
            SELECT
                ds.StoreKey,
                ds.StoreName,
                ds.SellingAreaSize,
                (agg.total_sales - agg.total_returns - agg.total_discounts) AS net_sales,
                CASE WHEN ds.SellingAreaSize > 0
                     THEN (agg.total_sales - agg.total_returns - agg.total_discounts) / ds.SellingAreaSize
                     ELSE 0
                END AS sales_per_sqft
            FROM agg_sales_by_store agg
            JOIN DimStore ds ON ds.StoreKey = agg.StoreKey
            WHERE {where} AND ds.SellingAreaSize > 0
            ORDER BY sales_per_sqft DESC
        """)
    else:
        where = "1=1"
        if start_date:
            where += " AND s.DateKey >= :start_date"
            params["start_date"] = start_date
        if end_date:
            where += " AND s.DateKey <= :end_date"
            params["end_date"] = end_date
        if rls_store_keys is not None:
            keys_csv = ",".join(str(k) for k in rls_store_keys) if rls_store_keys else "0"
            where += f" AND s.StoreKey IN ({keys_csv})"
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
    result = {"status": "success", "stores": stores, "avg_sales_per_sqft": round(avg, 2)}
    _simple_cache_set(cache_key, result)
    return result


def get_budget_vs_actual(
    start_date=None,
    end_date=None,
    rls_store_keys=None,
):
    """Budget vs Actual from FactSalesQuota vs summary_daily_sales."""
    cache_key = f"budget_vs_actual|{start_date}|{end_date}|{sorted(rls_store_keys) if rls_store_keys else None}"
    cached = _simple_cache_get(cache_key)
    if cached is not None:
        return cached
    engine = get_engine()
    params = {}

    if not start_date and not end_date:
        where_actual = "1=1"
        where_quota = "1=1"
        if rls_store_keys is not None:
            keys_csv = ",".join(str(k) for k in rls_store_keys) if rls_store_keys else "0"
            where_actual += f" AND agg.StoreKey IN ({keys_csv})"
            where_quota += f" AND q.StoreKey IN ({keys_csv})"
        query = text(f"""
            SELECT
                agg.StoreKey,
                ds.StoreName,
                (agg.total_sales - agg.total_returns - agg.total_discounts) AS actual_sales,
                COALESCE(b.budget_sales, 0) AS budget_sales,
                CASE WHEN COALESCE(b.budget_sales, 0) > 0
                     THEN ((agg.total_sales - agg.total_returns - agg.total_discounts) / b.budget_sales) * 100
                     ELSE 0
                END AS attainment_pct
            FROM agg_sales_by_store agg
            LEFT JOIN (
                SELECT q.StoreKey, SUM(q.SalesAmountQuota) AS budget_sales
                FROM FactSalesQuota q
                WHERE {where_quota}
                GROUP BY q.StoreKey
            ) b ON b.StoreKey = agg.StoreKey
            LEFT JOIN DimStore ds ON ds.StoreKey = agg.StoreKey
            WHERE {where_actual}
            ORDER BY attainment_pct DESC
        """)
    else:
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
        if rls_store_keys is not None:
            keys_csv = ",".join(str(k) for k in rls_store_keys) if rls_store_keys else "0"
            where_actual += f" AND s.StoreKey IN ({keys_csv})"
            where_quota += f" AND q.StoreKey IN ({keys_csv})"
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

    result = {"status": "success", "stores": stores, "overall_attainment": overall}
    _simple_cache_set(cache_key, result)
    return result
