from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class CapabilityItem(BaseModel):
    key: str
    enabled: bool
    reason: str


class EmployeeFiltersResponse(BaseModel):
    years: List[int]
    months: List[int]
    stores: List[Dict[str, Any]]
    employees: List[Dict[str, Any]]


class EmployeeDashboardResponse(BaseModel):
    filters: Dict[str, Any]
    kpis: Dict[str, Any]
    top_performer: Optional[Dict[str, Any]]
    comparison: Dict[str, Any]
    capabilities: List[CapabilityItem]


class EmployeeTrendResponse(BaseModel):
    filters: Dict[str, Any]
    rows: List[Dict[str, Any]]


class EmployeeLeaderboardResponse(BaseModel):
    filters: Dict[str, Any]
    rows: List[Dict[str, Any]]


class EmployeeScatterResponse(BaseModel):
    filters: Dict[str, Any]
    rows: List[Dict[str, Any]]
