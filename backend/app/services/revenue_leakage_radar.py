from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean, pstdev
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (CheckoutSession, Customer, CustomerRecoveryMemory, Invoice,
                        PromiseToPay, RecoveryEvent, RecoveryOutcome, Subscription,
                        Transaction)


def _aware(value: datetime | None) -> datetime | None:
    if value is None: return None
    return value.replace(tzinfo=value.tzinfo or timezone.utc)


def _event_time(event: RecoveryEvent) -> datetime:
    payload = event.payload or {}
    value = payload.get("timestamp")
    if value:
        try: return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError: pass
    return _aware(event.created_at) or datetime.now(timezone.utc)


def _rate(successes: int, total: int) -> float:
    return successes / total if total else 0.0


def _relative_change(current: float, baseline: float) -> float:
    if baseline == 0: return 1.0 if current > 0 else 0.0
    return max(-1.0, min(3.0, (current - baseline) / baseline))


def _normalize(value: float) -> float:
    return max(0.0, min(1.0, value))


class RevenueLeakageRadar:
    """Detects revenue leakage from persisted behavior and rolling baselines."""

    def __init__(self, session: Session, window_days: int = 30):
        self.session = session
        self.window_days = window_days

    def _records(self) -> dict[str, list[Any]]:
        return {"customers": list(self.session.scalars(select(Customer))), "transactions": list(self.session.scalars(select(Transaction))), "checkouts": list(self.session.scalars(select(CheckoutSession))), "subscriptions": list(self.session.scalars(select(Subscription))), "invoices": list(self.session.scalars(select(Invoice))), "promises": list(self.session.scalars(select(PromiseToPay))), "events": list(self.session.scalars(select(RecoveryEvent))), "outcomes": list(self.session.scalars(select(RecoveryOutcome))), "memories": list(self.session.scalars(select(CustomerRecoveryMemory)))}

    def _anchor(self, records: dict[str, list[Any]]) -> datetime:
        timestamps: list[datetime] = []
        timestamps.extend(_aware(row.occurred_at) for row in records["transactions"] if row.occurred_at)
        timestamps.extend(_event_time(row) for row in records["events"])
        timestamps.extend(_aware(row.due_at) for row in records["invoices"] if row.due_at)
        timestamps.extend(_aware(row.promised_for) for row in records["promises"] if row.promised_for)
        timestamps.extend(_aware(row.created_at) for row in records["subscriptions"] if row.created_at)
        return max((value for value in timestamps if value), default=datetime.now(timezone.utc))

    def _window(self, timestamp: datetime | None, anchor: datetime, current: bool) -> bool:
        if timestamp is None: return False
        timestamp = _aware(timestamp)
        start = anchor - timedelta(days=self.window_days if current else self.window_days * 2)
        end = anchor if current else anchor - timedelta(days=self.window_days)
        return start <= timestamp <= end

    def _opportunity(self, reason: str, score: float, amount: float, confidence: float, root_cause: str, time_to_intervene: str, action: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"reason": reason, "risk_score": round(_normalize(score), 4), "amount_at_risk": round(max(0.0, amount), 2), "confidence": round(_normalize(confidence), 4), "root_cause_candidate": root_cause, "time_to_intervene": time_to_intervene, "recommended_action": action, "details": details or {}}

    def _index(self, reason: str, score: float, amount: float, confidence: float, root_cause: str, action: str) -> dict[str, Any]:
        return self._opportunity(reason, score, amount, confidence, root_cause, "within_24_hours", action)

    def calculate_radar(self) -> dict[str, Any]:
        records = self._records(); anchor = self._anchor(records); current_start = anchor - timedelta(days=self.window_days); previous_start = current_start - timedelta(days=self.window_days)
        opportunities: list[dict[str, Any]] = []
        reason_amounts: defaultdict[str, float] = defaultdict(float); segment_amounts: defaultdict[str, float] = defaultdict(float); method_amounts: defaultdict[str, float] = defaultdict(float)
        tx_current = [row for row in records["transactions"] if self._window(row.occurred_at, anchor, True)]; tx_previous = [row for row in records["transactions"] if self._window(row.occurred_at, anchor, False)]

        def add(opportunity: dict[str, Any]) -> None:
            opportunities.append(opportunity); reason_amounts[opportunity["reason"]] += opportunity["amount_at_risk"]

        # Payment degradation: current failed-value rate versus the prior rolling window.
        current_failed = sum(float(row.amount) for row in tx_current if row.status == "failed"); previous_failed = sum(float(row.amount) for row in tx_previous if row.status == "failed")
        current_failure_rate = _rate(sum(row.status == "failed" for row in tx_current), len(tx_current)); previous_failure_rate = _rate(sum(row.status == "failed" for row in tx_previous), len(tx_previous)); degradation = max(0.0, _relative_change(current_failure_rate, previous_failure_rate)); recovery_outcomes = records["outcomes"]; recovery_difficulty = 1 - _rate(sum(str(row.status).lower() in {"verified", "success", "recovered"} for row in recovery_outcomes), len(recovery_outcomes))
        if degradation > 0:
            add(self._index("payment_degradation", _normalize(degradation * .4 + current_failure_rate * .3 + recovery_difficulty * .3), current_failed, _normalize(.5 + min(.5, len(tx_current) / 1000)), "payment_failure_rate_above_rolling_baseline", "inspect_failure_reasons_and_route_retries"))
            add(self._opportunity("merchant_level_anomaly", _normalize(degradation * .6 + recovery_difficulty * .4), current_failed, _normalize(.45 + min(.55, len(tx_current) / 1000)), "merchant_failure_exposure_shifted_from_rolling_baseline", "within_24_hours", "inspect_provider_and_failure_mix"))

        # Payment method degradation uses method-specific rolling failure rates.
        methods = sorted({row.payment_method for row in tx_current + tx_previous if row.payment_method})
        for method in methods:
            now = [row for row in tx_current if row.payment_method == method]; prior = [row for row in tx_previous if row.payment_method == method]; now_rate = _rate(sum(row.status == "failed" for row in now), len(now)); prior_rate = _rate(sum(row.status == "failed" for row in prior), len(prior)); delta = max(0.0, _relative_change(now_rate, prior_rate)); amount = sum(float(row.amount) for row in now if row.status == "failed")
            method_amounts[method] += amount
            if delta > 0 and amount > 0: add(self._opportunity("payment_method_degradation", delta * .65 + now_rate * .35, amount, _normalize(.4 + len(now) / 500), f"{method}_failure_rate_above_rolling_baseline", "within_24_hours", "offer_alternate_payment_method", {"payment_method": method, "current_failure_rate": now_rate, "baseline_failure_rate": prior_rate}))

        # Customer-level sudden behavior change and concentration use actual customer aggregates.
        by_customer: dict[Any, list[Transaction]] = defaultdict(list)
        for row in tx_current + tx_previous: by_customer[row.customer_id].append(row)
        customer_lookup = {row.id: row for row in records["customers"]}
        for customer_id, rows in by_customer.items():
            now = [row for row in rows if self._window(row.occurred_at, anchor, True)]; prior = [row for row in rows if self._window(row.occurred_at, anchor, False)]; now_rate = _rate(sum(row.status == "failed" for row in now), len(now)); prior_rate = _rate(sum(row.status == "failed" for row in prior), len(prior)); delta = max(0.0, _relative_change(now_rate, prior_rate)); amount = sum(float(row.amount) for row in now if row.status == "failed")
            if delta > 0 and amount > 0: add(self._opportunity("sudden_customer_behavior_change", delta * .6 + now_rate * .4, amount, _normalize(.45 + len(rows) / 100), "customer_failure_rate_shifted_from_rolling_baseline", "within_48_hours", "review_customer_recovery_dna", {"customer_id": str(customer_id), "segment": getattr(customer_lookup.get(customer_id), "segment", None)}))

        # Checkout abandonment and invoice ageing use current-period exposure.
        checkout_current = [row for row in records["checkouts"] if self._window(row.created_at, anchor, True)]; checkout_previous = [row for row in records["checkouts"] if self._window(row.created_at, anchor, False)]
        abandonment = _rate(sum(row.status == "abandoned" for row in checkout_current), len(checkout_current)); baseline_abandonment = _rate(sum(row.status == "abandoned" for row in checkout_previous), len(checkout_previous)); abandon_delta = max(0.0, _relative_change(abandonment, baseline_abandonment)); abandoned_value = sum(float(row.amount or 0) for row in checkout_current if row.status == "abandoned")
        if abandon_delta > 0 and abandoned_value > 0: add(self._opportunity("checkout_abandonment", abandon_delta * .65 + abandonment * .35, abandoned_value, _normalize(.45 + len(checkout_current) / 1000), "checkout_abandonment_above_rolling_baseline", "within_6_hours", "send_contextual_payment_link"))

        overdue = [row for row in records["invoices"] if row.status in {"overdue", "partially_paid"} and row.due_at and _aware(row.due_at) <= anchor]; overdue_value = sum(float(row.amount) for row in overdue); ageing = mean([(anchor - _aware(row.due_at)).days for row in overdue]) if overdue else 0
        if overdue_value > 0: add(self._opportunity("invoice_ageing", _normalize(ageing / max(1, self.window_days) * .6 + overdue_value / max(1, sum(float(row.amount) for row in records["invoices"])) * .4), overdue_value, _normalize(.5 + len(overdue) / 1000), "invoice_due_date_passed", "within_24_hours", "send_invoice_payment_link", {"average_days_overdue": round(ageing, 2)}))

        # Subscriptions and promises are event-like current facts; compare current counts to prior activity.
        past_due = [row for row in records["subscriptions"] if row.status == "past_due"]
        if past_due: add(self._opportunity("subscription_deterioration", _normalize(len(past_due) / max(1, len(records["subscriptions"]))), sum(float(row.amount or 0) for row in past_due), _normalize(.5 + len(past_due) / 500), "subscription_past_due", "within_24_hours", "retry_with_preferred_method"))
        missed = [row for row in records["promises"] if row.status.lower() in {"missed", "broken", "defaulted"} and _aware(row.promised_for) <= anchor]
        if missed: add(self._opportunity("missed_promise_to_pay", _normalize(len(missed) / max(1, len(records["promises"]))), sum(float(row.amount) for row in missed), _normalize(.5 + len(missed) / 500), "promise_to_pay_missed", "within_6_hours", "escalate_with_human_review"))

        memories = [row.memory or {} for row in records["memories"] if row.memory]; fatigued = [memory for memory in memories if memory.get("recovery_fatigue") in {"MEDIUM", "HIGH"}]; fatigue_amount = sum(float(memory.get("lifetime_at_risk_amount", 0) or 0) for memory in fatigued)
        if fatigued: add(self._opportunity("recovery_fatigue", _normalize(len(fatigued) / max(1, len(memories))), fatigue_amount, _normalize(.5 + len(fatigued) / max(1, len(memories))), "repeated_recovery_attempts_without_verified_success", "within_48_hours", "reduce_contact_frequency_and_change_channel"))

        total_current = sum(float(row.amount) for row in tx_current); top_segment = Counter(customer_lookup.get(row.customer_id).segment if customer_lookup.get(row.customer_id) else "unknown" for row in tx_current).most_common(1); concentration = top_segment[0][1] / max(1, len(tx_current)) if top_segment else 0
        if concentration > 0: add(self._opportunity("revenue_concentration_risk", concentration, total_current * concentration, _normalize(.4 + len(tx_current) / 1000), "revenue_concentrated_in_single_customer_segment", "within_7_days", "monitor_segment_exposure", {"top_segment": top_segment[0][0] if top_segment else None, "share": concentration}))

        for row in tx_current:
            customer = customer_lookup.get(row.customer_id)
            if row.status == "failed":
                segment_amounts[getattr(customer, "segment", None) or "unknown"] += float(row.amount)
                method_amounts[row.payment_method or "unknown"] += float(row.amount)
        for opportunity in opportunities:
            opportunity["revenue_risk_index"] = opportunity["risk_score"]
            if opportunity["reason"] not in {"revenue_risk_index", "revenue_concentration_risk"}: segment = opportunity["details"].get("segment") if opportunity["details"] else None; method = opportunity["details"].get("payment_method") if opportunity["details"] else None; segment_amounts[segment or "unknown"] += opportunity["amount_at_risk"]; method_amounts[method or "unknown"] += opportunity["amount_at_risk"]
        opportunities.sort(key=lambda item: (item["risk_score"] * item["amount_at_risk"]), reverse=True)
        high = sum(item["amount_at_risk"] for item in opportunities if item["risk_score"] >= .67); medium = sum(item["amount_at_risk"] for item in opportunities if .34 <= item["risk_score"] < .67); low = sum(item["amount_at_risk"] for item in opportunities if item["risk_score"] < .34)
        trend = {"anchor": anchor.isoformat(), "window_days": self.window_days, "current_failed_amount": round(current_failed, 2), "previous_failed_amount": round(previous_failed, 2), "failure_rate": round(current_failure_rate, 4), "baseline_failure_rate": round(previous_failure_rate, 4), "direction": "worsening" if current_failure_rate > previous_failure_rate else "improving" if current_failure_rate < previous_failure_rate else "stable"}
        return {"total_revenue_at_risk": round(sum(item["amount_at_risk"] for item in opportunities), 2), "high_risk_revenue": round(high, 2), "medium_risk_revenue": round(medium, 2), "low_risk_revenue": round(low, 2), "top_risk_events": opportunities[:20], "risk_by_reason": {key: round(value, 2) for key, value in sorted(reason_amounts.items(), key=lambda pair: pair[1], reverse=True)}, "risk_by_segment": {key: round(value, 2) for key, value in segment_amounts.items()}, "risk_by_payment_method": {key: round(value, 2) for key, value in method_amounts.items()}, "risk_trend": trend}
