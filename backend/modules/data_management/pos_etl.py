"""
POS â†’ DW ETL: Extract data from pos_system, Transform, Load into retails_dataset.

Maps POS normalized tables to DW star-schema:
  - sales_orders (InStore) + sales_order_items â†’ FactSales
  - sales_orders (Online)  + sales_order_items â†’ FactOnlineSales
  - Also refreshes summary_daily_sales and aggregate tables.

Key offsets (to avoid collision with existing DW data):
  - SalesKey / OnlineSalesKey: pos item_id + 10_000_000
  - CustomerKey:               pos customer_id + 100_000
"""

import logging
from datetime import datetime

from sqlalchemy import create_engine, text

from core.config import (
    DW_HOST, DW_PORT, DW_USER, DW_PASSWORD, DW_DATABASE,
    POS_HOST, POS_PORT, POS_USER, POS_PASSWORD, POS_DATABASE,
)

logger = logging.getLogger(__name__)

_SALES_KEY_OFFSET = 10_000_000
_ONLINE_KEY_OFFSET = 10_000_000
_CUSTOMER_KEY_OFFSET = 100_000


def _dw_url():
    return f"mysql+pymysql://{DW_USER}:{DW_PASSWORD}@{DW_HOST}:{DW_PORT}/{DW_DATABASE}?charset=utf8mb4"


def _pos_url():
    return f"mysql+pymysql://{POS_USER}:{POS_PASSWORD}@{POS_HOST}:{POS_PORT}/{POS_DATABASE}?charset=utf8mb4"


def sync_pos_to_dw() -> dict:
    """Extract from POS, transform, load into DW.  Returns sync stats.
    
    Incremental: skips entirely if pos_change_log is empty (no changes since last ETL).
    """
    pos_engine = create_engine(_pos_url(), pool_pre_ping=True)
    dw_engine = create_engine(_dw_url(), pool_pre_ping=True)

    stats = {"instore_rows": 0, "online_rows": 0, "skipped": 0, "errors": []}

    # â”€â”€ 0. Check if any changes since last ETL â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    with pos_engine.connect() as pos_conn:
        try:
            row = pos_conn.execute(text(
                "SELECT COUNT(*) AS cnt FROM pos_change_log"
            )).mappings().first()
            if row and row["cnt"] == 0:
                logger.info("POS sync: no changes in pos_change_log, skipping.")
                pos_engine.dispose()
                dw_engine.dispose()
                return stats
        except Exception:
            pass  # table may not exist, do full sync

    # â”€â”€ 1. Read POS orders + items â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    with pos_engine.connect() as pos_conn:
        orders = pos_conn.execute(text("""
            SELECT o.order_id, o.order_number, o.order_date, o.customer_id,
                   o.store_id, o.employee_id, o.channel,
                   o.total_amount, o.discount_amount, o.status,
                   i.item_id, i.product_id, i.quantity, i.unit_price,
                   i.unit_cost, i.discount_pct, i.line_total
            FROM sales_orders o
            JOIN sales_order_items i ON i.order_id = o.order_id
            WHERE o.status IN ('Completed', 'Returned')
            ORDER BY o.order_id, i.item_id
        """)).mappings().fetchall()

    if not orders:
        logger.info("POS sync: no orders to sync.")
        return stats

    # â”€â”€ 2. Transform all rows into batch lists â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    instore_batch: list[dict] = []
    online_batch: list[dict] = []

    for row in orders:
        item_id = row["item_id"]
        channel = row["channel"]
        order_date = row["order_date"]
        date_key = order_date.strftime("%Y-%m-%d") if isinstance(order_date, datetime) else str(order_date)[:10]

        store_key = int(row["store_id"]) if row["store_id"] else 0
        product_key = int(row["product_id"]) if row["product_id"] else 0
        customer_key = (int(row["customer_id"]) + _CUSTOMER_KEY_OFFSET) if row["customer_id"] else 0

        qty = int(row["quantity"]) if row["quantity"] else 0
        unit_price = float(row["unit_price"]) if row["unit_price"] else 0
        unit_cost = float(row["unit_cost"]) if row["unit_cost"] else 0
        line_total = float(row["line_total"]) if row["line_total"] else 0
        total_cost = unit_cost * qty
        discount_amt = float(row["discount_pct"] or 0) / 100.0 * unit_price * qty

        is_return = row["status"] == "Returned"
        return_qty = qty if is_return else 0
        return_amt = line_total if is_return else 0
        sales_qty = 0 if is_return else qty
        sales_amt = 0 if is_return else line_total

        if channel == "Online":
            online_batch.append({
                "key": item_id + _ONLINE_KEY_OFFSET,
                "date_key": date_key, "store_key": store_key,
                "product_key": product_key, "customer_key": customer_key,
                "order_number": row["order_number"], "line_no": item_id,
                "sales_qty": sales_qty, "sales_amt": sales_amt,
                "return_qty": return_qty, "return_amt": return_amt,
                "discount_amt": discount_amt, "total_cost": total_cost,
                "unit_cost": unit_cost, "unit_price": unit_price,
            })
        else:
            instore_batch.append({
                "key": item_id + _SALES_KEY_OFFSET,
                "date_key": date_key, "store_key": store_key,
                "product_key": product_key,
                "unit_cost": unit_cost, "unit_price": unit_price,
                "sales_qty": sales_qty, "return_qty": return_qty,
                "return_amt": return_amt, "discount_amt": discount_amt,
                "total_cost": total_cost, "sales_amt": sales_amt,
            })

    # â”€â”€ 3. Batch load into DW (much faster than row-by-row) â”€â”€
    BATCH_SIZE = 2000

    with dw_engine.begin() as dw_conn:
        _ensure_dim_date(dw_conn, orders)

        # InStore â†’ FactSales
        for i in range(0, len(instore_batch), BATCH_SIZE):
            chunk = instore_batch[i:i + BATCH_SIZE]
            dw_conn.execute(text("""
                REPLACE INTO FactSales
                    (SalesKey, DateKey, channelKey, StoreKey, ProductKey,
                     PromotionKey, CurrencyKey, UnitCost, UnitPrice,
                     SalesQuantity, ReturnQuantity, ReturnAmount,
                     DiscountQuantity, DiscountAmount, TotalCost, SalesAmount)
                VALUES
                    (:key, :date_key, 1, :store_key, :product_key,
                     1, 1, :unit_cost, :unit_price,
                     :sales_qty, :return_qty, :return_amt,
                     0, :discount_amt, :total_cost, :sales_amt)
            """), chunk)
        stats["instore_rows"] = len(instore_batch)

        # Online â†’ FactOnlineSales
        for i in range(0, len(online_batch), BATCH_SIZE):
            chunk = online_batch[i:i + BATCH_SIZE]
            dw_conn.execute(text("""
                REPLACE INTO FactOnlineSales
                    (OnlineSalesKey, DateKey, StoreKey, ProductKey,
                     PromotionKey, CurrencyKey, CustomerKey,
                     SalesOrderNumber, SalesOrderLineNumber,
                     SalesQuantity, SalesAmount,
                     ReturnQuantity, ReturnAmount,
                     DiscountQuantity, DiscountAmount,
                     TotalCost, UnitCost, UnitPrice)
                VALUES
                    (:key, :date_key, :store_key, :product_key,
                     1, 1, :customer_key,
                     :order_number, :line_no,
                     :sales_qty, :sales_amt,
                     :return_qty, :return_amt,
                     0, :discount_amt,
                     :total_cost, :unit_cost, :unit_price)
            """), chunk)
        stats["online_rows"] = len(online_batch)

    # ── 4. Refresh summary_daily_sales for new dates ──────────
    _refresh_summary(dw_engine)

    # ── 5. Clear processed change log entries ─────────────────
    # Only clear AFTER all DW writes succeed. If any prior step
    # raises an exception we never reach here, so the log entries
    # remain for the next ETL retry (data integrity guarantee).
    try:
        with pos_engine.connect() as pos_conn:
            with pos_conn.begin():
                pos_conn.execute(text("DELETE FROM pos_change_log"))
        logger.info("POS change log cleared after successful DW sync.")
    except Exception as exc:
        logger.warning("Could not clear pos_change_log (non-critical): %s", exc)

    pos_engine.dispose()
    dw_engine.dispose()

    logger.info(
        "POSâ†’DW sync done: %d InStore, %d Online rows loaded.",
        stats["instore_rows"], stats["online_rows"],
    )
    return stats


def _ensure_dim_date(conn, orders):
    """Insert any missing dates into DimDate so foreign-key lookups work."""
    dates_needed = set()
    for row in orders:
        od = row["order_date"]
        if isinstance(od, datetime):
            dates_needed.add(od.date())
        else:
            dates_needed.add(str(od)[:10])

    for d in dates_needed:
        if isinstance(d, str):
            from datetime import date as _date
            parts = d.split("-")
            d = _date(int(parts[0]), int(parts[1]), int(parts[2]))
        date_str = d.strftime("%Y-%m-%d")
        conn.execute(text("""
            INSERT IGNORE INTO DimDate (DateKey, CalendarYear, MonthNumber)
            VALUES (:dk, :y, :m)
        """), {"dk": date_str, "y": d.year, "m": d.month})


def _refresh_summary(dw_engine):
    """Incrementally refresh summary_daily_sales for POS-sourced rows.

    Includes return amounts and discount amounts so that net revenue
    calculations in all downstream queries remain accurate.
    """
    with dw_engine.begin() as conn:
        # Remove POS-sourced rows then rebuild from DW fact tables.
        # Using DELETE + REPLACE (not UPSERT) guarantees stale return
        # records from a previously 'Completed' order that became
        # 'Returned' are fully replaced with the correct figures.
        conn.execute(text(f"""
            DELETE FROM summary_daily_sales
            WHERE (DateKey, StoreKey, ProductKey, PromotionKey) IN (
                SELECT DATE(DateKey), COALESCE(StoreKey,0), ProductKey, COALESCE(PromotionKey,0)
                FROM FactSales WHERE SalesKey >= {_SALES_KEY_OFFSET}
            )
        """))
        conn.execute(text(f"""
            REPLACE INTO summary_daily_sales
                (DateKey, StoreKey, ProductKey, PromotionKey,
                 total_sales_quantity, total_sales_amount,
                 total_return_amount, total_discount_amount)
            SELECT
                DATE(f.DateKey),
                COALESCE(f.StoreKey, 0),
                f.ProductKey,
                COALESCE(f.PromotionKey, 0),
                SUM(f.SalesQuantity),
                SUM(f.SalesAmount),
                COALESCE(SUM(f.ReturnAmount), 0),
                COALESCE(SUM(f.DiscountAmount), 0)
            FROM FactSales f
            WHERE f.SalesKey >= {_SALES_KEY_OFFSET}
            GROUP BY DATE(f.DateKey), COALESCE(f.StoreKey,0),
                     f.ProductKey, COALESCE(f.PromotionKey,0)
        """))
        # Online channel
        conn.execute(text(f"""
            REPLACE INTO summary_daily_sales
                (DateKey, StoreKey, ProductKey, PromotionKey,
                 total_sales_quantity, total_sales_amount,
                 total_return_amount, total_discount_amount)
            SELECT
                DATE(f.DateKey),
                COALESCE(f.StoreKey, 0),
                f.ProductKey,
                COALESCE(f.PromotionKey, 0),
                SUM(f.SalesQuantity),
                SUM(f.SalesAmount),
                COALESCE(SUM(f.ReturnAmount), 0),
                COALESCE(SUM(f.DiscountAmount), 0)
            FROM FactOnlineSales f
            WHERE f.OnlineSalesKey >= {_ONLINE_KEY_OFFSET}
            GROUP BY DATE(f.DateKey), COALESCE(f.StoreKey,0),
                     f.ProductKey, COALESCE(f.PromotionKey,0)
        """))
    logger.info("summary_daily_sales refreshed for POS data (with returns and discounts).")

