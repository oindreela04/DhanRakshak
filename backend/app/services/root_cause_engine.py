from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (CheckoutSession, Customer, Invoice, RevenueRiskScore,
                        Subscription, Transaction)
from app.services.recovery_memory import RecoveryMemoryService


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None: return None
    return value.replace(tzinfo=value.tzinfo or timezone.utc)


class RootCauseEngine:
    """Explains revenue risk using stored customer, event, and model evidence."""

    def __init__(self, session: Session):
        self.session = session

    def analyze(self, customer_id: UUID, transaction_id: UUID | None = None) -> dict[str, Any]:
        customer = self.session.get(Customer, customer_id)
        if customer is None: raise ValueError("customer_not_found")
        transactions = list(self.session.scalars(select(Transaction).where(Transaction.customer_id == customer_id).order_by(Transaction.occurred_at)))
        if transaction_id:
            transactions = [transaction for transaction in transactions if transaction.id == transaction_id]
        subscriptions = list(self.session.scalars(select(Subscription).where(Subscription.customer_id == customer_id)))
        invoices = list(self.session.scalars(select(Invoice).where(Invoice.customer_id == customer_id)))
        checkouts = list(self.session.scalars(select(CheckoutSession).where(CheckoutSession.customer_id == customer_id)))
        dna = RecoveryMemoryService(self.session).calculate_recovery_dna(customer_id)
        risk_score = self.session.scalar(select(RevenueRiskScore).where(RevenueRiskScore.customer_id == customer_id).order_by(RevenueRiskScore.created_at.desc()))
        evidence: list[str] = []
        scores: Counter[str] = Counter()
        context: dict[str, Any] = {"customer_id": str(customer_id), "segment": customer.segment, "preferred_payment_method": customer.preferred_payment_method, "preferred_channel": customer.preferred_channel, "risk_score": float(risk_score.score) if risk_score else None}
        if risk_score:
            evidence.append(f"stored ML revenue risk score is {float(risk_score.score):.2f}")

        failures = [row for row in transactions if row.status == "failed"]
        failure_reasons = Counter(row.failure_code for row in failures if row.failure_code)
        failed_methods = Counter(row.payment_method for row in failures if row.payment_method)
        successes_by_method = dna.get("payment_method_success_by_method", {})
        recent_failures = failures[-5:]
        if failure_reasons.get("insufficient_funds"):
            count = failure_reasons["insufficient_funds"]; evidence.append(f"{count} stored transaction failure{'s' if count != 1 else ''} cite insufficient_funds"); scores["temporary_liquidity_issue"] += 3
        if failure_reasons.get("authentication_failure"):
            count = failure_reasons["authentication_failure"]; evidence.append(f"{count} stored transaction failure{'s' if count != 1 else ''} cite authentication_failure"); scores["authentication_friction"] += 3
        if failure_reasons.get("network_error") or failure_reasons.get("bank_declined"):
            count = failure_reasons.get("network_error", 0) + failure_reasons.get("bank_declined", 0); evidence.append(f"{count} stored transaction failure{'s' if count != 1 else ''} cite bank/network instability"); scores["bank_network_instability"] += 2
        if failure_reasons.get("customer_abandoned"):
            count = failure_reasons["customer_abandoned"]; evidence.append(f"{count} stored transaction failure{'s' if count != 1 else ''} cite customer_abandoned"); scores["customer_intent_drop"] += 3
        if customer.preferred_payment_method and failed_methods.get(customer.preferred_payment_method, 0) == 0 and failed_methods:
            method, count = failed_methods.most_common(1)[0]; best_rate = successes_by_method.get(customer.preferred_payment_method, 0); weak_rate = dna.get("payment_method_success_by_method", {}).get(method, 0); evidence.append(f"{count} stored {method} failure{'s' if count != 1 else ''}"); evidence.append(f"historical {customer.preferred_payment_method} success rate is {best_rate:.0%} versus {method} at {weak_rate:.0%}"); scores["payment_method_mismatch"] += 4
        if recent_failures and all((_as_utc(row.occurred_at) or datetime.min.replace(tzinfo=timezone.utc)).hour in {0, 1, 2, 3, 4, 5, 6} for row in recent_failures):
            evidence.append(f"{len(recent_failures)} recent stored failures occurred during the overnight window"); scores["bank_network_instability"] += 1

        abandoned = [row for row in checkouts if row.status == "abandoned"]
        if abandoned:
            evidence.append(f"{len(abandoned)} stored checkout session{'s' if len(abandoned) != 1 else ''} ended abandoned"); scores["checkout_friction"] += 3
        overdue = [row for row in invoices if row.status in {"overdue", "partially_paid"}]
        if overdue:
            evidence.append(f"{len(overdue)} stored invoice{'s' if len(overdue) != 1 else ''} remain{'s' if len(overdue) == 1 else ''} overdue"); scores["invoice_collection_delay"] += 3
        past_due = [row for row in subscriptions if row.status == "past_due"]
        if past_due:
            evidence.append(f"{len(past_due)} stored subscription charge{'s' if len(past_due) != 1 else ''} are past_due"); scores["subscription_payment_method_deterioration"] += 3
        fatigue = float(dna.get("recovery_fatigue_score", 0) or 0)
        if fatigue > 0:
            evidence.append(f"stored recovery fatigue score is {fatigue:.2f}"); scores["recovery_fatigue"] += 3
        if transactions and not failures and not abandoned and not overdue and not past_due:
            evidence.append(f"{len(transactions)} stored transactions do not identify a dominant failure pattern"); scores["unknown"] += 1
        if not evidence:
            evidence.append("no qualifying stored customer events were found")
            scores["unknown"] += 1

        root_cause = scores.most_common(1)[0][0]
        model_support = min(.05, max(0.0, float(risk_score.score) * .05)) if risk_score else 0.0
        confidence = min(.99, .50 + (scores[root_cause] / max(1, sum(scores.values()))) * .40 + min(.09, len(evidence) * .01) + model_support)
        intervention = {"temporary_liquidity_issue": "delayed_retry", "payment_method_mismatch": "payment_link", "authentication_friction": "payment_link", "bank_network_instability": "delayed_retry", "customer_intent_drop": "human_escalation", "checkout_friction": "payment_link", "invoice_collection_delay": "payment_link", "subscription_payment_method_deterioration": "retry_with_preferred_method", "recovery_fatigue": "change_channel", "unknown": "review_manually"}.get(root_cause, "review_manually")
        explanation = f"Stored customer history and current records most strongly support {root_cause.replace('_', ' ')}. " + "; ".join(evidence[:2]) + "."
        context.update({"transaction_count": len(transactions), "failed_transaction_count": len(failures), "subscription_statuses": Counter(row.status for row in subscriptions), "invoice_statuses": Counter(row.status for row in invoices), "checkout_statuses": Counter(row.status for row in checkouts), "recovery_confidence": dna.get("recovery_confidence")})
        return {"root_cause": root_cause, "confidence": round(confidence, 4), "evidence": evidence, "customer_context": context, "recommended_intervention": intervention, "explanation": explanation}
