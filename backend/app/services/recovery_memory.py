from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (Customer, CustomerRecoveryMemory, Invoice, PromiseToPay,
                        RecoveryAction, RecoveryEvent, RecoveryOutcome, Transaction)

PAYMENT_METHODS = ("upi", "credit_card", "debit_card", "netbanking", "wallet", "emi")
CHANNELS = ("whatsapp", "email", "sms")
ACTIONS = ("retry", "payment_link", "whatsapp", "email", "sms", "delayed_retry", "promise_to_pay", "human_escalation", "no_action")


def _rate(successes: int, total: int) -> float:
    return round(successes / total, 4) if total else 0.0


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime): return value.replace(tzinfo=value.tzinfo or timezone.utc)
    if not value: return None
    try: return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError: return None


class RecoveryMemoryService:
    """Builds and updates a persisted, explainable customer recovery snapshot."""

    def __init__(self, session: Session):
        self.session = session

    def build_customer_memory(self, customer_id: UUID) -> dict[str, Any]:
        customer = self.session.get(Customer, customer_id)
        if customer is None: raise ValueError("customer_not_found")
        transactions = list(self.session.scalars(select(Transaction).where(Transaction.customer_id == customer_id)))
        events = list(self.session.scalars(select(RecoveryEvent).where(RecoveryEvent.customer_id == customer_id).order_by(RecoveryEvent.created_at)))
        invoices = list(self.session.scalars(select(Invoice).where(Invoice.customer_id == customer_id)))
        promises = list(self.session.scalars(select(PromiseToPay).where(PromiseToPay.customer_id == customer_id)))
        outcomes = list(self.session.scalars(select(RecoveryOutcome).join(RecoveryAction, RecoveryAction.id == RecoveryOutcome.recovery_action_id).join(RecoveryEvent, RecoveryEvent.id == RecoveryAction.recovery_event_id).where(RecoveryEvent.customer_id == customer_id, RecoveryOutcome.status.in_(["verified", "success", "recovered"]))))
        action_by_outcome = {}
        for outcome in outcomes:
            action = self.session.get(RecoveryAction, outcome.recovery_action_id)
            event = self.session.get(RecoveryEvent, action.recovery_event_id) if action else None
            action_by_outcome[outcome.id] = (action, event)

        payment_totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for transaction in transactions:
            method = str(transaction.payment_method or "").lower()
            if method not in PAYMENT_METHODS: continue
            payment_totals[method][1] += 1
            if transaction.status == "success": payment_totals[method][0] += 1
        channel_totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        action_totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        durations: list[float] = []; attempts: list[float] = []; recovery_hours: dict[int, list[float]] = defaultdict(list); recovery_days: dict[str, list[float]] = defaultdict(list)
        recovered_amount = 0.0; last_success: datetime | None = None; last_failure: datetime | None = None
        for event in events:
            payload = event.payload or {}; channel = str(payload.get("channel", "")).lower(); action_name = str(payload.get("action", event.event_type)).lower()
            if channel in CHANNELS: channel_totals[channel][1] += 1
            if action_name in ACTIONS: action_totals[action_name][1] += 1
            retry_count = payload.get("retry_count")
            if retry_count is not None:
                try: attempts.append(float(retry_count) + 1)
                except (TypeError, ValueError): pass
        for outcome_id, (action, event) in action_by_outcome.items():
            outcome = self.session.get(RecoveryOutcome, outcome_id)
            if outcome is None: continue
            payload = event.payload or {} if event else {}
            channel = str(payload.get("channel", "")).lower(); action_name = action.action_type if action else str(payload.get("action", "no_action"))
            if channel in CHANNELS: channel_totals[channel][0] += 1
            if action_name in ACTIONS: action_totals[action_name][0] += 1
            verified_at = _as_datetime(outcome.verified_at or outcome.updated_at); event_at = _as_datetime(payload.get("timestamp")) or _as_datetime(event.created_at if event else verified_at)
            if verified_at and event_at:
                hours = max(0.0, (verified_at - event_at).total_seconds() / 3600); durations.append(hours); recovery_hours[event_at.hour].append(hours); recovery_days[event_at.strftime("%A")].append(hours)
            recovered_amount += float(outcome.recovered_amount or 0); last_success = max(last_success, verified_at) if last_success and verified_at else verified_at or last_success
        failed_outcomes = list(self.session.scalars(select(RecoveryOutcome).join(RecoveryAction, RecoveryAction.id == RecoveryOutcome.recovery_action_id).join(RecoveryEvent, RecoveryEvent.id == RecoveryAction.recovery_event_id).where(RecoveryEvent.customer_id == customer_id, RecoveryOutcome.status.notin_(["verified", "success", "recovered"]))))
        for outcome in failed_outcomes:
            failed_at = _as_datetime(outcome.updated_at)
            last_failure = max(last_failure, failed_at) if last_failure and failed_at else failed_at or last_failure
        preferred_payment = max(payment_totals, key=lambda key: (payment_totals[key][0], -PAYMENT_METHODS.index(key))) if payment_totals else None
        preferred_channel = max(channel_totals, key=lambda key: (channel_totals[key][0], -CHANNELS.index(key))) if channel_totals else None
        preferred_event = next((event.payload or {} for event in reversed(events) if event.payload), {})
        promise_reliability = _rate(sum(p.status.lower() in {"kept", "paid", "fulfilled", "success"} for p in promises), len(promises))
        opt_outs = sum(str((event.payload or {}).get("outcome", "")).lower() in {"opt_out", "unsubscribed"} for event in events)
        fatigue = min(1.0, max(0.0, (len(events) / 12) * .55 + (opt_outs / max(1, len(events))) * .45))
        total_risk = sum(float((event.payload or {}).get("original_amount", 0) or 0) for event in events)
        payment_success = {method: _rate(*payment_totals[method]) for method in PAYMENT_METHODS}
        recovery_success = {action: _rate(*action_totals[action]) for action in ACTIONS}
        fatigue_label = "HIGH" if fatigue >= .7 else "MEDIUM" if fatigue >= .35 else "LOW"
        dna = {"customer_id": str(customer_id), "payment_method_success_by_method": payment_success, "payment_success": payment_success, "channel_success_by_channel": {channel: _rate(*channel_totals[channel]) for channel in CHANNELS}, "recovery_success_by_action": recovery_success, "recovery_success": recovery_success, "average_recovery_time": round(mean(durations), 2) if durations else 0.0, "average_attempts_before_recovery": round(mean(attempts), 2) if attempts else 0.0, "best_recovery_hour": max(recovery_hours, key=lambda hour: (len(recovery_hours[hour]), -hour)) if recovery_hours else None, "best_recovery_day": max(recovery_days, key=lambda day: (len(recovery_days[day]), day)) if recovery_days else None, "preferred_language": customer.language or preferred_event.get("language"), "preferred_channel": customer.preferred_channel or preferred_channel or preferred_event.get("preferred_channel"), "preferred_payment_method": customer.preferred_payment_method or preferred_payment or preferred_event.get("preferred_payment_method"), "average_invoice_delay": round(mean([max(0, (invoice.due_at - invoice.created_at).days) for invoice in invoices if invoice.due_at and invoice.created_at]), 2) if invoices else 0.0, "promise_to_pay_reliability": promise_reliability, "historical_opt_out_rate": _rate(opt_outs, len(events)), "recovery_fatigue_score": round(fatigue, 4), "recovery_fatigue": fatigue_label, "lifetime_recovered_amount": round(recovered_amount, 2), "lifetime_at_risk_amount": round(total_risk, 2), "last_successful_recovery": last_success.isoformat() if last_success else None, "last_failed_recovery": last_failure.isoformat() if last_failure else None, "recovery_confidence": _rate(len(outcomes), len(outcomes) + len(failed_outcomes))}
        return dna

    def update_after_recovery(self, recovery_outcome_id: UUID) -> dict[str, Any]:
        outcome = self.session.get(RecoveryOutcome, recovery_outcome_id)
        if outcome is None: raise ValueError("recovery_outcome_not_found")
        if outcome.status.lower() not in {"verified", "success", "recovered"}: raise ValueError("recovery_outcome_not_verified")
        action = self.session.get(RecoveryAction, outcome.recovery_action_id)
        event = self.session.get(RecoveryEvent, action.recovery_event_id) if action else None
        if event is None or event.customer_id is None: raise ValueError("recovery_customer_not_found")
        memory = self.get_customer_memory(event.customer_id)
        memory.memory = self.calculate_recovery_dna(event.customer_id)
        self.session.add(memory); self.session.commit(); self.session.refresh(memory)
        return memory.memory or {}

    def get_customer_memory(self, customer_id: UUID) -> CustomerRecoveryMemory:
        memory = self.session.scalar(select(CustomerRecoveryMemory).where(CustomerRecoveryMemory.customer_id == customer_id))
        if memory is None:
            memory = CustomerRecoveryMemory(customer_id=customer_id, memory=self.calculate_recovery_dna(customer_id)); self.session.add(memory); self.session.commit(); self.session.refresh(memory)
        return memory

    def calculate_recovery_dna(self, customer_id: UUID) -> dict[str, Any]:
        return self.build_customer_memory(customer_id)