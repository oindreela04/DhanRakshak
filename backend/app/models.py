from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class UUIDMixin:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)


class Customer(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "customers"
    external_id: Mapped[str | None] = mapped_column(String(128), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    phone: Mapped[str | None] = mapped_column(String(32), index=True)
    name: Mapped[str | None] = mapped_column(String(255))
    segment: Mapped[str | None] = mapped_column(String(32), index=True)
    language: Mapped[str | None] = mapped_column(String(32))
    preferred_channel: Mapped[str | None] = mapped_column(String(32))
    preferred_payment_method: Mapped[str | None] = mapped_column(String(32))


class Transaction(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "transactions"
    customer_id: Mapped[UUID | None] = mapped_column(ForeignKey("customers.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    failure_code: Mapped[str | None] = mapped_column(String(128))
    payment_method: Mapped[str | None] = mapped_column(String(32), index=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class Subscription(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "subscriptions"
    customer_id: Mapped[UUID | None] = mapped_column(ForeignKey("customers.id"), index=True)
    external_id: Mapped[str | None] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))


class Invoice(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "invoices"
    customer_id: Mapped[UUID | None] = mapped_column(ForeignKey("customers.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CheckoutSession(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "checkout_sessions"
    customer_id: Mapped[UUID | None] = mapped_column(ForeignKey("customers.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))


class RecoveryEvent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "recovery_events"
    customer_id: Mapped[UUID | None] = mapped_column(ForeignKey("customers.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class RecoveryAction(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "recovery_actions"
    recovery_event_id: Mapped[UUID | None] = mapped_column(ForeignKey("recovery_events.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    rationale: Mapped[str | None] = mapped_column(Text)


class RecoveryOutcome(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "recovery_outcomes"
    recovery_action_id: Mapped[UUID | None] = mapped_column(ForeignKey("recovery_actions.id"), index=True)
    recovered_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CustomerRecoveryMemory(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "customer_recovery_memory"
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("customers.id"), unique=True, index=True)
    memory: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class RevenueRiskScore(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "revenue_risk_scores"
    customer_id: Mapped[UUID | None] = mapped_column(ForeignKey("customers.id"), index=True)
    score: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    amount_at_risk: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))


class RootCausePrediction(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "root_cause_predictions"
    recovery_event_id: Mapped[UUID | None] = mapped_column(ForeignKey("recovery_events.id"), index=True)
    cause: Mapped[str] = mapped_column(String(128), nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))


class ActionPrediction(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "action_predictions"
    recovery_event_id: Mapped[UUID | None] = mapped_column(ForeignKey("recovery_events.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    probability: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))


class Policy(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "policies"
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    rules: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)


class PromiseToPay(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "promises_to_pay"
    customer_id: Mapped[UUID | None] = mapped_column(ForeignKey("customers.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    promised_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    language: Mapped[str | None] = mapped_column(String(32))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    reminder_status: Mapped[str] = mapped_column(String(32), default="scheduled", nullable=False)


class AuditLog(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "audit_logs"
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class Experiment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "experiments"
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    configuration: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ModelVersion(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "model_versions"
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class WebhookEvent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "webhook_events"
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)


class NotificationEvent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "notification_events"
    customer_id: Mapped[UUID | None] = mapped_column(ForeignKey("customers.id"), index=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)


Index("ix_transactions_customer_status", Transaction.customer_id, Transaction.status)
Index("ix_recovery_events_customer_created", RecoveryEvent.customer_id, RecoveryEvent.created_at)
