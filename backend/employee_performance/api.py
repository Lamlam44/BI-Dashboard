from typing import Optional

from fastapi import APIRouter

try:
    from db_utils import serialize_payload
except ImportError:
    from ..db_utils import serialize_payload
from .metrics import get_dashboard, get_filters, get_leaderboard, get_scatter, get_trend, health_check
from .schemas import (
    EmployeeDashboardResponse,
    EmployeeFiltersResponse,
    EmployeeLeaderboardResponse,
    EmployeeScatterResponse,
    EmployeeTrendResponse,
)


router = APIRouter(prefix="/employee-performance", tags=["employee-performance"])


@router.get("/health")
def employee_performance_health():
    return serialize_payload(health_check())


@router.get("/filters", response_model=EmployeeFiltersResponse)
def employee_performance_filters():
    return serialize_payload(get_filters())


@router.get("/dashboard", response_model=EmployeeDashboardResponse)
def employee_performance_dashboard(
    year: Optional[int] = None,
    month: Optional[int] = None,
    employee_key: Optional[int] = None,
    store_key: Optional[int] = None,
):
    payload = get_dashboard(year=year, month=month, employee_key=employee_key, store_key=store_key)
    return serialize_payload(payload)


@router.get("/trend", response_model=EmployeeTrendResponse)
def employee_performance_trend(
    year: Optional[int] = None,
    employee_key: Optional[int] = None,
    store_key: Optional[int] = None,
):
    payload = get_trend(year=year, employee_key=employee_key, store_key=store_key)
    return serialize_payload(payload)


@router.get("/leaderboard", response_model=EmployeeLeaderboardResponse)
def employee_performance_leaderboard(
    year: Optional[int] = None,
    month: Optional[int] = None,
    store_key: Optional[int] = None,
    top_n: int = 10,
):
    payload = get_leaderboard(year=year, month=month, store_key=store_key, top_n=top_n)
    return serialize_payload(payload)


@router.get("/scatter", response_model=EmployeeScatterResponse)
def employee_performance_scatter(
    year: Optional[int] = None,
    month: Optional[int] = None,
    store_key: Optional[int] = None,
):
    payload = get_scatter(year=year, month=month, store_key=store_key)
    return serialize_payload(payload)
