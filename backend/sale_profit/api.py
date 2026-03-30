import logging
import threading
from typing import Optional

from fastapi import APIRouter

try:
    from db_utils import serialize_payload
except ImportError:
    from ..db_utils import serialize_payload

from .service import (
    get_sales_profit_dashboard,
    refresh_sales_profit_cache,
    get_channel_breakdown,
    get_kpi_summary,
    get_sales_per_sqft,
    get_budget_vs_actual,
)

router = APIRouter(prefix="/sale-profit", tags=["sale-profit"])
logger = logging.getLogger(__name__)


def _warm_cache_background() -> None:
    try:
        # Build parquet cache in background so first dashboard load is faster.
        refresh_sales_profit_cache()
        logger.info("Sale profit cache warmup completed.")
    except Exception as exc:
        logger.warning(f"Sale profit cache warmup skipped: {exc}")


@router.on_event("startup")
def sale_profit_startup_warmup() -> None:
    threading.Thread(target=_warm_cache_background, daemon=True).start()


@router.get("/api/dashboard/sales")
def sale_profit_dashboard(start_date: Optional[str] = None, end_date: Optional[str] = None):
    payload = get_sales_profit_dashboard(start_date=start_date, end_date=end_date)
    return serialize_payload(payload)


@router.post("/cache/refresh")
def sale_profit_refresh_cache():
    threading.Thread(target=_warm_cache_background, daemon=True).start()
    return serialize_payload({
        "status": "accepted",
        "message": "Sale profit cache refresh started in background.",
    })


@router.get("/api/channels")
def sale_profit_channels(start_date: Optional[str] = None, end_date: Optional[str] = None):
    payload = get_channel_breakdown(start_date=start_date, end_date=end_date)
    return serialize_payload(payload)


@router.get("/api/kpi-summary")
def sale_profit_kpi_summary(start_date: Optional[str] = None, end_date: Optional[str] = None):
    payload = get_kpi_summary(start_date=start_date, end_date=end_date)
    return serialize_payload(payload)


@router.get("/api/sales-per-sqft")
def sale_profit_sales_per_sqft(start_date: Optional[str] = None, end_date: Optional[str] = None):
    payload = get_sales_per_sqft(start_date=start_date, end_date=end_date)
    return serialize_payload(payload)


@router.get("/api/budget-vs-actual")
def sale_profit_budget_vs_actual(start_date: Optional[str] = None, end_date: Optional[str] = None):
    payload = get_budget_vs_actual(start_date=start_date, end_date=end_date)
    return serialize_payload(payload)
