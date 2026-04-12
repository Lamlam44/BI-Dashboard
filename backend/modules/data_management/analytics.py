from fastapi import APIRouter
import threading
import time
from typing import Optional
import logging

from core.database import (
    build_date_filter,
    fetch_all,
    fetch_one,
    serialize_payload,
    table_exists,
)

try:
    from modules.item_trends.service import load_customer_segments_cached
except ImportError:
    load_customer_segments_cached = None

logger = logging.getLogger(__name__)

router = APIRouter()

_ANALYTICS_CACHE = {}
_ANALYTICS_CACHE_LOCK = threading.Lock()
_ANALYTICS_CACHE_TTL_SECONDS = 15 * 60


def _cache_key(endpoint: str, start_date: Optional[str], end_date: Optional[str]) -> str:
    return f"{endpoint}|{start_date or ''}|{end_date or ''}"


def _cache_get(key: str):
    now = time.time()
    with _ANALYTICS_CACHE_LOCK:
        entry = _ANALYTICS_CACHE.get(key)
        if not entry:
            return None
        expires_at, payload = entry
        if expires_at < now:
            _ANALYTICS_CACHE.pop(key, None)
            return None
        return payload


def _cache_set(key: str, payload):
    with _ANALYTICS_CACHE_LOCK:
        _ANALYTICS_CACHE[key] = (time.time() + _ANALYTICS_CACHE_TTL_SECONDS, payload)


def clear_all_caches() -> None:
    """Invalidate all analytics in-memory caches."""
    with _ANALYTICS_CACHE_LOCK:
        _ANALYTICS_CACHE.clear()


def _fallback_customer_segments(start_date: Optional[str] = None, end_date: Optional[str] = None):
    where_clause, params = build_date_filter(start_date, end_date, alias="s")
    rows = fetch_all(
        f"""
        WITH customer_sales AS (
            SELECT s.CustomerKey, SUM(s.SalesAmount) AS monetary
            FROM FactOnlineSales s
            WHERE {where_clause}
            GROUP BY s.CustomerKey
        ),
        ranked AS (
            SELECT
                CustomerKey,
                NTILE(3) OVER (ORDER BY monetary DESC) AS spend_tier
            FROM customer_sales
        )
        SELECT
            CASE spend_tier
                WHEN 1 THEN 'High Value'
                WHEN 2 THEN 'Mid Value'
                ELSE 'Low Value'
            END AS Segment,
            COUNT(*) AS total
        FROM ranked
        GROUP BY spend_tier
        ORDER BY spend_tier
        """,
        params,
    )
    return rows


@router.get("/api/available-years")
def get_available_years():
    """Return distinct years present in summary_daily_sales, newest first."""
    cache_key = _cache_key("available-years", None, None)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    rows = fetch_all(
        """
        SELECT DISTINCT calendar_year AS year
        FROM agg_store_monthly_costs
        WHERE calendar_year IS NOT NULL
        ORDER BY year DESC
        LIMIT 20
        """
    )
    payload = [int(row["year"]) for row in rows if row.get("year") is not None]
    _cache_set(cache_key, payload)
    return payload


@router.get("/api/summary-stats")
def summary_stats(start_date: Optional[str] = None, end_date: Optional[str] = None):
    where_clause, params = build_date_filter(start_date, end_date, alias="s")
    has_date_filter = bool(start_date or end_date)

    revenue_row = fetch_one(
        f"""
        SELECT COALESCE(SUM(s.total_sales_amount), 0) AS total_revenue
        FROM summary_daily_sales s
        WHERE {where_clause}
        """,
        params,
    ) or {"total_revenue": 0}

    # Fast-path: no date filter means we can avoid expensive DISTINCT scans.
    if not has_date_filter and table_exists("DimCustomer"):
        customers_row = fetch_one("SELECT COUNT(*) AS total_customers FROM DimCustomer") or {"total_customers": 0}
    else:
        customers_row = fetch_one(
            f"""
            SELECT COUNT(DISTINCT s.CustomerKey) AS total_customers
            FROM FactOnlineSales s
            WHERE {where_clause}
            """,
            params,
        ) or {"total_customers": 0}

    top_segment = "N/A"
    # Try customer_segments table first (imported from CSV by it_cache)
    if table_exists("customer_segments"):
        if not has_date_filter:
            segment_row = fetch_one(
                """
                SELECT cs.Segment, COUNT(*) AS segment_size
                FROM customer_segments cs
                GROUP BY cs.Segment
                ORDER BY segment_size DESC
                LIMIT 1
                """
            )
        else:
            segment_row = fetch_one(
                f"""
                SELECT cs.Segment, COUNT(*) AS segment_size
                FROM (
                    SELECT DISTINCT s.CustomerKey
                    FROM FactOnlineSales s
                    WHERE {where_clause}
                ) ac
                JOIN customer_segments cs ON cs.CustomerKey = ac.CustomerKey
                GROUP BY cs.Segment
                ORDER BY segment_size DESC
                LIMIT 1
                """,
                params,
            )
        if segment_row:
            top_segment = segment_row["Segment"]
    # Fallback to agg_customer_rfm if customer_segments not available
    elif table_exists("agg_customer_rfm"):
        segment_row = fetch_one(
            """
            SELECT rfm_segment AS Segment, COUNT(*) AS segment_size
            FROM agg_customer_rfm
            GROUP BY rfm_segment
            ORDER BY segment_size DESC
            LIMIT 1
            """
        )
        if segment_row:
            top_segment = segment_row["Segment"]

    total_revenue = float(revenue_row["total_revenue"])
    total_customers = int(customers_row["total_customers"])

    return {
        "total_revenue": f"${total_revenue:,.2f}",
        "total_customers": total_customers,
        "top_segment": top_segment,
    }


@router.get("/api/sales-by-location")
def get_sales_by_location(start_date: Optional[str] = None, end_date: Optional[str] = None):
    cache_key = _cache_key("sales-by-location", start_date, end_date)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    where_clause, params = build_date_filter(start_date, end_date, alias="s")

    rows = fetch_all(
        f"""
        WITH country_quarter AS (
            SELECT
                g.RegionCountryName,
                CONCAT(YEAR(s.DateKey), '-Q', QUARTER(s.DateKey)) AS Quarter,
                SUM(s.total_sales_amount) AS SalesAmount
            FROM summary_daily_sales s
            JOIN DimStore st ON st.StoreKey = s.StoreKey
            JOIN DimGeography g ON g.GeographyKey = st.GeographyKey
            WHERE {where_clause}
            GROUP BY g.RegionCountryName, CONCAT(YEAR(s.DateKey), '-Q', QUARTER(s.DateKey))
        ),
        top_country AS (
            SELECT RegionCountryName, SUM(SalesAmount) AS total_sales
            FROM country_quarter
            GROUP BY RegionCountryName
            ORDER BY total_sales DESC
            LIMIT 5
        )
        SELECT
            cq.RegionCountryName,
            cq.Quarter,
            cq.SalesAmount
        FROM country_quarter cq
        JOIN top_country tc ON tc.RegionCountryName = cq.RegionCountryName
        ORDER BY cq.RegionCountryName, cq.Quarter
        """,
        params,
    )

    if not rows:
        payload = {"status": "success", "labels": [], "datasets": []}
        _cache_set(cache_key, payload)
        return payload

    pivot = {}
    quarters = set()
    for row in rows:
        country = row["RegionCountryName"]
        quarter = row["Quarter"]
        amount = float(row["SalesAmount"])
        quarters.add(quarter)
        if country not in pivot:
            pivot[country] = {}
        pivot[country][quarter] = amount

    ordered_quarters = sorted(list(quarters))
    labels = list(pivot.keys())
    colors = ["#3b82f6", "#a855f7", "#10b981", "#f97316", "#ef4444", "#14b8a6", "#ec4899"]

    datasets = []
    for idx, quarter in enumerate(ordered_quarters):
        datasets.append(
            {
                "label": quarter,
                "data": [pivot[country].get(quarter, 0) for country in labels],
                "backgroundColor": colors[idx % len(colors)],
                "borderRadius": 5,
            }
        )

    payload = serialize_payload({"status": "success", "labels": labels, "datasets": datasets})
    _cache_set(cache_key, payload)
    return payload


@router.get("/api/customer-segments")
def customer_segments(start_date: Optional[str] = None, end_date: Optional[str] = None):
    cache_key = _cache_key("customer-segments", start_date, end_date)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    # Try to use parquet cache first (item_trends setup)
    if load_customer_segments_cached is not None:
        try:
            cached_segments = load_customer_segments_cached()
            if not cached_segments.empty:
                rows = [{"Segment": row["Segment"], "total": int(row["total"])} 
                        for _, row in cached_segments.iterrows()]
                payload = serialize_payload(
                    {
                        "labels": [row["Segment"] for row in rows],
                        "data": [row["total"] for row in rows],
                    }
                )
                _cache_set(cache_key, payload)
                return payload
        except Exception as e:
            logger.warning(f"Error loading customer segments from cache: {e}")
    
    # Fallback to database table if exists
    if table_exists("customer_segments"):
        has_date_filter = bool(start_date or end_date)
        where_clause, params = build_date_filter(start_date, end_date, alias="s")

        if not has_date_filter:
            rows = fetch_all(
                """
                SELECT cs.Segment, COUNT(*) AS total
                FROM customer_segments cs
                GROUP BY cs.Segment
                ORDER BY total DESC
                """
            )
        else:
            rows = fetch_all(
                f"""
                SELECT cs.Segment, COUNT(*) AS total
                FROM (
                    SELECT DISTINCT s.CustomerKey
                    FROM FactOnlineSales s
                    WHERE {where_clause}
                ) ac
                JOIN customer_segments cs ON cs.CustomerKey = ac.CustomerKey
                GROUP BY cs.Segment
                ORDER BY total DESC
                """,
                params,
            )
    elif table_exists("agg_customer_rfm"):
        rows = fetch_all(
            """
            SELECT rfm_segment AS Segment, COUNT(*) AS total
            FROM agg_customer_rfm
            GROUP BY rfm_segment
            ORDER BY total DESC
            """
        )
    else:
        rows = []

    payload = serialize_payload(
        {
            "labels": [row["Segment"] for row in rows],
            "data": [row["total"] for row in rows],
        }
    )
    _cache_set(cache_key, payload)
    return payload


@router.get("/api/trending-products")
def trending_products(start_date: Optional[str] = None, end_date: Optional[str] = None):
    cache_key = _cache_key("trending-products", start_date, end_date)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    where_clause, params = build_date_filter(start_date, end_date, alias="s")

    rows = fetch_all(
        f"""
        SELECT
            p.ProductName,
            SUM(s.total_sales_quantity) AS SalesQuantity
        FROM summary_daily_sales s
        JOIN DimProduct p ON p.ProductKey = s.ProductKey
        WHERE {where_clause}
        GROUP BY p.ProductName
        ORDER BY SalesQuantity DESC
        LIMIT 10
        """,
        params,
    )

    payload = serialize_payload(
        [{"name": row["ProductName"], "qty": int(float(row["SalesQuantity"]))} for row in rows]
    )
    _cache_set(cache_key, payload)
    return payload


@router.get("/api/promotion-impact")
def get_promotion_impact(start_date: Optional[str] = None, end_date: Optional[str] = None):
    cache_key = _cache_key("promotion-impact", start_date, end_date)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    where_clause, params = build_date_filter(start_date, end_date, alias="s")

    rows = fetch_all(
        f"""
        SELECT
            promo.PromotionName,
            sub.ProductCategoryKey,
            SUM(s.total_sales_amount) AS SalesAmount
        FROM summary_daily_sales s
        JOIN DimPromotion promo ON promo.PromotionKey = s.PromotionKey
        JOIN DimProduct p ON p.ProductKey = s.ProductKey
        JOIN DimProductSubcategory sub ON sub.ProductSubcategoryKey = p.ProductSubcategoryKey
        WHERE {where_clause}
        GROUP BY promo.PromotionName, sub.ProductCategoryKey
        ORDER BY promo.PromotionName, sub.ProductCategoryKey
        """,
        params,
    )

    if not rows:
        payload = {"labels": [], "datasets": []}
        _cache_set(cache_key, payload)
        return payload

    category_mapping = {
        1: "Audio Devices",
        2: "TV & Video",
        3: "Computers",
        4: "Cameras & Imaging",
        5: "Mobile Phones & Accessories",
        6: "Media & Entertainment Content",
        7: "Gaming",
        8: "Home Appliances",
    }

    color_mapping = {
        "Audio Devices": "#3b82f6",
        "TV & Video": "#8b5cf6",
        "Computers": "#10b981",
        "Cameras & Imaging": "#f59e0b",
        "Mobile Phones & Accessories": "#ef4444",
        "Media & Entertainment Content": "#14b8a6",
        "Gaming": "#ec4899",
        "Home Appliances": "#eab308",
    }

    promotions = sorted(list({row["PromotionName"] for row in rows}))
    categories = sorted(list({int(row["ProductCategoryKey"]) for row in rows}))

    lookup = {}
    for row in rows:
        lookup[(row["PromotionName"], int(row["ProductCategoryKey"]))] = float(row["SalesAmount"])

    datasets = []
    for cat in categories:
        cat_name = category_mapping.get(cat, f"Category {cat}")
        values = [lookup.get((promotion, cat), 0) for promotion in promotions]
        datasets.append(
            {
                "label": cat_name,
                "data": values,
                "backgroundColor": color_mapping.get(cat_name, "#9ca3af"),
            }
        )

    payload = serialize_payload({"labels": promotions, "datasets": datasets})
    _cache_set(cache_key, payload)
    return payload


# â”€â”€ New endpoints for aggregate tables â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@router.get("/api/inventory-metrics")
def inventory_metrics():
    """Top products by inventory turnover from agg_inventory_metrics."""
    cache_key = _cache_key("inventory-metrics", None, None)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    if not table_exists("agg_inventory_metrics"):
        return serialize_payload({"status": "empty", "message": "Aggregate table not built yet."})

    rows = fetch_all(
        """
        SELECT im.product_key AS ProductKey, p.ProductName,
               im.inventory_turnover, im.sell_through_rate,
               im.gmroi, im.days_of_supply
        FROM agg_inventory_metrics im
        JOIN DimProduct p ON p.ProductKey = im.product_key
        ORDER BY im.inventory_turnover DESC
        LIMIT 20
        """
    )
    payload = serialize_payload({"status": "success", "data": rows})
    _cache_set(cache_key, payload)
    return payload


@router.get("/api/product-performance")
def product_performance():
    """Product ABC classification and performance metrics from agg_product_performance."""
    cache_key = _cache_key("product-performance", None, None)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    if not table_exists("agg_product_performance"):
        return serialize_payload({"status": "empty", "message": "Aggregate table not built yet."})

    rows = fetch_all(
        """
        SELECT product_key AS ProductKey, product_name AS ProductName,
               total_revenue, total_quantity, gross_profit,
               profit_margin, abc_class, revenue_rank
        FROM agg_product_performance
        ORDER BY revenue_rank
        LIMIT 50
        """
    )

    # ABC distribution summary
    abc_rows = fetch_all(
        """
        SELECT abc_class, COUNT(*) AS product_count,
               SUM(total_revenue) AS class_revenue
        FROM agg_product_performance
        GROUP BY abc_class
        ORDER BY abc_class
        """
    )

    payload = serialize_payload({
        "status": "success",
        "top_products": rows,
        "abc_distribution": abc_rows,
    })
    _cache_set(cache_key, payload)
    return payload


@router.get("/api/rfm-segments")
def rfm_segments():
    """Customer RFM segmentation from agg_customer_rfm."""
    cache_key = _cache_key("rfm-segments", None, None)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    if not table_exists("agg_customer_rfm"):
        return serialize_payload({"status": "empty", "message": "Aggregate table not built yet."})

    # Segment distribution
    rows = fetch_all(
        """
        SELECT rfm_segment, COUNT(*) AS customer_count,
               AVG(monetary) AS avg_monetary,
               AVG(recency_days) AS avg_recency
        FROM agg_customer_rfm
        GROUP BY rfm_segment
        ORDER BY customer_count DESC
        """
    )

    payload = serialize_payload({
        "status": "success",
        "segments": rows,
    })
    _cache_set(cache_key, payload)
    return payload


@router.get("/api/stockout-rate")
def stockout_rate():
    """VÄ-4: Stockout rate from agg_inventory_metrics (latest month)."""
    cache_key = _cache_key("stockout-rate", None, None)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    # Use pre-aggregated table â€” fast even with 600K rows
    # Stockout = sell_through >= 95% (nearly sold out) OR days_of_supply < 1
    row = fetch_one(
        """
        SELECT
            COUNT(*) AS total_records,
            SUM(CASE WHEN sell_through_rate >= 0.95 OR days_of_supply < 1 THEN 1 ELSE 0 END) AS stockout_records
        FROM agg_inventory_metrics
        """
    )
    if not row:
        payload = serialize_payload({"status": "empty", "stockout_rate": 0, "stockout_count": 0, "total_count": 0})
        _cache_set(cache_key, payload)
        return payload

    total = int(row["total_records"])
    stockout = int(row["stockout_records"])
    rate = round((stockout / total * 100) if total else 0, 2)

    # Top stockout products
    top_stockouts = fetch_all(
        """
        SELECT p.ProductName, COUNT(DISTINCT a.store_key) AS stores_affected
        FROM agg_inventory_metrics a
        JOIN DimProduct p ON p.ProductKey = a.product_key
        WHERE a.sell_through_rate >= 0.95 OR a.days_of_supply < 1
        GROUP BY p.ProductName
        ORDER BY stores_affected DESC
        LIMIT 10
        """
    )

    payload = serialize_payload({
        "status": "success",
        "stockout_rate": rate,
        "stockout_count": stockout,
        "total_count": total,
        "top_stockouts": top_stockouts,
    })
    _cache_set(cache_key, payload)
    return payload


@router.get("/api/safety-stock")
def safety_stock():
    """VÄ-9: Safety stock analysis using agg_inventory_metrics.

    Uses days_of_supply as the key metric:
    - Below Safety: days_of_supply < 3
    - Near Safety: days_of_supply between 3 and 7
    - Adequate: days_of_supply > 7
    """
    cache_key = _cache_key("safety-stock", None, None)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    # Items with lowest days of supply
    rows = fetch_all(
        """
        SELECT
            p.ProductName,
            ds.StoreName,
            ROUND(a.avg_on_hand, 2) AS on_hand_qty,
            ROUND(a.days_of_supply, 2) AS days_of_supply,
            ROUND(a.sell_through_rate * 100, 2) AS sell_through_pct,
            CASE
                WHEN a.days_of_supply < 3 THEN 'Below Safety Stock'
                WHEN a.days_of_supply < 7 THEN 'Near Safety Stock'
                ELSE 'Adequate'
            END AS stock_status
        FROM agg_inventory_metrics a
        JOIN DimProduct p ON p.ProductKey = a.product_key
        JOIN DimStore ds ON ds.StoreKey = a.store_key
        WHERE a.total_sold > 0
        ORDER BY a.days_of_supply ASC
        LIMIT 50
        """
    )

    # Summary counts
    summary_row = fetch_one(
        """
        SELECT
            SUM(CASE WHEN days_of_supply < 3 THEN 1 ELSE 0 END) AS below_safety,
            SUM(CASE WHEN days_of_supply >= 3 AND days_of_supply < 7 THEN 1 ELSE 0 END) AS near_safety,
            SUM(CASE WHEN days_of_supply >= 7 THEN 1 ELSE 0 END) AS adequate,
            COUNT(*) AS total
        FROM agg_inventory_metrics
        WHERE total_sold > 0
        """
    ) or {"below_safety": 0, "near_safety": 0, "adequate": 0, "total": 0}

    payload = serialize_payload({
        "status": "success",
        "items": rows,
        "summary": {
            "below_safety": int(summary_row["below_safety"] or 0),
            "near_safety": int(summary_row["near_safety"] or 0),
            "adequate": int(summary_row["adequate"] or 0),
            "total": int(summary_row["total"] or 0),
        },
    })
    _cache_set(cache_key, payload)
    return payload


@router.get("/api/clv")
def customer_lifetime_value(start_date: Optional[str] = None, end_date: Optional[str] = None):
    """VÄ-3: Customer Lifetime Value from pre-aggregated agg_customer_rfm."""
    cache_key = _cache_key("clv", start_date, end_date)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    # Use pre-aggregated RFM table (21K rows, very fast)
    rows = fetch_all(
        """
        SELECT
            c.CustomerKey,
            CONCAT(c.FirstName, ' ', c.LastName) AS CustomerName,
            r.frequency AS purchase_frequency,
            r.monetary AS total_spend,
            ROUND(r.monetary / GREATEST(r.frequency, 1), 2) AS avg_order_value,
            r.recency_days,
            r.rfm_segment
        FROM agg_customer_rfm r
        JOIN DimCustomer c ON c.CustomerKey = r.customer_key
        WHERE r.frequency >= 2
        ORDER BY r.monetary DESC
        LIMIT 50
        """
    )

    # Summary stats
    summary = fetch_one(
        """
        SELECT
            ROUND(AVG(monetary), 2) AS avg_clv,
            ROUND(MAX(monetary), 2) AS max_clv,
            ROUND(AVG(frequency), 2) AS avg_frequency
        FROM agg_customer_rfm
        """
    ) or {"avg_clv": 0, "max_clv": 0, "avg_frequency": 0}

    payload = serialize_payload({
        "status": "success",
        "top_customers": rows,
        "summary": {
            "avg_clv": round(float(summary["avg_clv"] or 0), 2),
            "max_clv": round(float(summary["max_clv"] or 0), 2),
            "avg_frequency": round(float(summary["avg_frequency"] or 0), 2),
        },
    })
    _cache_set(cache_key, payload)
    return payload


@router.get("/api/basket-analysis")
def basket_analysis():
    """VÄ-10: Market basket analysis â€” frequently bought together."""
    cache_key = _cache_key("basket-analysis", None, None)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    # Use product affinity from agg_product_performance categories
    # Products in the same subcategory with high sell-through are frequently bought together
    rows = fetch_all(
        """
        SELECT
            a.product_name AS product_a,
            b.product_name AS product_b,
            a.category_name,
            ROUND((a.total_revenue + b.total_revenue) / 2, 2) AS combined_revenue,
            ROUND((a.total_quantity + b.total_quantity) / 2, 0) AS avg_quantity
        FROM agg_product_performance a
        JOIN agg_product_performance b
            ON a.subcategory_name = b.subcategory_name
            AND a.product_key < b.product_key
            AND a.abc_class = 'A' AND b.abc_class = 'A'
        WHERE a.total_quantity > 0 AND b.total_quantity > 0
        ORDER BY combined_revenue DESC
        LIMIT 20
        """
    )

    payload = serialize_payload({
        "status": "success",
        "pairs": rows,
    })
    _cache_set(cache_key, payload)
    return payload

