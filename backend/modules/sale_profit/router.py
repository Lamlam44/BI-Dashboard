import logging
import threading
from typing import List, Optional

from fastapi import APIRouter, Depends

from core.database import serialize_payload, get_engine

from core.auth import UserContext, get_current_user, get_rls_store_keys

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
        # If Parquet cache already exists, just load it (fast).
        # Only rebuild from DB if the file is missing.
        from .service import load_sales_profit_snapshot, _parquet_has_data
        if _parquet_has_data():
            load_sales_profit_snapshot(force_refresh=False)
            logger.info("Sale profit cache warmup completed (loaded existing file).")
        else:
            refresh_sales_profit_cache()
            logger.info("Sale profit cache warmup completed (rebuilt from DB).")
    except Exception as exc:
        logger.warning(f"Sale profit cache warmup skipped: {exc}")
    # Warm up the two direct-DB endpoints that are slow on first call
    try:
        get_sales_per_sqft()
        logger.info("sales_per_sqft cache warmed up.")
    except Exception as exc:
        logger.warning(f"sales_per_sqft warmup skipped: {exc}")
    try:
        get_budget_vs_actual()
        logger.info("budget_vs_actual cache warmed up.")
    except Exception as exc:
        logger.warning(f"budget_vs_actual warmup skipped: {exc}")


def sale_profit_startup_warmup() -> None:
    threading.Thread(target=_warm_cache_background, daemon=True).start()


sale_profit_startup_warmup()


@router.get("/api/dashboard/sales")
def sale_profit_dashboard(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    store_key: Optional[int] = None,
    user: UserContext = Depends(get_current_user),
):
    rls_keys = get_rls_store_keys(get_engine(), user)
    # If user explicitly passes store_key AND it's allowed by RLS, use it.
    effective_store_key = store_key
    if rls_keys is not None and store_key is not None and store_key not in rls_keys:
        effective_store_key = rls_keys[0] if rls_keys else None
    payload = get_sales_profit_dashboard(
        start_date=start_date, end_date=end_date,
        store_key=effective_store_key, rls_store_keys=rls_keys,
    )
    return serialize_payload(payload)


@router.post("/cache/refresh")
def sale_profit_refresh_cache(user: UserContext = Depends(get_current_user)):
    threading.Thread(target=_warm_cache_background, daemon=True).start()
    return serialize_payload({
        "status": "accepted",
        "message": "Sale profit cache refresh started in background.",
    })


@router.get("/api/channels")
def sale_profit_channels(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user: UserContext = Depends(get_current_user),
):
    rls_keys = get_rls_store_keys(get_engine(), user)
    payload = get_channel_breakdown(start_date=start_date, end_date=end_date, rls_store_keys=rls_keys)
    return serialize_payload(payload)


@router.get("/api/kpi-summary")
def sale_profit_kpi_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user: UserContext = Depends(get_current_user),
):
    rls_keys = get_rls_store_keys(get_engine(), user)
    payload = get_kpi_summary(start_date=start_date, end_date=end_date, rls_store_keys=rls_keys)
    return serialize_payload(payload)


@router.get("/api/sales-per-sqft")
def sale_profit_sales_per_sqft(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user: UserContext = Depends(get_current_user),
):
    rls_keys = get_rls_store_keys(get_engine(), user)
    payload = get_sales_per_sqft(start_date=start_date, end_date=end_date, rls_store_keys=rls_keys)
    return serialize_payload(payload)


@router.get("/api/budget-vs-actual")
def sale_profit_budget_vs_actual(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user: UserContext = Depends(get_current_user),
):
    rls_keys = get_rls_store_keys(get_engine(), user)
    payload = get_budget_vs_actual(start_date=start_date, end_date=end_date, rls_store_keys=rls_keys)
    return serialize_payload(payload)

