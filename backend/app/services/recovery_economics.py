from __future__ import annotations

from typing import Any
from uuid import UUID

from app.services.recovery_memory import RecoveryMemoryService

ACTIONS = ("retry", "payment_link", "whatsapp", "email", "sms", "delayed_retry", "promise_to_pay", "human_escalation", "no_action")
COSTS = {"retry": (0, .20), "payment_link": (2, .12), "whatsapp": (1, .10), "email": (.2, .05), "sms": (1.5, .08), "delayed_retry": (0, .10), "promise_to_pay": (1, .15), "human_escalation": (25, .25), "no_action": (0, 0)}


class RecoveryEconomicsService:
    def __init__(self, session): self.session = session

    def simulate(self, customer_id: UUID, amount: float, action: str, payment_method: str = "upi") -> dict[str, Any]:
        if action not in ACTIONS: raise ValueError("invalid_action")
        memory = RecoveryMemoryService(self.session).get_customer_memory(customer_id).memory or {}
        base = float(memory.get("recovery_success", {}).get(action, 0) or 0)
        method = float(memory.get("payment_success", {}).get(payment_method, 0) or 0)
        fatigue = float(memory.get("recovery_fatigue_score", 0) or 0)
        probability = max(0.01, min(.99, base * .65 + method * .25 + (1 - fatigue) * .10))
        organic = max(0, min(1, float(memory.get("recovery_confidence", 0) or 0)))
        cost, friction = COSTS[action]; expected = amount * probability; incremental = expected * max(0, 1 - organic); penalty = amount * fatigue * .02
        return {"action": action, "recovery_probability": round(probability, 4), "expected_recovered_amount": round(expected, 2), "intervention_cost": cost, "customer_friction_cost": round(amount * friction / 100, 2), "risk_penalty": round(penalty, 2), "expected_incremental_recovery_value": round(incremental - cost - amount * friction / 100 - penalty, 2)}

    def rank_actions(self, customer_id: UUID, amount: float, payment_method: str) -> list[dict[str, Any]]:
        return sorted((self.simulate(customer_id, amount, action, payment_method) for action in ACTIONS), key=lambda item: item["expected_incremental_recovery_value"], reverse=True)
