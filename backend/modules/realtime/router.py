"""
Realtime Metrics - DW-backed Near Real-Time Dashboard.

Design:
  1. A background thread polls the BI Data Warehouse (retails_dataset) every
     DW_POLL_INTERVAL seconds and writes results to a Global Singleton dict.
  2. ALL SSE clients and REST endpoints read from the singleton -
     zero per-client DB queries (no thundering herd on MySQL).
  3. Data freshness: at most DW_POLL_INTERVAL seconds behind reality.
  4. Single Source of Truth: all numbers come from the same DW tables
     as the historical dashboard, so numbers are always consistent.

DW tables used:
  - v_total_sales         - UNION of FactSales + FactOnlineSales (today transactions)
  - summary_daily_sales   - pre-aggregated daily totals (30-day trend)
  - DimStore              - store names
  - DimProduct            - product names / brands
  - DimEmployee           - employee names / titles
  - agg_inventory_metrics - monthly inventory health (Turnover, Days-of-Supply)
  - DimPromotion          - promotion names / discount percentages
"""

import asyncio
import json
import logging
import threading
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from core.database import get_engine

logger = logging.getLogger(__name__)

# ── Poll interval constants ───────────────────────────────────
DW_POLL_INTERVAL: int = 15   # background thread refreshes every 15 seconds

# =============================================================
# Global Singleton Snapshot
# =============================================================
# One dict holding the latest metrics for every realtime endpoint.
# Updated by ONE background thread; ALL clients read from it.
_SNAPSHOT: Dict[str, Any] = {}
_SNAPSHOT_TS: float = 0.0
_SNAPSHOT_LOCK = threading.Lock()
_POLLER_STARTED = False
_POLLER_LOCK = threading.Lock()


def _get_snapshot_key(key: str) -> Optional[Any]:
    with _SNAPSHOT_LOCK:
        return _SNAPSHOT.get(key)


def _update_snapshot(data: Dict[str, Any]) -> None:
    global _SNAPSHOT_TS
    with _SNAPSHOT_LOCK:
        _SNAPSHOT.update(data)
        _SNAPSHOT_TS = time.time()


# =============================================================
# Serialisation helper
# =============================================================

def _serialize(val: Any) -> Any:
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, dict):
        return {k: _serialize(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_serialize(v) for v in val]
    return val


def _today() -> str:
    return date.today().isoformat()


# =============================================================
# DW Query Functions
# =============================================================

def _fetch_summary(conn) -> Dict[str, Any]:
    """Today KPIs from v_total_sales (reflects latest ETL cycle)."""
    today = _today()
    first_of_month = date.today().replace(day=1).isoformat()

    row = conn.execute(text("""
        SELECT
            COALESCE(SUM(SalesAmount - COALESCE(ReturnAmount,0) - COALESCE(DiscountAmount,0)), 0)
                AS today_revenue,
            COALESCE(SUM(TotalCost), 0) AS today_cost,
            COALESCE(
                SUM(SalesAmount - COALESCE(ReturnAmount,0) - COALESCE(DiscountAmount,0))
                - SUM(TotalCost), 0) AS today_profit,
            COUNT(*) AS today_orders,
            COALESCE(SUM(SalesQuantity), 0) AS today_items_sold,
            COALESCE(SUM(COALESCE(DiscountAmount, 0)), 0) AS today_discount
        FROM v_total_sales
        WHERE DateKey = :d
    """), {"d": today}).mappings().first()

    mtd = conn.execute(text("""
        SELECT
            COALESCE(SUM(
                total_sales_amount
                - COALESCE(total_return_amount, 0)
                - COALESCE(total_discount_amount, 0)
            ), 0) AS mtd_revenue,
            COUNT(DISTINCT CONCAT(DateKey, '_', StoreKey)) AS mtd_orders
        FROM summary_daily_sales
        WHERE DateKey >= :fom
    """), {"fom": first_of_month}).mappings().first()

    return {
        "today_revenue":    float(row["today_revenue"])    if row else 0.0,
        "today_cost":       float(row["today_cost"])       if row else 0.0,
        "today_profit":     float(row["today_profit"])     if row else 0.0,
        "today_orders":     int(row["today_orders"])       if row else 0,
        "today_items_sold": int(row["today_items_sold"])   if row else 0,
        "today_discount":   float(row["today_discount"])   if row else 0.0,
        "mtd_revenue":      float(mtd["mtd_revenue"])      if mtd else 0.0,
        "mtd_orders":       int(mtd["mtd_orders"])         if mtd else 0,
        "last_updated":     datetime.utcnow().isoformat(),
        "metric_date":      today,
    }


def _fetch_channels(conn) -> Dict[str, Any]:
    """Sales breakdown by channel (OFFLINE / ONLINE) for today."""
    today = _today()
    rows = conn.execute(text("""
        SELECT
            SaleChannel AS channel,
            COALESCE(SUM(SalesAmount - COALESCE(ReturnAmount,0) - COALESCE(DiscountAmount,0)), 0)
                AS revenue,
            COALESCE(SUM(TotalCost), 0) AS cost,
            COALESCE(
                SUM(SalesAmount - COALESCE(ReturnAmount,0) - COALESCE(DiscountAmount,0))
                - SUM(TotalCost), 0) AS profit,
            COUNT(*) AS orders,
            COALESCE(SUM(SalesQuantity), 0) AS items_sold
        FROM v_total_sales
        WHERE DateKey = :d
        GROUP BY SaleChannel
    """), {"d": today}).mappings().all()

    channels = [
        {
            "channel":    r["channel"],
            "revenue":    float(r["revenue"]),
            "cost":       float(r["cost"]),
            "profit":     float(r["profit"]),
            "orders":     int(r["orders"]),
            "items_sold": int(r["items_sold"]),
        }
        for r in rows
    ]
    total = sum(c["revenue"] for c in channels) or 1.0
    for c in channels:
        c["share_pct"] = round(c["revenue"] / total * 100, 1)

    return {"channels": channels, "total_revenue": total}


def _fetch_by_store(conn) -> Dict[str, Any]:
    """Today revenue and order count per store."""
    today = _today()
    rows = conn.execute(text("""
        SELECT
            v.StoreKey,
            COALESCE(ds.StoreName, CONCAT('Store ', v.StoreKey)) AS store_name,
            COALESCE(SUM(v.SalesAmount - COALESCE(v.ReturnAmount,0) - COALESCE(v.DiscountAmount,0)), 0)
                AS revenue,
            COUNT(*) AS orders
        FROM v_total_sales v
        LEFT JOIN DimStore ds ON ds.StoreKey = v.StoreKey
        WHERE v.DateKey = :d
        GROUP BY v.StoreKey, ds.StoreName
        ORDER BY revenue DESC
        LIMIT 20
    """), {"d": today}).mappings().all()

    return {
        "stores": [
            {
                "store_key":  int(r["StoreKey"]),
                "store_name": r["store_name"],
                "revenue":    float(r["revenue"]),
                "orders":     int(r["orders"]),
            }
            for r in rows
        ]
    }


def _fetch_trending_products(conn) -> Dict[str, Any]:
    """Top 10 products by quantity sold today."""
    today = _today()
    rows = conn.execute(text("""
        SELECT
            v.ProductKey,
            COALESCE(p.ProductName, CONCAT('Product ', v.ProductKey)) AS product_name,
            COALESCE(p.BrandName, '') AS brand_name,
            COALESCE(SUM(v.SalesQuantity), 0) AS qty_sold,
            COALESCE(SUM(v.SalesAmount - COALESCE(v.ReturnAmount,0) - COALESCE(v.DiscountAmount,0)), 0)
                AS revenue
        FROM v_total_sales v
        LEFT JOIN DimProduct p ON p.ProductKey = v.ProductKey
        WHERE v.DateKey = :d
        GROUP BY v.ProductKey, p.ProductName, p.BrandName
        ORDER BY qty_sold DESC
        LIMIT 10
    """), {"d": today}).mappings().all()

    return {
        "products": [
            {
                "product_key":  int(r["ProductKey"]),
                "product_name": r["product_name"],
                "brand_name":   r["brand_name"],
                "qty_sold":     int(r["qty_sold"]),
                "revenue":      float(r["revenue"]),
            }
            for r in rows
        ],
        "metric_date": today,
    }


def _fetch_employee_leaderboard(conn) -> Dict[str, Any]:
    """Today revenue leaderboard per store manager (from DimEmployee + DimStore)."""
    today = _today()
    rows = conn.execute(text("""
        SELECT
            e.EmployeeKey,
            COALESCE(CONCAT(e.FirstName, ' ', e.LastName), e.FirstName, 'Unknown')
                AS employee_name,
            COALESCE(e.Title, '') AS title,
            COALESCE(ds.StoreName, CONCAT('Store ', ds.StoreKey)) AS store_name,
            COUNT(*) AS orders_count,
            COALESCE(SUM(v.SalesAmount - COALESCE(v.ReturnAmount,0) - COALESCE(v.DiscountAmount,0)), 0)
                AS total_sales
        FROM v_total_sales v
        JOIN DimStore ds ON ds.StoreKey = v.StoreKey
        JOIN DimEmployee e ON e.EmployeeKey = ds.StoreManager
        WHERE v.DateKey = :d AND ds.StoreManager IS NOT NULL
        GROUP BY e.EmployeeKey, e.FirstName, e.LastName, e.Title, ds.StoreKey, ds.StoreName
        ORDER BY total_sales DESC
        LIMIT 15
    """), {"d": today}).mappings().all()

    return {
        "employees": [
            {
                "rank":          idx + 1,
                "employee_key":  int(r["EmployeeKey"]),
                "employee_name": r["employee_name"],
                "title":         r["title"],
                "store_name":    r["store_name"],
                "orders_count":  int(r["orders_count"]),
                "total_sales":   float(r["total_sales"]),
            }
            for idx, r in enumerate(rows)
        ],
        "metric_date": today,
    }


def _fetch_promotion_impact(conn) -> Dict[str, Any]:
    """Today promotion performance from v_total_sales + DimPromotion."""
    today = _today()
    rows = conn.execute(text("""
        SELECT
            v.PromotionKey,
            COALESCE(dp.PromotionName, CONCAT('Promo ', v.PromotionKey)) AS promotion_name,
            COALESCE(dp.DiscountPercent, 0) AS discount_pct,
            COUNT(*) AS orders_count,
            COALESCE(SUM(v.SalesAmount - COALESCE(v.ReturnAmount,0)), 0) AS total_sales,
            COALESCE(SUM(COALESCE(v.DiscountAmount, 0)), 0) AS total_discount
        FROM v_total_sales v
        LEFT JOIN DimPromotion dp ON dp.PromotionKey = v.PromotionKey
        WHERE v.DateKey = :d AND v.PromotionKey > 1
        GROUP BY v.PromotionKey, dp.PromotionName, dp.DiscountPercent
        ORDER BY total_sales DESC
    """), {"d": today}).mappings().all()

    return {
        "promotions": [
            {
                "promotion_key":  int(r["PromotionKey"]),
                "promotion_name": r["promotion_name"],
                "discount_pct":   float(r["discount_pct"]),
                "orders_count":   int(r["orders_count"]),
                "total_sales":    float(r["total_sales"]),
                "total_discount": float(r["total_discount"]),
            }
            for r in rows
        ],
        "metric_date": today,
    }


def _fetch_inventory(conn) -> Dict[str, Any]:
    """Inventory health from agg_inventory_metrics for the current month."""
    current_month = date.today().strftime("%Y-%m")

    summary = conn.execute(text("""
        SELECT
            COUNT(*) AS total_sku_store,
            COALESCE(SUM(avg_on_hand), 0) AS total_units,
            COALESCE(SUM(CASE WHEN avg_on_hand = 0               THEN 1 ELSE 0 END), 0) AS out_of_stock,
            COALESCE(SUM(CASE WHEN avg_on_hand > 0 AND avg_on_hand < 10 THEN 1 ELSE 0 END), 0) AS low_stock,
            COALESCE(SUM(CASE WHEN avg_on_hand >= 10              THEN 1 ELSE 0 END), 0) AS healthy_stock
        FROM agg_inventory_metrics
        WHERE period_month = :pm
    """), {"pm": current_month}).mappings().first()

    low_items = conn.execute(text("""
        SELECT
            aim.product_key,
            COALESCE(p.ProductName, CONCAT('Product ', aim.product_key)) AS product_name,
            aim.store_key,
            COALESCE(ds.StoreName, CONCAT('Store ', aim.store_key)) AS store_name,
            aim.avg_on_hand,
            aim.days_of_supply
        FROM agg_inventory_metrics aim
        LEFT JOIN DimProduct p  ON p.ProductKey  = aim.product_key
        LEFT JOIN DimStore   ds ON ds.StoreKey   = aim.store_key
        WHERE aim.period_month = :pm
          AND aim.avg_on_hand > 0 AND aim.avg_on_hand < 10
        ORDER BY aim.avg_on_hand ASC
        LIMIT 20
    """), {"pm": current_month}).mappings().all()

    return {
        "total_sku_store": int(summary["total_sku_store"])  if summary else 0,
        "total_units":     float(summary["total_units"])    if summary else 0.0,
        "out_of_stock":    int(summary["out_of_stock"])     if summary else 0,
        "low_stock":       int(summary["low_stock"])        if summary else 0,
        "healthy_stock":   int(summary["healthy_stock"])    if summary else 0,
        "low_stock_items": [
            {
                "product_key":   int(r["product_key"]),
                "product_name":  r["product_name"],
                "store_key":     int(r["store_key"]),
                "store_name":    r["store_name"],
                "avg_on_hand":   float(r["avg_on_hand"]),
                "days_of_supply":float(r["days_of_supply"]) if r["days_of_supply"] else 0.0,
            }
            for r in low_items
        ],
    }


def _fetch_daily_trend(conn) -> Dict[str, Any]:
    """Last 30 days of daily net revenue and item volume from summary_daily_sales."""
    rows = conn.execute(text("""
        SELECT
            DateKey,
            COALESCE(SUM(
                total_sales_amount
                - COALESCE(total_return_amount, 0)
                - COALESCE(total_discount_amount, 0)
            ), 0) AS net_revenue,
            COALESCE(SUM(total_sales_quantity), 0) AS items_sold,
            COUNT(DISTINCT StoreKey) AS active_stores
        FROM summary_daily_sales
        WHERE DateKey >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        GROUP BY DateKey
        ORDER BY DateKey
    """)).mappings().all()

    return {
        "labels":        [r["DateKey"].isoformat() for r in rows],
        "revenue":       [float(r["net_revenue"])   for r in rows],
        "items_sold":    [int(r["items_sold"])       for r in rows],
        "active_stores": [int(r["active_stores"])    for r in rows],
    }


# =============================================================
# Global DW Poller - updates singleton from Data Warehouse
# =============================================================

def _poll_dw_once() -> None:
    """Fetch all realtime metrics from DW and update the global singleton."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            snapshot = {
                "summary":              _fetch_summary(conn),
                "channels":             _fetch_channels(conn),
                "by_store":             _fetch_by_store(conn),
                "trending_products":    _fetch_trending_products(conn),
                "employee_leaderboard": _fetch_employee_leaderboard(conn),
                "promotion_impact":     _fetch_promotion_impact(conn),
                "inventory":            _fetch_inventory(conn),
                "daily_trend":          _fetch_daily_trend(conn),
            }
        _update_snapshot(snapshot)
        logger.debug("Realtime DW snapshot refreshed successfully.")
    except Exception as exc:
        logger.warning("Realtime DW poll failed: %s", exc)


def _start_dw_poller() -> None:
    """Start the singleton background poller (idempotent - only one thread runs)."""
    global _POLLER_STARTED
    with _POLLER_LOCK:
        if _POLLER_STARTED:
            return
        _POLLER_STARTED = True

    def _loop():
        # Initial poll immediately so first SSE client gets data right away.
        _poll_dw_once()
        while True:
            time.sleep(DW_POLL_INTERVAL)
            _poll_dw_once()

    threading.Thread(target=_loop, daemon=True, name="realtime-dw-poller").start()
    logger.info("Realtime DW poller started (interval=%ds)", DW_POLL_INTERVAL)


# =============================================================
# SSE Generator - reads ONLY from singleton (no DB hit per client)
# =============================================================

async def _sse_generator():
    """Stream realtime summary to clients.

    Sends an update whenever the DW snapshot is refreshed, or every 30 s
    as a keepalive so the connection stays alive through proxies.
    """
    last_sent_ts: float = 0.0
    FORCE_REFRESH_SEC = 30

    while True:
        try:
            with _SNAPSHOT_LOCK:
                current_ts = _SNAPSHOT_TS
                summary = _SNAPSHOT.get("summary")

            if summary and (
                current_ts > last_sent_ts
                or time.time() - last_sent_ts >= FORCE_REFRESH_SEC
            ):
                last_sent_ts = current_ts
                payload = json.dumps(_serialize(summary))
                yield f"data: {payload}\n\n"
            else:
                yield ": keepalive\n\n"
        except Exception as exc:
            logger.warning("SSE error: %s", exc)
            yield ": error\n\n"
        await asyncio.sleep(3)


# =============================================================
# FastAPI Router
# =============================================================

router = APIRouter(prefix="", tags=["realtime"])

# Start the background DW poller when this module is imported.
_start_dw_poller()


@router.get("/summary")
def rt_summary():
    data = _get_snapshot_key("summary") or {}
    return _serialize(data)


@router.get("/channels")
def rt_channels():
    data = _get_snapshot_key("channels") or {}
    return _serialize(data)


@router.get("/by-store")
def rt_by_store():
    data = _get_snapshot_key("by_store") or {}
    return _serialize(data)


@router.get("/trending-products")
def rt_trending_products():
    data = _get_snapshot_key("trending_products") or {}
    return _serialize(data)


@router.get("/employee-leaderboard")
def rt_employee_leaderboard():
    data = _get_snapshot_key("employee_leaderboard") or {}
    return _serialize(data)


@router.get("/promotion-impact")
def rt_promotion_impact():
    data = _get_snapshot_key("promotion_impact") or {}
    return _serialize(data)


@router.get("/inventory")
def rt_inventory():
    data = _get_snapshot_key("inventory") or {}
    return _serialize(data)


@router.get("/daily-trend")
def rt_daily_trend():
    data = _get_snapshot_key("daily_trend") or {}
    return _serialize(data)


@router.get("/stream")
async def rt_stream():
    """SSE endpoint - pushes realtime summary whenever DW snapshot is refreshed."""
    return StreamingResponse(
        _sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection":    "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/cache/invalidate")
def rt_invalidate_cache():
    """Force immediate DW poll to refresh the singleton snapshot."""
    threading.Thread(target=_poll_dw_once, daemon=True).start()
    return {"status": "ok", "message": "DW snapshot refresh triggered"}


@router.post("/refresh")
def rt_refresh():
    """Trigger immediate DW snapshot refresh."""
    threading.Thread(target=_poll_dw_once, daemon=True).start()
    return {"status": "ok", "message": f"Realtime DW snapshot refresh triggered for {_today()}"}