from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class EventRequest(BaseModel):
    customer_id: UUID | None = None
    event_type: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)


class EventResponse(BaseModel):
    id: UUID
    event_type: str
    customer_id: UUID | None
    accepted: bool


class CustomerResponse(BaseModel):
    id: UUID
    external_id: str | None = None
    name: str | None = None
    email: str | None = None
    segment: str | None = None


class CustomerListResponse(BaseModel):
    items: list[CustomerResponse]
    total: int


class RecoveryRequest(BaseModel):
    customer_id: UUID
    amount: float = Field(gt=0)
    payment_method: str = "upi"
    failure_reason: str = "unknown"
    channel: str | None = None
    action: str | None = None


class ActionRequest(RecoveryRequest):
    action: str = Field(min_length=1)


class StopRequest(BaseModel):
    customer_id: UUID
    reason: str = Field(min_length=1)


class RecoveryDecisionResponse(BaseModel):
    customer_id: UUID
    decision: str
    state: str
    root_cause: dict[str, Any]
    actions: list[dict[str, Any]]
    policy: dict[str, Any]


class PromiseRequest(BaseModel):
    customer_id: UUID
    text: str = Field(min_length=1)
    amount: float | None = Field(default=None, gt=0)


class PromiseResponse(BaseModel):
    id: UUID
    customer_id: UUID
    amount: float
    promised_for: datetime
    language: str
    confidence: float
    status: str


class GenericResponse(BaseModel):
    status: str
    data: dict[str, Any] = Field(default_factory=dict)


class PolicyRequest(BaseModel):
    customer_id: UUID
    amount: float = Field(gt=0)
    model_confidence: float = Field(ge=0, le=1)
    action: str
    messages_last_7_days: int = Field(default=0, ge=0)
    total_actions: int = Field(default=0, ge=0)
    attempts: int = Field(default=0, ge=0)
    discount_percent: float = Field(default=0, ge=0)
    expected_incremental_recovery: float = Field(default=0, ge=0)


class ExperimentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    configuration: dict[str, Any] = Field(default_factory=dict)
    active: bool = False


class WebhookResponse(BaseModel):
    event_id: UUID | None = None
    duplicate: bool = False
    accepted: bool


class RecoveryTwinResponse(BaseModel):
    baseline_at_risk: float
    organic_recovery: float
    assisted_recovery: float
    incremental_recovery: float
    recovery_rate_without_dhanrakshak: float
    recovery_rate_with_dhanrakshak: float
    confidence: float
    sample_size: int
