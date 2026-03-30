import threading
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    from db_utils import fetch_all, fetch_one
except ImportError:
    from ..db_utils import fetch_all, fetch_one


_CACHE_TTL_SECONDS = 10 * 60
_EMP_PERF_CACHE: Dict[str, Tuple[float, Any]] = {}
_EMP_PERF_CACHE_LOCK = threading.Lock()
_LATEST_YEAR_CACHE: Tuple[float, Optional[int]] = (0, None)


def _cache_key(endpoint: str, **filters: Any) -> str:
    parts = [endpoint]
    for key in sorted(filters.keys()):
        value = filters[key]
        parts.append(f"{key}={value if value is not None else ''}")
    return "|".join(parts)


def _cache_get(key: str):
    now = time.time()
    with _EMP_PERF_CACHE_LOCK:
        entry = _EMP_PERF_CACHE.get(key)
        if not entry:
            return None
        expires_at, payload = entry
        if expires_at < now:
            _EMP_PERF_CACHE.pop(key, None)
            return None
        return payload


def _cache_set(key: str, payload: Any) -> None:
    with _EMP_PERF_CACHE_LOCK:
        _EMP_PERF_CACHE[key] = (time.time() + _CACHE_TTL_SECONDS, payload)


def _normalize_int(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    return int(value)


def _resolve_year(year: Optional[int]) -> Optional[int]:
    explicit = _normalize_int(year)
    if explicit is not None:
        return explicit

    now = time.time()
    global _LATEST_YEAR_CACHE
    cached_at, cached_value = _LATEST_YEAR_CACHE
    if cached_value is not None and (now - cached_at) < _CACHE_TTL_SECONDS:
        return cached_value

    row = fetch_one(
        """
        SELECT CAST(MAX(d.CalendarYear) AS SIGNED) AS latest_year
        FROM summary_daily_sales sds
        JOIN DimDate d ON d.DateKey = sds.DateKey
        WHERE d.CalendarYear IS NOT NULL
        """
    )
    if not row:
        return None
    latest_year = row.get("latest_year")
    _LATEST_YEAR_CACHE = (now, latest_year)
    return latest_year


def _manager_filters_sql(
    year: Optional[int] = None,
    month: Optional[int] = None,
    employee_key: Optional[int] = None,
    store_key: Optional[int] = None,
) -> Tuple[str, Dict[str, Any]]:
    clauses: List[str] = ["ds.StoreManager IS NOT NULL"]
    params: Dict[str, Any] = {}

    year_val = _normalize_int(year)
    month_val = _normalize_int(month)
    employee_val = _normalize_int(employee_key)
    store_val = _normalize_int(store_key)

    if year_val is not None:
        clauses.append("d.CalendarYear = :year")
        params["year"] = year_val

    if month_val is not None:
        clauses.append("d.MonthNumber = :month")
        params["month"] = month_val

    if employee_val is not None:
        clauses.append("ds.StoreManager = :employee_key")
        params["employee_key"] = employee_val

    if store_val is not None:
        clauses.append("sds.StoreKey = :store_key")
        params["store_key"] = store_val

    return " AND ".join(clauses), params


def _manager_monthly_subquery(where_clause: str) -> str:
    return f"""
    SELECT
        ds.StoreManager AS employee_key,
        sds.StoreKey AS store_key,
        d.CalendarYear AS year,
        d.MonthNumber AS month,
        SUM(COALESCE(sds.total_sales_amount, 0)) AS total_sales_amount,
        COALESCE(smc.total_return_amount, 0) AS total_return_amount,
        SUM(COALESCE(sds.total_sales_amount, 0)) - COALESCE(smc.total_return_amount, 0) AS net_sales,
        COALESCE(smc.total_cost, 0) AS total_cost,
        CASE WHEN SUM(COALESCE(sds.total_sales_amount, 0)) > 0
             THEN (SUM(COALESCE(sds.total_sales_amount, 0)) - COALESCE(smc.total_cost, 0))
                  / SUM(COALESCE(sds.total_sales_amount, 0)) * 100
             ELSE 0
        END AS profit_margin,
        SUM(COALESCE(sds.total_sales_quantity, 0)) AS total_sales_quantity,
        COALESCE(smc.total_return_quantity, 0) AS total_return_quantity,
        CASE WHEN SUM(COALESCE(sds.total_sales_quantity, 0)) > 0
             THEN COALESCE(smc.total_return_quantity, 0)
                  / SUM(COALESCE(sds.total_sales_quantity, 0)) * 100
             ELSE 0
        END AS return_rate,
        COUNT(*) AS order_count,
        AVG(COALESCE(sds.total_sales_amount, 0)) AS avg_ticket_size
    FROM summary_daily_sales sds
    JOIN DimStore ds ON ds.StoreKey = sds.StoreKey
    JOIN DimDate d ON d.DateKey = sds.DateKey
    LEFT JOIN agg_store_monthly_costs smc
        ON smc.store_key = sds.StoreKey
       AND smc.calendar_year = d.CalendarYear
       AND smc.month_number = d.MonthNumber
    WHERE {where_clause}
    GROUP BY ds.StoreManager, sds.StoreKey, d.CalendarYear, d.MonthNumber,
             smc.total_return_amount, smc.total_cost, smc.total_return_quantity
    """


def get_filters() -> Dict[str, Any]:
    cache_key = _cache_key("filters")
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    years = fetch_all(
        """
        SELECT DISTINCT CAST(d.CalendarYear AS SIGNED) AS year
        FROM summary_daily_sales sds
        JOIN DimDate d ON d.DateKey = sds.DateKey
        WHERE d.CalendarYear IS NOT NULL
        ORDER BY year DESC
        LIMIT 10
        """
    )

    months = fetch_all(
        """
        SELECT DISTINCT CAST(MonthNumber AS SIGNED) AS month
        FROM DimDate
        WHERE MonthNumber IS NOT NULL
        ORDER BY month
        """
    )

    stores = fetch_all(
        """
        SELECT DISTINCT
            CAST(StoreKey AS SIGNED) AS store_key,
            COALESCE(StoreName, CONCAT('Store ', StoreKey)) AS store_name
        FROM DimStore
        WHERE StoreKey IS NOT NULL
        ORDER BY store_name
        """
    )

    employees = fetch_all(
        """
        SELECT DISTINCT
            CAST(ds.StoreManager AS SIGNED) AS employee_key,
            TRIM(CONCAT(COALESCE(de.FirstName, ''), ' ', COALESCE(de.LastName, ''))) AS employee_name,
            de.Title AS title
        FROM DimStore ds
        LEFT JOIN DimEmployee de ON de.EmployeeKey = ds.StoreManager
        WHERE ds.StoreManager IS NOT NULL
        ORDER BY employee_name
        """
    )

    normalized_employees = []
    for row in employees:
        employee_name = row.get("employee_name") or f"Employee {row.get('employee_key')}"
        normalized_employees.append(
            {
                "employee_key": row.get("employee_key"),
                "employee_name": employee_name,
                "title": row.get("title"),
            }
        )

    payload = {
        "years": [int(row["year"]) for row in years if row.get("year") is not None],
        "months": [int(row["month"]) for row in months if row.get("month") is not None],
        "stores": stores,
        "employees": normalized_employees,
    }
    _cache_set(cache_key, payload)
    return payload


def get_dashboard(
    year: Optional[int] = None,
    month: Optional[int] = None,
    employee_key: Optional[int] = None,
    store_key: Optional[int] = None,
) -> Dict[str, Any]:
    cache_key = _cache_key(
        "dashboard",
        year=year,
        month=month,
        employee_key=employee_key,
        store_key=store_key,
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    resolved_year = _resolve_year(year)
    where_clause, params = _manager_filters_sql(resolved_year, month, employee_key, store_key)
    manager_monthly_sql = _manager_monthly_subquery(where_clause)

    kpi_sql = f"""
    WITH manager_monthly AS (
        {manager_monthly_sql}
    )
    SELECT
        COUNT(DISTINCT employee_key) AS employee_count,
        COUNT(DISTINCT store_key) AS store_count,
        SUM(net_sales) AS total_net_sales,
        AVG(net_sales) AS avg_net_sales,
        AVG(profit_margin) AS avg_profit_margin,
        AVG(return_rate) AS avg_return_rate,
        AVG(avg_ticket_size) AS avg_ticket_size,
        SUM(order_count) AS total_orders
    FROM manager_monthly
    """

    top_sql = f"""
    WITH manager_monthly AS (
        {manager_monthly_sql}
    )
    SELECT
        CAST(mm.employee_key AS SIGNED) AS employee_key,
        TRIM(CONCAT(COALESCE(de.FirstName, ''), ' ', COALESCE(de.LastName, ''))) AS employee_name,
        de.Title AS title,
        SUM(mm.net_sales) AS net_sales,
        AVG(mm.profit_margin) AS profit_margin,
        AVG(mm.return_rate) AS return_rate,
        SUM(mm.order_count) AS total_orders
    FROM manager_monthly mm
    LEFT JOIN dimemployee de ON de.EmployeeKey = mm.employee_key
    GROUP BY mm.employee_key, de.FirstName, de.LastName, de.Title
    ORDER BY net_sales DESC
    LIMIT 1
    """

    company_where_clause, company_params = _manager_filters_sql(resolved_year, month, None, None)
    company_monthly_sql = _manager_monthly_subquery(company_where_clause)

    company_avg_sql = f"""
    WITH manager_monthly AS (
        {company_monthly_sql}
    )
    SELECT
        AVG(COALESCE(net_sales, 0)) AS company_avg_net_sales,
        AVG(COALESCE(profit_margin, 0)) AS company_avg_profit_margin,
        AVG(COALESCE(return_rate, 0)) AS company_avg_return_rate
    FROM manager_monthly
    """

    kpis = fetch_one(kpi_sql, params) or {}
    has_data = int(kpis.get("employee_count") or 0) > 0
    top_performer = fetch_one(top_sql, params) if has_data else None
    company_avg = fetch_one(company_avg_sql, company_params) or {}

    comparison = {
        "delta_vs_company_avg_net_sales": (kpis.get("avg_net_sales") or 0) - (company_avg.get("company_avg_net_sales") or 0),
        "delta_vs_company_avg_profit_margin": (kpis.get("avg_profit_margin") or 0)
        - (company_avg.get("company_avg_profit_margin") or 0),
        "delta_vs_company_avg_return_rate": (kpis.get("avg_return_rate") or 0)
        - (company_avg.get("company_avg_return_rate") or 0),
    }

    capabilities = [
        {
            "key": "manager_productivity",
            "enabled": True,
            "reason": "Supported using factsales, dimstore, and dimdate with store manager aggregation.",
        },
        {
            "key": "time_trend_drilldown",
            "enabled": True,
            "reason": "CalendarYear and MonthNumber support trend and drill-down by month.",
        },
        {
            "key": "radar_skill_assessment",
            "enabled": False,
            "reason": "No skill-dimension table or competency score columns in current database.",
        },
        {
            "key": "absenteeism_heatmap",
            "enabled": False,
            "reason": "No attendance or leave table detected in retails_dataset.",
        },
        {
            "key": "enps_engagement",
            "enabled": False,
            "reason": "No survey/eNPS dataset detected in retails_dataset.",
        },
        {
            "key": "nine_box_potential",
            "enabled": False,
            "reason": "Potential score data is not available; only performance-side metrics exist.",
        },
    ]

    payload = {
        "filters": {
            "year": resolved_year,
            "month": month,
            "employee_key": employee_key,
            "store_key": store_key,
        },
        "kpis": kpis,
        "top_performer": top_performer,
        "comparison": comparison,
        "capabilities": capabilities,
    }


    _cache_set(cache_key, payload)
    return payload
def get_trend(
    year: Optional[int] = None,
    employee_key: Optional[int] = None,
    store_key: Optional[int] = None,
) -> Dict[str, Any]:
    cache_key = _cache_key(
        "trend",
        year=year,
        employee_key=employee_key,
        store_key=store_key,
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    resolved_year = _resolve_year(year)
    where_clause, params = _manager_filters_sql(resolved_year, None, employee_key, store_key)
    manager_monthly_sql = _manager_monthly_subquery(where_clause)

    sql = f"""
    WITH manager_monthly AS (
        {manager_monthly_sql}
    )
    SELECT
        CAST(year AS SIGNED) AS year,
        CAST(month AS SIGNED) AS month,
        SUM(net_sales) AS net_sales,
        AVG(profit_margin) AS profit_margin,
        AVG(return_rate) AS return_rate,
        SUM(order_count) AS total_orders
    FROM manager_monthly
    GROUP BY year, month
    ORDER BY year, month
    """

    rows = fetch_all(sql, params)
    payload = {
        "filters": {
            "year": resolved_year,
            "employee_key": employee_key,
            "store_key": store_key,
        },
        "rows": rows,
    }
    _cache_set(cache_key, payload)
    return payload


def get_leaderboard(
    year: Optional[int] = None,
    month: Optional[int] = None,
    store_key: Optional[int] = None,
    top_n: int = 10,
) -> Dict[str, Any]:
    cache_key = _cache_key(
        "leaderboard",
        year=year,
        month=month,
        store_key=store_key,
        top_n=top_n,
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    resolved_year = _resolve_year(year)
    where_clause, params = _manager_filters_sql(resolved_year, month, None, store_key)
    manager_monthly_sql = _manager_monthly_subquery(where_clause)
    params["top_n"] = int(top_n)

    sql = f"""
    WITH manager_monthly AS (
        {manager_monthly_sql}
    )
    SELECT
        CAST(mm.employee_key AS SIGNED) AS employee_key,
        TRIM(CONCAT(COALESCE(de.FirstName, ''), ' ', COALESCE(de.LastName, ''))) AS employee_name,
        de.Title AS title,
        SUM(mm.net_sales) AS net_sales,
        AVG(mm.profit_margin) AS profit_margin,
        AVG(mm.return_rate) AS return_rate,
        SUM(mm.order_count) AS total_orders,
        AVG(mm.avg_ticket_size) AS avg_ticket_size,
        DENSE_RANK() OVER (ORDER BY SUM(mm.net_sales) DESC) AS ranking
    FROM manager_monthly mm
    LEFT JOIN dimemployee de ON de.EmployeeKey = mm.employee_key
    GROUP BY mm.employee_key, de.FirstName, de.LastName, de.Title
    ORDER BY net_sales DESC
    LIMIT :top_n
    """

    rows = fetch_all(sql, params)
    for row in rows:
        if not row.get("employee_name"):
            row["employee_name"] = f"Employee {row.get('employee_key')}"

    payload = {
        "filters": {
            "year": resolved_year,
            "month": month,
            "store_key": store_key,
            "top_n": top_n,
        },
        "rows": rows,
    }
    _cache_set(cache_key, payload)
    return payload


def get_scatter(
    year: Optional[int] = None,
    month: Optional[int] = None,
    store_key: Optional[int] = None,
) -> Dict[str, Any]:
    cache_key = _cache_key(
        "scatter",
        year=year,
        month=month,
        store_key=store_key,
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    resolved_year = _resolve_year(year)
    where_clause, params = _manager_filters_sql(resolved_year, month, None, store_key)
    manager_monthly_sql = _manager_monthly_subquery(where_clause)

    sql = f"""
    WITH manager_monthly AS (
        {manager_monthly_sql}
    )
    SELECT
        CAST(mm.employee_key AS SIGNED) AS employee_key,
        TRIM(CONCAT(COALESCE(de.FirstName, ''), ' ', COALESCE(de.LastName, ''))) AS employee_name,
        SUM(mm.net_sales) AS net_sales,
        AVG(mm.profit_margin) AS profit_margin,
        AVG(mm.return_rate) AS return_rate,
        SUM(mm.order_count) AS total_orders
    FROM manager_monthly mm
    LEFT JOIN dimemployee de ON de.EmployeeKey = mm.employee_key
    GROUP BY mm.employee_key, de.FirstName, de.LastName
    ORDER BY net_sales DESC
    LIMIT 100
    """

    rows = fetch_all(sql, params)
    for row in rows:
        if not row.get("employee_name"):
            row["employee_name"] = f"Employee {row.get('employee_key')}"

    payload = {
        "filters": {"year": resolved_year, "month": month, "store_key": store_key},
        "rows": rows,
    }
    _cache_set(cache_key, payload)
    return payload


def health_check() -> Dict[str, Any]:
    row = fetch_one("SELECT 1 AS ok") or {"ok": 0}

    table_state = fetch_one(
        """
        SELECT 1 AS exists_flag
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND LOWER(table_name) IN ('summary_daily_sales', 'dimstore', 'dimdate')
        LIMIT 1
        """
    )

    return {
        "db_ok": bool(row.get("ok") == 1),
        "required_tables_available": bool(table_state and table_state.get("exists_flag") == 1),
    }
