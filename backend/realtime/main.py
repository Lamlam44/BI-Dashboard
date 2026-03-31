"""
Realtime Metrics – Incremental Pre-Aggregation + In-Memory Cache.

This module provides near-real-time operational metrics by:
1. Maintaining a `realtime_daily_metrics` table in POS DB (incremental UPDATE on each order)
2. Keeping an in-memory Python dict cache (O(1) reads, ~1ms latency)
3. Exposing SSE endpoint so the frontend dashboard auto-updates

Metric Groups:
  - Revenue & Profit summary (today_revenue, today_cost, today_profit, today_orders)
  - Sales by Channel / Location
  - Trending Products (top SKUs today)
  - Employee Leaderboard (today)
  - Promotion Impact (today)
  - Real-time Inventory (stock levels, low-stock alerts)
"""

import asyncio
import json
import logging
import threading
import time
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, FastAPI
from fastapi.responses import StreamingResponse
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

try:
    from config import (
        POS_HOST, POS_PORT, POS_USER, POS_PASSWORD, POS_DATABASE,
    )
except ImportError:
    POS_HOST = "127.0.0.1"
    POS_PORT = 3306
    POS_USER = "root"
    POS_PASSWORD = "12345"
    POS_DATABASE = "pos_system"

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# POS Database Engine (singleton)
# ══════════════════════════════════════════════════════════════

_pos_engine: Optional[Engine] = None


def _get_pos_engine() -> Engine:
    global _pos_engine
    if _pos_engine is None:
        url = (
            f"mysql+pymysql://{POS_USER}:{POS_PASSWORD}"
            f"@{POS_HOST}:{POS_PORT}/{POS_DATABASE}?charset=utf8mb4"
        )
        _pos_engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)
    return _pos_engine


# ══════════════════════════════════════════════════════════════
# In-Memory Cache (thread-safe)
# ══════════════════════════════════════════════════════════════

_CACHE: Dict[str, Any] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL = 10  # seconds – very short for near-real-time
_CACHE_TIMESTAMPS: Dict[str, float] = {}


def _cache_get(key: str) -> Optional[Any]:
    with _CACHE_LOCK:
        ts = _CACHE_TIMESTAMPS.get(key, 0)
        if time.time() - ts > _CACHE_TTL:
            return None
        return _CACHE.get(key)


def _cache_set(key: str, value: Any):
    with _CACHE_LOCK:
        _CACHE[key] = value
        _CACHE_TIMESTAMPS[key] = time.time()


def _cache_invalidate():
    with _CACHE_LOCK:
        _CACHE.clear()
        _CACHE_TIMESTAMPS.clear()


def _serialize(val: Any) -> Any:
    from decimal import Decimal
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, dict):
        return {k: _serialize(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_serialize(v) for v in val]
    return val


# ══════════════════════════════════════════════════════════════
# Data Access – POS queries
# ══════════════════════════════════════════════════════════════

def _today() -> str:
    return date.today().isoformat()


def get_realtime_summary() -> Dict[str, Any]:
    """Revenue, Profit, Cost, Orders for today from realtime_daily_metrics."""
    cached = _cache_get("summary")
    if cached is not None:
        return cached

    engine = _get_pos_engine()
    today = _today()
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT
                COALESCE(today_revenue, 0) AS today_revenue,
                COALESCE(today_cost, 0) AS today_cost,
                COALESCE(today_profit, 0) AS today_profit,
                COALESCE(today_orders, 0) AS today_orders,
                COALESCE(today_items_sold, 0) AS today_items_sold,
                COALESCE(today_discount, 0) AS today_discount,
                updated_at
            FROM realtime_daily_metrics
            WHERE metric_date = :d AND store_id = 0 AND channel = 'ALL'
        """), {"d": today}).mappings().first()

        # MTD
        first_of_month = date.today().replace(day=1).isoformat()
        mtd_row = conn.execute(text("""
            SELECT
                COALESCE(SUM(today_revenue), 0) AS mtd_revenue,
                COALESCE(SUM(today_profit), 0) AS mtd_profit,
                COALESCE(SUM(today_orders), 0) AS mtd_orders
            FROM realtime_daily_metrics
            WHERE metric_date >= :fom
              AND store_id = 0 AND channel = 'ALL'
        """), {"fom": first_of_month}).mappings().first()

    result = {
        "today_revenue": float(row["today_revenue"]) if row else 0,
        "today_cost": float(row["today_cost"]) if row else 0,
        "today_profit": float(row["today_profit"]) if row else 0,
        "today_orders": int(row["today_orders"]) if row else 0,
        "today_items_sold": int(row["today_items_sold"]) if row else 0,
        "today_discount": float(row["today_discount"]) if row else 0,
        "mtd_revenue": float(mtd_row["mtd_revenue"]) if mtd_row else 0,
        "mtd_profit": float(mtd_row["mtd_profit"]) if mtd_row else 0,
        "mtd_orders": int(mtd_row["mtd_orders"]) if mtd_row else 0,
        "last_updated": row["updated_at"].isoformat() if row and row["updated_at"] else None,
        "metric_date": today,
    }
    _cache_set("summary", result)
    return result


def get_realtime_channels() -> Dict[str, Any]:
    """Sales by channel for today."""
    cached = _cache_get("channels")
    if cached is not None:
        return cached

    engine = _get_pos_engine()
    today = _today()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                channel,
                COALESCE(today_revenue, 0) AS revenue,
                COALESCE(today_profit, 0) AS profit,
                COALESCE(today_orders, 0) AS orders,
                COALESCE(today_items_sold, 0) AS items_sold
            FROM realtime_daily_metrics
            WHERE metric_date = :d AND store_id = 0 AND channel != 'ALL'
        """), {"d": today}).mappings().all()

    channels = []
    total = sum(float(r["revenue"]) for r in rows) or 1
    for r in rows:
        rev = float(r["revenue"])
        channels.append({
            "channel": r["channel"],
            "revenue": rev,
            "profit": float(r["profit"]),
            "orders": int(r["orders"]),
            "items_sold": int(r["items_sold"]),
            "share_pct": round(rev / total * 100, 1),
        })

    result = {"channels": channels, "total_revenue": total}
    _cache_set("channels", result)
    return result


def get_realtime_by_store() -> Dict[str, Any]:
    """Sales by store (location) for today."""
    cached = _cache_get("by_store")
    if cached is not None:
        return cached

    engine = _get_pos_engine()
    today = _today()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                rdm.store_id,
                s.store_name,
                s.city,
                s.country,
                COALESCE(rdm.today_revenue, 0) AS revenue,
                COALESCE(rdm.today_orders, 0) AS orders
            FROM realtime_daily_metrics rdm
            JOIN stores s ON s.store_id = rdm.store_id
            WHERE rdm.metric_date = :d AND rdm.store_id > 0 AND rdm.channel = 'ALL'
            ORDER BY rdm.today_revenue DESC
            LIMIT 20
        """), {"d": today}).mappings().all()

    stores = []
    for r in rows:
        stores.append({
            "store_id": int(r["store_id"]),
            "store_name": r["store_name"],
            "city": r["city"],
            "country": r["country"],
            "revenue": float(r["revenue"]),
            "orders": int(r["orders"]),
        })

    result = {"stores": stores}
    _cache_set("by_store", result)
    return result


def get_realtime_trending_products() -> Dict[str, Any]:
    """Top products by quantity sold today – direct query, lightweight."""
    cached = _cache_get("trending")
    if cached is not None:
        return cached

    engine = _get_pos_engine()
    today = _today()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                p.product_id,
                p.product_name,
                p.brand,
                SUM(soi.quantity) AS qty_sold,
                SUM(soi.line_total) AS revenue
            FROM sales_order_items soi
            JOIN sales_orders so ON so.order_id = soi.order_id
            JOIN products p ON p.product_id = soi.product_id
            WHERE DATE(so.order_date) = :d AND so.status = 'Completed'
            GROUP BY p.product_id, p.product_name, p.brand
            ORDER BY qty_sold DESC
            LIMIT 10
        """), {"d": today}).mappings().all()

    products = []
    for r in rows:
        products.append({
            "product_id": int(r["product_id"]),
            "product_name": r["product_name"],
            "brand": r["brand"],
            "qty_sold": int(r["qty_sold"]),
            "revenue": float(r["revenue"]),
        })

    result = {"products": products, "metric_date": today}
    _cache_set("trending", result)
    return result


def get_realtime_employee_leaderboard() -> Dict[str, Any]:
    """Employee sales leaderboard for today."""
    cached = _cache_get("employee_lb")
    if cached is not None:
        return cached

    engine = _get_pos_engine()
    today = _today()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                e.employee_id,
                CONCAT(e.first_name, ' ', e.last_name) AS employee_name,
                e.title,
                s.store_name,
                COUNT(DISTINCT so.order_id) AS orders_count,
                SUM(so.total_amount) AS total_sales
            FROM sales_orders so
            JOIN employees e ON e.employee_id = so.employee_id
            JOIN stores s ON s.store_id = so.store_id
            WHERE DATE(so.order_date) = :d AND so.status = 'Completed'
            GROUP BY e.employee_id, e.first_name, e.last_name, e.title, s.store_name
            ORDER BY total_sales DESC
            LIMIT 15
        """), {"d": today}).mappings().all()

    employees = []
    for idx, r in enumerate(rows):
        employees.append({
            "rank": idx + 1,
            "employee_id": int(r["employee_id"]),
            "employee_name": r["employee_name"],
            "title": r["title"],
            "store_name": r["store_name"],
            "orders_count": int(r["orders_count"]),
            "total_sales": float(r["total_sales"]),
        })

    result = {"employees": employees, "metric_date": today}
    _cache_set("employee_lb", result)
    return result


def get_realtime_promotion_impact() -> Dict[str, Any]:
    """Promotion impact for today – sales by promotion."""
    cached = _cache_get("promo_impact")
    if cached is not None:
        return cached

    engine = _get_pos_engine()
    today = _today()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                pr.promotion_id,
                pr.promotion_name,
                pr.discount_pct,
                COUNT(DISTINCT so.order_id) AS orders_count,
                COALESCE(SUM(so.total_amount), 0) AS total_sales,
                COALESCE(SUM(so.discount_amount), 0) AS total_discount,
                pr.budget,
                pr.spent
            FROM sales_orders so
            JOIN promotions pr ON pr.promotion_id = so.promotion_id
            WHERE DATE(so.order_date) = :d AND so.status = 'Completed' AND so.promotion_id > 1
            GROUP BY pr.promotion_id, pr.promotion_name, pr.discount_pct, pr.budget, pr.spent
            ORDER BY total_sales DESC
        """), {"d": today}).mappings().all()

    promotions = []
    for r in rows:
        promotions.append({
            "promotion_id": int(r["promotion_id"]),
            "promotion_name": r["promotion_name"],
            "discount_pct": float(r["discount_pct"]),
            "orders_count": int(r["orders_count"]),
            "total_sales": float(r["total_sales"]),
            "total_discount": float(r["total_discount"]),
            "budget": float(r["budget"]),
            "spent": float(r["spent"]),
        })

    result = {"promotions": promotions, "metric_date": today}
    _cache_set("promo_impact", result)
    return result


def get_realtime_inventory() -> Dict[str, Any]:
    """Real-time inventory status from current_inventory."""
    cached = _cache_get("inventory")
    if cached is not None:
        return cached

    engine = _get_pos_engine()
    with engine.connect() as conn:
        summary = conn.execute(text("""
            SELECT
                COUNT(*) AS total_sku_store,
                SUM(on_hand_qty) AS total_units,
                SUM(ci.on_hand_qty * p.unit_cost) AS total_stock_value,
                SUM(CASE WHEN on_hand_qty = 0 THEN 1 ELSE 0 END) AS out_of_stock,
                SUM(CASE WHEN on_hand_qty > 0 AND on_hand_qty <= reorder_point THEN 1 ELSE 0 END) AS low_stock,
                SUM(CASE WHEN on_hand_qty > reorder_point THEN 1 ELSE 0 END) AS healthy_stock
            FROM current_inventory ci
            JOIN products p ON p.product_id = ci.product_id
        """)).mappings().first()

        low_stock_items = conn.execute(text("""
            SELECT
                ci.product_id,
                p.product_name,
                ci.store_id,
                s.store_name,
                ci.on_hand_qty,
                ci.reorder_point,
                ci.safety_stock
            FROM current_inventory ci
            JOIN products p ON p.product_id = ci.product_id
            JOIN stores s ON s.store_id = ci.store_id
            WHERE ci.on_hand_qty <= ci.reorder_point AND ci.on_hand_qty > 0
            ORDER BY ci.on_hand_qty ASC
            LIMIT 20
        """)).mappings().all()

    result = {
        "total_sku_store": int(summary["total_sku_store"]) if summary else 0,
        "total_units": int(summary["total_units"]) if summary else 0,
        "total_stock_value": float(summary["total_stock_value"]) if summary else 0,
        "out_of_stock": int(summary["out_of_stock"]) if summary else 0,
        "low_stock": int(summary["low_stock"]) if summary else 0,
        "healthy_stock": int(summary["healthy_stock"]) if summary else 0,
        "low_stock_items": [
            {
                "product_id": int(r["product_id"]),
                "product_name": r["product_name"],
                "store_id": int(r["store_id"]),
                "store_name": r["store_name"],
                "on_hand_qty": int(r["on_hand_qty"]),
                "reorder_point": int(r["reorder_point"]),
                "safety_stock": int(r["safety_stock"]),
            }
            for r in low_stock_items
        ],
    }
    _cache_set("inventory", result)
    return result


def get_realtime_daily_trend() -> Dict[str, Any]:
    """Last 30 days trend from realtime_daily_metrics."""
    cached = _cache_get("daily_trend")
    if cached is not None:
        return cached

    engine = _get_pos_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                metric_date,
                today_revenue AS revenue,
                today_profit AS profit,
                today_orders AS orders
            FROM realtime_daily_metrics
            WHERE store_id = 0 AND channel = 'ALL'
              AND metric_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            ORDER BY metric_date
        """)).mappings().all()

    result = {
        "labels": [r["metric_date"].isoformat() for r in rows],
        "revenue": [float(r["revenue"]) for r in rows],
        "profit": [float(r["profit"]) for r in rows],
        "orders": [int(r["orders"]) for r in rows],
    }
    _cache_set("daily_trend", result)
    return result


# ══════════════════════════════════════════════════════════════
# Incremental Updater – called when a new order is processed
# ══════════════════════════════════════════════════════════════

def increment_metrics_for_order(
    order_date: str,
    store_id: int,
    channel: str,
    revenue: float,
    cost: float,
    items: int,
    discount: float,
    is_promo: bool,
):
    """Increment the aggregation table + invalidate cache. O(1) per order."""
    engine = _get_pos_engine()
    d = order_date[:10]  # YYYY-MM-DD

    with engine.begin() as conn:
        # Upsert ALL/ALL row
        conn.execute(text("""
            INSERT INTO realtime_daily_metrics
                (metric_date, store_id, channel, today_revenue, today_cost, today_profit,
                 today_orders, today_items_sold, today_discount, today_promo_sales, today_promo_discount)
            VALUES (:d, 0, 'ALL', :rev, :cost, :profit, 1, :items, :disc, :promo_sales, :promo_disc)
            ON DUPLICATE KEY UPDATE
                today_revenue = today_revenue + :rev,
                today_cost = today_cost + :cost,
                today_profit = today_profit + :profit,
                today_orders = today_orders + 1,
                today_items_sold = today_items_sold + :items,
                today_discount = today_discount + :disc,
                today_promo_sales = today_promo_sales + :promo_sales,
                today_promo_discount = today_promo_discount + :promo_disc,
                updated_at = NOW()
        """), {
            "d": d, "rev": revenue, "cost": cost, "profit": revenue - cost,
            "items": items, "disc": discount,
            "promo_sales": revenue if is_promo else 0,
            "promo_disc": discount if is_promo else 0,
        })

        # Upsert channel row
        conn.execute(text("""
            INSERT INTO realtime_daily_metrics
                (metric_date, store_id, channel, today_revenue, today_cost, today_profit,
                 today_orders, today_items_sold, today_discount)
            VALUES (:d, 0, :ch, :rev, :cost, :profit, 1, :items, :disc)
            ON DUPLICATE KEY UPDATE
                today_revenue = today_revenue + :rev,
                today_cost = today_cost + :cost,
                today_profit = today_profit + :profit,
                today_orders = today_orders + 1,
                today_items_sold = today_items_sold + :items,
                today_discount = today_discount + :disc,
                updated_at = NOW()
        """), {
            "d": d, "ch": channel, "rev": revenue, "cost": cost,
            "profit": revenue - cost, "items": items, "disc": discount,
        })

        # Upsert store row
        conn.execute(text("""
            INSERT INTO realtime_daily_metrics
                (metric_date, store_id, channel, today_revenue, today_cost, today_profit,
                 today_orders, today_items_sold, today_discount)
            VALUES (:d, :sid, 'ALL', :rev, :cost, :profit, 1, :items, :disc)
            ON DUPLICATE KEY UPDATE
                today_revenue = today_revenue + :rev,
                today_cost = today_cost + :cost,
                today_profit = today_profit + :profit,
                today_orders = today_orders + 1,
                today_items_sold = today_items_sold + :items,
                today_discount = today_discount + :disc,
                updated_at = NOW()
        """), {
            "d": d, "sid": store_id, "rev": revenue, "cost": cost,
            "profit": revenue - cost, "items": items, "disc": discount,
        })

    # Invalidate in-memory cache so next read picks up new data
    _cache_invalidate()


# ══════════════════════════════════════════════════════════════
# SSE – Server-Sent Events for push updates
# ══════════════════════════════════════════════════════════════

_last_known_updated_at: Optional[str] = None


async def _sse_generator():
    """Push realtime summary to connected clients every 3 seconds if data changed."""
    global _last_known_updated_at
    while True:
        try:
            summary = get_realtime_summary()
            current_ts = summary.get("last_updated")
            if current_ts != _last_known_updated_at:
                _last_known_updated_at = current_ts
                payload = json.dumps(_serialize(summary))
                yield f"data: {payload}\n\n"
            else:
                yield ": keepalive\n\n"
        except Exception as exc:
            logger.warning("SSE realtime error: %s", exc)
            yield ": error\n\n"
        await asyncio.sleep(3)


# ══════════════════════════════════════════════════════════════
# FastAPI Application
# ══════════════════════════════════════════════════════════════

app = FastAPI(title="Realtime Metrics API")


@app.get("/summary")
def rt_summary():
    return _serialize(get_realtime_summary())


@app.get("/channels")
def rt_channels():
    return _serialize(get_realtime_channels())


@app.get("/by-store")
def rt_by_store():
    return _serialize(get_realtime_by_store())


@app.get("/trending-products")
def rt_trending_products():
    return _serialize(get_realtime_trending_products())


@app.get("/employee-leaderboard")
def rt_employee_leaderboard():
    return _serialize(get_realtime_employee_leaderboard())


@app.get("/promotion-impact")
def rt_promotion_impact():
    return _serialize(get_realtime_promotion_impact())


@app.get("/inventory")
def rt_inventory():
    return _serialize(get_realtime_inventory())


@app.get("/daily-trend")
def rt_daily_trend():
    return _serialize(get_realtime_daily_trend())


@app.get("/stream")
async def rt_stream():
    """SSE endpoint – pushes realtime summary when data changes."""
    return StreamingResponse(
        _sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/cache/invalidate")
def rt_invalidate_cache():
    _cache_invalidate()
    return {"status": "ok", "message": "In-memory cache invalidated"}
