from fastapi import APIRouter
from typing import Optional

from db_utils import (
    build_date_filter,
    fetch_all,
    fetch_one,
    serialize_payload,
    table_exists,
)

router = APIRouter()


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
    if table_exists("Customer_Segments_Final"):
        if not has_date_filter:
            segment_row = fetch_one(
                """
                SELECT cs.Segment, COUNT(*) AS segment_size
                FROM Customer_Segments_Final cs
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
                JOIN Customer_Segments_Final cs ON cs.CustomerKey = ac.CustomerKey
                GROUP BY cs.Segment
                ORDER BY segment_size DESC
                LIMIT 1
                """,
                params,
            )
        if segment_row:
            top_segment = segment_row["Segment"]
    else:
        fallback_rows = _fallback_customer_segments(start_date=start_date, end_date=end_date)
        if fallback_rows:
            top_segment = fallback_rows[0]["Segment"]

    total_revenue = float(revenue_row["total_revenue"])
    total_customers = int(customers_row["total_customers"])

    return {
        "total_revenue": f"${total_revenue:,.2f}",
        "total_customers": total_customers,
        "top_segment": top_segment,
    }


@router.get("/api/sales-by-location")
def get_sales_by_location(start_date: Optional[str] = None, end_date: Optional[str] = None):
    where_clause, params = build_date_filter(start_date, end_date, alias="s")

    rows = fetch_all(
        f"""
        WITH filtered AS (
            SELECT
                g.RegionCountryName,
                CONCAT(YEAR(s.DateKey), '-Q', QUARTER(s.DateKey)) AS Quarter,
                s.SalesAmount
            FROM FactOnlineSales s
            JOIN DimCustomer c ON c.CustomerKey = s.CustomerKey
            JOIN DimGeography g ON g.GeographyKey = c.GeographyKey
            WHERE {where_clause}
        ),
        top_country AS (
            SELECT RegionCountryName, SUM(SalesAmount) AS total_sales
            FROM filtered
            GROUP BY RegionCountryName
            ORDER BY total_sales DESC
            LIMIT 5
        )
        SELECT
            f.RegionCountryName,
            f.Quarter,
            SUM(f.SalesAmount) AS SalesAmount
        FROM filtered f
        JOIN top_country tc ON tc.RegionCountryName = f.RegionCountryName
        GROUP BY f.RegionCountryName, f.Quarter
        ORDER BY f.RegionCountryName, f.Quarter
        """,
        params,
    )

    if not rows:
        return {"status": "success", "labels": [], "datasets": []}

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

    return serialize_payload({"status": "success", "labels": labels, "datasets": datasets})


@router.get("/api/customer-segments")
def customer_segments(start_date: Optional[str] = None, end_date: Optional[str] = None):
    if table_exists("Customer_Segments_Final"):
        has_date_filter = bool(start_date or end_date)
        where_clause, params = build_date_filter(start_date, end_date, alias="s")

        if not has_date_filter:
            rows = fetch_all(
                """
                SELECT cs.Segment, COUNT(*) AS total
                FROM Customer_Segments_Final cs
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
                JOIN Customer_Segments_Final cs ON cs.CustomerKey = ac.CustomerKey
                GROUP BY cs.Segment
                ORDER BY total DESC
                """,
                params,
            )
    else:
        rows = _fallback_customer_segments(start_date=start_date, end_date=end_date)

    return serialize_payload(
        {
            "labels": [row["Segment"] for row in rows],
            "data": [row["total"] for row in rows],
        }
    )


@router.get("/api/trending-products")
def trending_products(start_date: Optional[str] = None, end_date: Optional[str] = None):
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

    return serialize_payload(
        [{"name": row["ProductName"], "qty": int(float(row["SalesQuantity"]))} for row in rows]
    )


@router.get("/api/promotion-impact")
def get_promotion_impact(start_date: Optional[str] = None, end_date: Optional[str] = None):
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
        return {"labels": [], "datasets": []}

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

    return serialize_payload({"labels": promotions, "datasets": datasets})
