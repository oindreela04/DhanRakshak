"""Live inference endpoints that combine all three trained models."""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.ml.models import ActionRecoveryModel, IncrementalityModel, RevenueRiskModel
from app.services.recovery_economics import COSTS

MODEL_ROOT = Path(__file__).resolve().parents[2] / "models"
ACTIONS = ["retry", "payment_link", "whatsapp", "email", "sms", "delayed_retry", "promise_to_pay", "human_escalation", "no_action"]
router = APIRouter(prefix="/api/v1/ml", tags=["ml"])


@lru_cache
def _models() -> tuple[RevenueRiskModel, ActionRecoveryModel, IncrementalityModel]:
    try:
        return (RevenueRiskModel.load(MODEL_ROOT / "revenue_risk"), ActionRecoveryModel.load(MODEL_ROOT / "action_recovery"), IncrementalityModel.load(MODEL_ROOT / "incrementality"))
    except FileNotFoundError as error:
        raise HTTPException(status_code=503, detail="MODEL_NOT_TRAINED") from error


@lru_cache
def _profiles() -> pd.DataFrame:
    path = MODEL_ROOT / "demo_customer_profiles.csv"
    return pd.read_csv(path).set_index("customer_id") if path.exists() else pd.DataFrame()


def _time_of_day(hour: int) -> str:
    return "night" if hour < 6 else "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"


class ScenarioRequest(BaseModel):
    amount: float = Field(default=12000, gt=0, le=10_000_000)
    customer_lifetime_value: float = Field(default=45000, ge=0)
    historical_payment_success_rate: float = Field(default=0.72, ge=0, le=1)
    historical_recovery_rate: float = Field(default=0.35, ge=0, le=1)
    retry_count: int = Field(default=1, ge=0, le=10)
    days_overdue: int = Field(default=7, ge=0, le=365)
    customer_tenure: int = Field(default=420, ge=0)
    days_since_last_payment: int = Field(default=20, ge=0)
    payment_method: str = "upi"
    failure_reason: str = "bank_declined"
    preferred_channel: str = "whatsapp"
    segment: str = "consumer"
    hour: int = Field(default=datetime.now(timezone.utc).hour, ge=0, le=23)


def _features(req: ScenarioRequest) -> dict[str, Any]:
    return {
        "amount": req.amount, "customer_lifetime_value": req.customer_lifetime_value,
        "historical_payment_success_rate": req.historical_payment_success_rate, "historical_recovery_rate": req.historical_recovery_rate,
        "retry_count": req.retry_count, "days_overdue": req.days_overdue, "customer_tenure": req.customer_tenure,
        "previous_failed_attempts": (1 - req.historical_payment_success_rate) * 8, "previous_recovery_actions": req.historical_recovery_rate * 6,
        "days_since_last_payment": req.days_since_last_payment, "payment_method": req.payment_method, "failure_reason": req.failure_reason,
        "subscription_status": "past_due" if req.days_overdue > 0 else "active", "checkout_stage": "payment_failed",
        "preferred_channel": req.preferred_channel, "time_of_day": _time_of_day(req.hour),
        "day_of_week": datetime.now(timezone.utc).strftime("%A"), "segment": req.segment,
    }


def score(req: ScenarioRequest) -> dict[str, Any]:
    risk_model, action_model, incr_model = _models()
    features = _features(req)
    risk = risk_model.predict_proba(features)[0]
    organic = incr_model.predict_proba(features)[0]
    probabilities = action_model.predict_proba([{**features, "action": action} for action in ACTIONS])
    # Uplift is measured against the same model's do-nothing counterfactual so the
    # comparison is internally consistent; the control-trained incrementality model
    # is reported alongside as an independent organic-recovery estimate.
    baseline = probabilities[ACTIONS.index("no_action")]
    ranked = []
    for action, probability in zip(ACTIONS, probabilities):
        cost, friction = COSTS[action]
        uplift = max(0.0, probability - baseline) if action != "no_action" else 0.0
        incremental = req.amount * uplift - cost - req.amount * friction / 100
        ranked.append({"action": action, "recovery_probability": round(probability, 4), "uplift_vs_organic": round(uplift, 4), "expected_recovered_amount": round(req.amount * probability, 2), "intervention_cost": cost, "friction_cost": round(req.amount * friction / 100, 2), "expected_incremental_value": round(incremental, 2)})
    ranked.sort(key=lambda item: item["expected_incremental_value"], reverse=True)
    best = ranked[0]
    policy = "ESCALATE" if req.amount > 100000 else "BLOCK" if best["expected_incremental_value"] < 100 or req.retry_count >= 3 else "ALLOW"
    tier = "high" if risk >= 0.6 else "medium" if risk >= 0.45 else "low"
    return {
        "risk": {"probability_unrecovered": round(risk, 4), "tier": tier, "model_version": risk_model.metadata["model_version"]},
        "organic_recovery_probability": round(organic, 4), "do_nothing_probability": round(baseline, 4), "estimated_organic_revenue": round(req.amount * organic, 2),
        "actions": ranked, "recommended_action": best["action"], "policy_decision": policy,
        "explanation": f"{risk:.0%} chance this ₹{req.amount:,.0f} stays unrecovered. Doing nothing recovers {baseline:.0%} (control-group model: {organic:.0%}); {best['action'].replace('_', ' ')} lifts recovery to {best['recovery_probability']:.0%} for ₹{best['expected_incremental_value']:,.0f} expected incremental value.",
        "features": features,
    }


@router.post("/score")
async def score_scenario(request: ScenarioRequest) -> dict[str, Any]:
    return score(request)


@router.get("/customers")
async def scored_customers(limit: int = 60) -> dict[str, Any]:
    frame = _profiles()
    if frame.empty: return {"items": [], "total": 0}
    top = frame.sort_values("risk_score", ascending=False).head(min(max(limit, 1), 300)).reset_index()
    cols = ["customer_id", "name", "city", "segment", "language", "lifetime_value", "preferred_payment_method", "preferred_channel", "historical_payment_success_rate", "historical_recovery_rate", "risk_score", "open_amount", "risk_segment"]
    return {"items": top[cols].round(4).to_dict(orient="records"), "total": int(len(frame))}


@router.get("/customers/{customer_id}")
async def score_customer(customer_id: str) -> dict[str, Any]:
    frame = _profiles()
    if customer_id not in frame.index: raise HTTPException(status_code=404, detail="CUSTOMER_NOT_FOUND")
    row = frame.loc[customer_id]
    req = ScenarioRequest(amount=float(row["open_amount"]), customer_lifetime_value=float(row["lifetime_value"]), historical_payment_success_rate=float(row["historical_payment_success_rate"]), historical_recovery_rate=float(row["historical_recovery_rate"]), customer_tenure=int(row["customer_tenure"]), days_since_last_payment=int(row["days_since_last_payment"]), payment_method=str(row["payment_method"]), preferred_channel=str(row["preferred_channel"]), segment=str(row["segment"]))
    return {"customer": {"customer_id": customer_id, **{k: (v.item() if hasattr(v, "item") else v) for k, v in row.items()}}, **score(req)}


@router.get("/summary")
async def model_summary() -> dict[str, Any]:
    risk_model, action_model, incr_model = _models()
    per_action = action_model.metrics.get("per_action", {})
    return {
        "revenue_risk": {"version": risk_model.metadata["model_version"], "trained_at": risk_model.metadata["training_timestamp"], "training_rows": risk_model.metadata["training_rows"], "test_rows": risk_model.metadata["test_rows"], "validation": {k: v for k, v in risk_model.metrics.items() if k != "test"}, "test": risk_model.metrics.get("test", {})},
        "action_recovery": {"version": action_model.metadata["model_version"], "trained_at": action_model.metadata["training_timestamp"], "training_rows": action_model.metadata["training_rows"], "per_action_auc": {k: round(v["roc_auc"], 4) for k, v in per_action.items()}},
        "incrementality": {"version": incr_model.metadata["model_version"], "trained_at": incr_model.metadata["training_timestamp"], "training_rows": incr_model.metadata["training_rows"], **incr_model.metrics},
        "dataset_version": risk_model.metadata["dataset_version"],
    }
