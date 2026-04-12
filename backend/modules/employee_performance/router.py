from typing import Optional
import logging
import threading

from fastapi import APIRouter, Depends

from core.database import serialize_payload, get_engine

from core.auth import UserContext, get_current_user, get_rls_store_keys

from .service import get_dashboard, get_filters, get_leaderboard, get_scatter, get_trend, health_check
from .schemas import (
    EmployeeDashboardResponse,
    EmployeeFiltersResponse,
    EmployeeLeaderboardResponse,
    EmployeeScatterResponse,
    EmployeeTrendResponse,
)


router = APIRouter(prefix="/employee-performance", tags=["employee-performance"])
logger = logging.getLogger(__name__)


def _resolve_rls(user: UserContext, store_key: Optional[int] = None) -> Optional[int]:
    """Return effective store_key for RLS.
    - admin/executive: returns caller's store_key param unchanged (may be None=all)
    - store_manager: always their own store
    - regional_manager: only stores in their region (returns store_key if in region, else None which
      will be filtered in the metrics functions via rls_store_keys)
    """
    if user.role in ("admin", "executive") or user.is_anonymous:
        return store_key
    if user.role == "store_manager" and user.store_key is not None:
        return user.store_key
    # regional_manager â€” let it pass through; we'll filter later per-query or
    # via store_key if it's within their region
    return store_key


def _warm_cache_background() -> None:
    try:
        # Prime cache for the most common initial page load.
        get_filters()
        get_dashboard()
        get_trend()
        get_leaderboard(top_n=10)
        get_scatter()
        logger.info("Employee performance cache warmup completed.")
    except Exception as exc:
        logger.warning(f"Employee performance cache warmup skipped: {exc}")


def employee_performance_startup_warmup() -> None:
    threading.Thread(target=_warm_cache_background, daemon=True).start()


employee_performance_startup_warmup()


@router.get("/health")
def employee_performance_health():
    return serialize_payload(health_check())


@router.get("/filters", response_model=EmployeeFiltersResponse)
def employee_performance_filters(user: UserContext = Depends(get_current_user)):
    cached = get_filters()
    # Copy to avoid mutating the cached object when applying RLS store filter
    result = {**cached, "stores": list(cached["stores"])}
    rls_keys = get_rls_store_keys(get_engine(), user)
    if rls_keys is not None:
        result["stores"] = [s for s in result["stores"] if s.get("store_key") in rls_keys]
    return serialize_payload(result)


@router.get("/dashboard", response_model=EmployeeDashboardResponse)
def employee_performance_dashboard(
    year: Optional[int] = None,
    month: Optional[int] = None,
    employee_key: Optional[int] = None,
    store_key: Optional[int] = None,
    user: UserContext = Depends(get_current_user),
):
    sk = _resolve_rls(user, store_key)
    payload = get_dashboard(year=year, month=month, employee_key=employee_key, store_key=sk)
    return serialize_payload(payload)


@router.get("/trend", response_model=EmployeeTrendResponse)
def employee_performance_trend(
    year: Optional[int] = None,
    employee_key: Optional[int] = None,
    store_key: Optional[int] = None,
    user: UserContext = Depends(get_current_user),
):
    sk = _resolve_rls(user, store_key)
    payload = get_trend(year=year, employee_key=employee_key, store_key=sk)
    return serialize_payload(payload)


@router.get("/leaderboard", response_model=EmployeeLeaderboardResponse)
def employee_performance_leaderboard(
    year: Optional[int] = None,
    month: Optional[int] = None,
    store_key: Optional[int] = None,
    top_n: int = 10,
    user: UserContext = Depends(get_current_user),
):
    sk = _resolve_rls(user, store_key)
    payload = get_leaderboard(year=year, month=month, store_key=sk, top_n=top_n)
    return serialize_payload(payload)


@router.get("/scatter", response_model=EmployeeScatterResponse)
def employee_performance_scatter(
    year: Optional[int] = None,
    month: Optional[int] = None,
    store_key: Optional[int] = None,
    user: UserContext = Depends(get_current_user),
):
    sk = _resolve_rls(user, store_key)
    payload = get_scatter(year=year, month=month, store_key=sk)
    return serialize_payload(payload)

