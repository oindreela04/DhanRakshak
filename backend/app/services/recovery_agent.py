from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.models import (AuditLog, RecoveryAction, RecoveryEvent, RecoveryOutcome,
                        Transaction)
from app.services.policy_guard import PolicyGuard
from app.services.recovery_economics import RecoveryEconomicsService
from app.services.root_cause_engine import RootCauseEngine


class RecoveryAgent:
    """Bounded recovery workflow. Every executable action is policy checked."""

    def __init__(self, session): self.session = session

    def get_customer_history(self, customer_id: UUID) -> dict[str, Any]:
        return {"transactions": [row.id for row in self.session.scalars(select(Transaction).where(Transaction.customer_id == customer_id))]}

    def get_transaction_history(self, customer_id: UUID) -> list[Transaction]:
        return list(self.session.scalars(select(Transaction).where(Transaction.customer_id == customer_id).order_by(Transaction.occurred_at)))

    def get_revenue_risk(self, customer_id: UUID) -> dict[str, Any]:
        from app.services.revenue_leakage_radar import RevenueLeakageRadar
        return {"customer_id": str(customer_id), "radar": RevenueLeakageRadar(self.session).calculate_radar()}

    def get_root_cause(self, customer_id: UUID) -> dict[str, Any]: return RootCauseEngine(self.session).analyze(customer_id)

    def predict_action_recovery(self, customer_id: UUID, amount: float, payment_method: str) -> list[dict[str, Any]]: return RecoveryEconomicsService(self.session).rank_actions(customer_id, amount, payment_method)

    def calculate_expected_recovery(self, customer_id: UUID, amount: float, action: str, payment_method: str) -> dict[str, Any]: return RecoveryEconomicsService(self.session).simulate(customer_id, amount, action, payment_method)

    def check_policy(self, customer_id: UUID, amount: float, action: str, expected: dict[str, Any], confidence: float) -> dict[str, Any]: return PolicyGuard(self.session).check(customer_id, amount, action, confidence, expected_incremental_recovery=expected["expected_incremental_recovery_value"])

    def decide(self, customer_id: UUID, amount: float, payment_method: str) -> dict[str, Any]:
        root = self.get_root_cause(customer_id); actions = self.predict_action_recovery(customer_id, amount, payment_method); selected = actions[0]; policy = self.check_policy(customer_id, amount, selected["action"], selected, root["confidence"]); state = "RECOMMENDED" if policy["decision"] == "ALLOW" else "ESCALATED" if policy["decision"] == "ESCALATE" else "STOPPED"
        return {"customer_id": customer_id, "decision": policy["decision"], "state": state, "root_cause": root, "actions": actions, "policy": policy}

    def execute(self, customer_id: UUID, amount: float, action: str, payment_method: str) -> dict[str, Any]:
        decision = self.decide(customer_id, amount, payment_method)
        selected = next((item for item in decision["actions"] if item["action"] == action), decision["actions"][0]); policy = self.check_policy(customer_id, amount, selected["action"], selected, decision["root_cause"]["confidence"])
        if policy["decision"] != "ALLOW": return {**decision, "policy": policy, "state": "ESCALATED" if policy["decision"] == "ESCALATE" else "STOPPED"}
        event = RecoveryEvent(customer_id=customer_id, event_type="recovery_action", payload={"action": action, "amount": amount, "payment_method": payment_method, "created_by": "recovery_agent"}); self.session.add(event); self.session.flush()
        recovery_action = RecoveryAction(recovery_event_id=event.id, action_type=action, status="EXECUTED", rationale=decision["root_cause"]["explanation"]); self.session.add(recovery_action); self.session.commit()
        return {"customer_id": customer_id, "state": "VERIFICATION_PENDING", "action_id": recovery_action.id, "policy": policy, "decision": "ALLOW"}

    def stop(self, customer_id: UUID, reason: str) -> dict[str, Any]:
        actions = list(self.session.scalars(select(RecoveryAction).join(RecoveryEvent, RecoveryEvent.id == RecoveryAction.recovery_event_id).where(RecoveryEvent.customer_id == customer_id, RecoveryAction.status.in_(["EXECUTED", "RECOMMENDED", "VERIFICATION_PENDING"]))))
        for action in actions: action.status = "STOPPED"
        self.session.add(AuditLog(action="recovery_stop", actor="recovery_agent", details={"customer_id": str(customer_id), "reason": reason, "timestamp": datetime.now(timezone.utc).isoformat()})); self.session.commit()
        return {"customer_id": customer_id, "state": "STOPPED", "stopped_actions": len(actions), "reason": reason}

    def record_recovery_outcome(self, action_id: UUID, status: str, amount: float = 0) -> dict[str, Any]:
        outcome = RecoveryOutcome(recovery_action_id=action_id, status=status, recovered_amount=Decimal(str(amount)) if amount else None, verified_at=datetime.now(timezone.utc) if status.lower() in {"verified", "recovered", "success"} else None); self.session.add(outcome); self.session.commit(); return {"outcome_id": outcome.id, "status": status}