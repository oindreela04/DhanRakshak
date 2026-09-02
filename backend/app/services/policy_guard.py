from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.models import AuditLog

DEFAULT_RULES = {"max_attempts": 3, "max_messages_per_7_days": 2, "max_total_recovery_actions": 3, "max_discount_percent": 10, "require_human_above_amount": 100000, "stop_on_success": True, "stop_on_opt_out": True, "stop_on_dispute": True, "stop_on_fraud_signal": True, "minimum_model_confidence": .65, "minimum_expected_incremental_recovery": 100}


class PolicyGuard:
    def __init__(self, session, rules: dict[str, Any] | None = None): self.session, self.rules = session, {**DEFAULT_RULES, **(rules or {})}

    def check(self, customer_id: UUID, amount: float, action: str, model_confidence: float, attempts: int = 0, messages_last_7_days: int = 0, total_actions: int = 0, discount_percent: float = 0, expected_incremental_recovery: float = 0, opt_out: bool = False, success: bool = False, dispute: bool = False, fraud_signal: bool = False) -> dict[str, Any]:
        failed: list[str] = []
        if attempts >= self.rules["max_attempts"]: failed.append("max_attempts")
        if messages_last_7_days >= self.rules["max_messages_per_7_days"]: failed.append("max_messages_per_7_days")
        if total_actions >= self.rules["max_total_recovery_actions"]: failed.append("max_total_recovery_actions")
        if discount_percent > self.rules["max_discount_percent"]: failed.append("max_discount_percent")
        if model_confidence < self.rules["minimum_model_confidence"]: failed.append("minimum_model_confidence")
        if expected_incremental_recovery < self.rules["minimum_expected_incremental_recovery"]: failed.append("minimum_expected_incremental_recovery")
        stop_reasons = {"opt_out": opt_out and self.rules["stop_on_opt_out"], "success": success and self.rules["stop_on_success"], "dispute": dispute and self.rules["stop_on_dispute"], "fraud_signal": fraud_signal and self.rules["stop_on_fraud_signal"]}
        failed.extend(key for key, value in stop_reasons.items() if value)
        decision = "ESCALATE" if amount > self.rules["require_human_above_amount"] else "BLOCK" if failed else "ALLOW"
        if decision == "ESCALATE": failed.append("require_human_above_amount")
        audit = AuditLog(action="policy_check", actor="policy_guard", details={"policy_id": "default", "decision": decision, "rules_evaluated": list(self.rules), "rules_failed": failed, "reason": ";".join(failed), "timestamp": datetime.now(timezone.utc).isoformat(), "customer_id": str(customer_id), "action": action})
        self.session.add(audit); self.session.commit()
        return {"decision": decision, "policy_id": "default", "rules_evaluated": list(self.rules), "rules_failed": failed, "reason": ";".join(failed) or "all rules passed"}
