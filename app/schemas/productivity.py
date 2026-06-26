from datetime import date as date_type, datetime
from typing import Any, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class KPITrend(BaseModel):
    current_value: float
    previous_value: float
    change_percentage: str
    direction: str


class KPIDetail(BaseModel):
    raw_seconds: int
    hours: float
    minutes: float
    formatted: str
    percentage: float
    status: str
    color: str
    tooltip: str
    formula: str
    trend: Optional[KPITrend] = None


class ProductivityKPIResponse(BaseModel):
    employee_id: UUID
    date: date_type
    kpis: dict[str, KPIDetail]


class TimelineEventResponse(BaseModel):
    time: str
    event_type: str
    title: str
    description: str
    metadata: dict[str, Any]


class IdleReasonResponse(BaseModel):
    id: UUID
    code: str
    name: str
    description: Optional[str] = None
    display_order: int
    color: Optional[str] = None
    department_id: Optional[UUID] = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class IdleClassificationCreate(BaseModel):
    date: date_type
    idle_segment_identifier: str
    reason_id: UUID
    remarks: Optional[str] = None


class IdleClassificationResponse(BaseModel):
    id: UUID
    employee_id: UUID
    date: date_type
    idle_segment_identifier: str
    reason_id: UUID
    remarks: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class DailySummaryItem(BaseModel):
    date: str
    kpis: dict[str, KPIDetail]


class RangeProductivityResponse(BaseModel):
    employee_id: UUID
    start_date: date_type
    end_date: date_type
    period_kpis: dict[str, KPIDetail]
    days: list[DailySummaryItem]
