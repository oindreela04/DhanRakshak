import logging
import hashlib
import json
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from app.db import init_db
from app.ml.models import ActionRecoveryModel, IncrementalityModel, RevenueRiskModel
from app.services.recovery_memory import RecoveryMemoryService
from app.services.revenue_leakage_radar import RevenueLeakageRadar
from app.services.root_cause_engine import RootCauseEngine
from app.db import get_db
from uuid import UUID
from fastapi import Depends
from sqlalchemy.orm import Session
from sqlalchemy import delete, func, select
from app.config import get_settings
from app.models import (AuditLog, Customer, Experiment, Invoice, PromiseToPay,
                        RecoveryAction, RecoveryEvent, RecoveryOutcome,
                        Transaction, WebhookEvent)
from app.schemas import (ActionRequest, CustomerListResponse, CustomerResponse,
                         EventRequest, EventResponse, ExperimentRequest,
                         GenericResponse, PolicyRequest, PromiseRequest,
                         PromiseResponse, RecoveryRequest, RecoveryTwinResponse,
                         StopRequest, WebhookResponse)
from app.adapters.razorpay import RazorpayAdapter
from app.services.promise_parser import parse_promise
from app.services.policy_guard import PolicyGuard
from app.services.recovery_agent import RecoveryAgent
from app.services.recovery_economics import RecoveryEconomicsService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    logger.info("Database initialized")
    yield


app = FastAPI(title="DhanRakshak API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "dhanrakshak-api"}


MODEL_ROOT = Path(__file__).resolve().parents[2] / "models"


class PredictionRequest(BaseModel):
    features: dict[str, Any] = Field(default_factory=dict)


class ActionProbabilityRequest(PredictionRequest):
    actions: list[str] = Field(default_factory=lambda: ["retry", "payment_link", "whatsapp", "email", "sms", "delayed_retry", "promise_to_pay", "human_escalation", "no_action"])

    @field_validator("actions")
    @classmethod
    def validate_actions(cls, values: list[str]) -> list[str]:
        allowed = {"retry", "payment_link", "whatsapp", "email", "sms", "delayed_retry", "promise_to_pay", "human_escalation", "no_action"}
        if not values or any(action not in allowed for action in values): raise ValueError("actions contains an unsupported value")
        return values


class IncrementalityRequest(PredictionRequest):
    amount: float = Field(ge=0)


@lru_cache
def load_model(model_name: str):
    try:
        model_type = {"revenue_risk": RevenueRiskModel, "action_recovery": ActionRecoveryModel, "incrementality": IncrementalityModel}[model_name]
        return model_type.load(MODEL_ROOT / model_name)
    except FileNotFoundError as error:
        raise HTTPException(status_code=503, detail="MODEL_NOT_TRAINED") from error


@app.post("/api/v1/ml/risk")
async def predict_risk(request: PredictionRequest) -> dict[str, Any]:
    model = load_model("revenue_risk")
    return {"model_version": model.metadata["model_version"], "probability_unrecovered": model.predict_proba(request.features)[0]}


@app.post("/api/v1/ml/action-probabilities")
async def predict_actions(request: ActionProbabilityRequest) -> dict[str, Any]:
    model = load_model("action_recovery")
    records = [{**request.features, "action": action} for action in request.actions]
    probabilities = model.predict_proba(records)
    return {"model_version": model.metadata["model_version"], "probabilities": dict(zip(request.actions, probabilities))}


@app.post("/api/v1/ml/incrementality")
async def predict_incrementality(request: IncrementalityRequest) -> dict[str, Any]:
    model = load_model("incrementality")
    organic = model.predict_proba(request.features)[0]
    return {"model_version": model.metadata["model_version"], "organic_recovery_probability": organic, "estimated_organic_revenue": request.amount * organic}


@app.get("/api/v1/models/performance")
async def model_performance() -> dict[str, Any]:
    performance = {}
    for name in ["revenue_risk", "action_recovery", "incrementality"]:
        model = load_model(name)
        performance[name] = {"model_version": model.metadata["model_version"], "metrics": model.metrics, "metadata": model.metadata}
    return performance


@app.get("/api/v1/customers/{customer_id}/recovery-dna")
async def recovery_dna(customer_id: UUID, session: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return RecoveryMemoryService(session).get_customer_memory(customer_id).memory or {}
    except ValueError as error:
        raise HTTPException(status_code=404, detail="CUSTOMER_NOT_FOUND") from error


@app.get("/api/v1/revenue-at-risk")
async def revenue_at_risk(session: Session = Depends(get_db)) -> dict[str, Any]:
    return RevenueLeakageRadar(session).calculate_radar()


class RootCauseRequest(BaseModel):
    customer_id: UUID
    transaction_id: UUID | None = None


@app.post("/api/v1/root-cause/analyze")
async def analyze_root_cause(request: RootCauseRequest, session: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return RootCauseEngine(session).analyze(request.customer_id, request.transaction_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail="CUSTOMER_NOT_FOUND") from error


@app.post("/api/v1/events", response_model=EventResponse)
async def create_event(request: EventRequest, session: Session = Depends(get_db)) -> EventResponse:
    event = RecoveryEvent(customer_id=request.customer_id, event_type=request.event_type, payload=request.payload)
    session.add(event); session.commit(); session.refresh(event)
    return EventResponse(id=event.id, event_type=event.event_type, customer_id=event.customer_id, accepted=True)


@app.post("/api/v1/webhooks/razorpay", response_model=WebhookResponse)
async def razorpay_webhook(request: Request, session: Session = Depends(get_db)) -> WebhookResponse:
    body = await request.body(); settings = get_settings(); signature = request.headers.get("X-Razorpay-Signature", "")
    adapter = RazorpayAdapter(webhook_secret=settings.razorpay_webhook_secret)
    if not adapter.verify_signature(body, signature, settings.razorpay_webhook_secret): raise HTTPException(status_code=401, detail="INVALID_WEBHOOK_SIGNATURE")
    event_key = request.headers.get("X-Razorpay-Event-Id") or hashlib.sha256(body).hexdigest()
    existing = session.scalar(select(WebhookEvent).where(WebhookEvent.external_id == event_key))
    if existing: return WebhookResponse(event_id=existing.id, duplicate=True, accepted=True)
    normalized = adapter.normalize_webhook(body); event = WebhookEvent(provider="razorpay", external_id=event_key, event_type=normalized["event_type"], payload=normalized["payload"], processed=False); session.add(event); session.commit(); session.refresh(event)
    return WebhookResponse(event_id=event.id, accepted=True)


@app.get("/api/v1/revenue-recovered")
async def revenue_recovered(session: Session = Depends(get_db)) -> dict[str, Any]:
    outcomes = list(session.scalars(select(RecoveryOutcome).where(RecoveryOutcome.status.in_(["verified", "success", "recovered"]))))
    return {"total_recovered": round(sum(float(outcome.recovered_amount or 0) for outcome in outcomes), 2), "verified_outcomes": len(outcomes)}


@app.get("/api/v1/customers", response_model=CustomerListResponse)
async def customers(limit: int = 100, offset: int = 0, session: Session = Depends(get_db)) -> CustomerListResponse:
    limit = min(max(limit, 1), 500); rows = list(session.scalars(select(Customer).order_by(Customer.created_at).offset(offset).limit(limit))); total = session.scalar(select(func.count()).select_from(Customer)) or 0
    return CustomerListResponse(items=[CustomerResponse(id=row.id, external_id=row.external_id, name=row.name, email=row.email, segment=row.segment) for row in rows], total=total)


@app.get("/api/v1/customers/{customer_id}", response_model=CustomerResponse)
async def customer(customer_id: UUID, session: Session = Depends(get_db)) -> CustomerResponse:
    row = session.get(Customer, customer_id)
    if row is None: raise HTTPException(status_code=404, detail="CUSTOMER_NOT_FOUND")
    return CustomerResponse(id=row.id, external_id=row.external_id, name=row.name, email=row.email, segment=row.segment)


@app.post("/api/v1/recovery/simulate")
async def simulate_recovery(request: RecoveryRequest, session: Session = Depends(get_db)) -> dict[str, Any]:
    if session.get(Customer, request.customer_id) is None: raise HTTPException(status_code=404, detail="CUSTOMER_NOT_FOUND")
    return {"customer_id": str(request.customer_id), "actions": RecoveryAgent(session).predict_action_recovery(request.customer_id, request.amount, request.payment_method)}


@app.post("/api/v1/recovery/decide")
async def decide_recovery(request: RecoveryRequest, session: Session = Depends(get_db)) -> dict[str, Any]:
    try: return RecoveryAgent(session).decide(request.customer_id, request.amount, request.payment_method)
    except ValueError as error: raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/v1/recovery/execute")
async def execute_recovery(request: ActionRequest, session: Session = Depends(get_db)) -> dict[str, Any]:
    try: return RecoveryAgent(session).execute(request.customer_id, request.amount, request.action, request.payment_method)
    except ValueError as error: raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/v1/recovery/stop")
async def stop_recovery(request: StopRequest, session: Session = Depends(get_db)) -> dict[str, Any]: return RecoveryAgent(session).stop(request.customer_id, request.reason)


@app.post("/api/v1/promises-to-pay", response_model=PromiseResponse)
async def create_promise(request: PromiseRequest, session: Session = Depends(get_db)) -> PromiseResponse:
    if session.get(Customer, request.customer_id) is None: raise HTTPException(status_code=404, detail="CUSTOMER_NOT_FOUND")
    parsed = parse_promise(request.text, request.amount); promise = PromiseToPay(customer_id=request.customer_id, amount=parsed["amount"], promised_for=parsed["promised_for"], status="scheduled", language=parsed["language"], confidence=parsed["confidence"], reminder_status="scheduled"); session.add(promise); session.commit(); session.refresh(promise)
    return PromiseResponse(id=promise.id, customer_id=promise.customer_id, amount=float(promise.amount), promised_for=promise.promised_for, language=promise.language or "English", confidence=float(promise.confidence or 0), status=promise.status)


@app.get("/api/v1/promises-to-pay")
async def promises_to_pay(customer_id: UUID | None = None, session: Session = Depends(get_db)) -> dict[str, Any]:
    query = select(PromiseToPay).order_by(PromiseToPay.promised_for)
    if customer_id: query = query.where(PromiseToPay.customer_id == customer_id)
    return {"items": [{"id": str(row.id), "customer_id": str(row.customer_id), "amount": float(row.amount), "promised_for": row.promised_for, "language": row.language, "confidence": float(row.confidence or 0), "status": row.status, "reminder_status": row.reminder_status} for row in session.scalars(query)]}


@app.get("/api/v1/audit")
async def audit(limit: int = 100, session: Session = Depends(get_db)) -> dict[str, Any]:
    rows = list(session.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(max(limit, 1), 500))))
    return {"items": [{"id": str(row.id), "action": row.action, "actor": row.actor, "details": row.details, "created_at": row.created_at} for row in rows]}


@app.get("/api/v1/experiments")
async def experiments(session: Session = Depends(get_db)) -> dict[str, Any]:
    return {"items": [{"id": str(row.id), "name": row.name, "configuration": row.configuration, "active": row.active} for row in session.scalars(select(Experiment).order_by(Experiment.created_at.desc()))]}


@app.post("/api/v1/experiments")
async def create_experiment(request: ExperimentRequest, session: Session = Depends(get_db)) -> dict[str, Any]:
    if session.scalar(select(Experiment).where(Experiment.name == request.name)): raise HTTPException(status_code=409, detail="EXPERIMENT_EXISTS")
    row = Experiment(name=request.name, configuration=request.configuration, active=request.active); session.add(row); session.commit(); session.refresh(row)
    return {"id": str(row.id), "name": row.name, "configuration": row.configuration, "active": row.active}


@app.post("/api/v1/policy/check")
async def policy_check(request: PolicyRequest, session: Session = Depends(get_db)) -> dict[str, Any]:
    return PolicyGuard(session).check(request.customer_id, request.amount, request.action, request.model_confidence, request.attempts, request.messages_last_7_days, request.total_actions, request.discount_percent, request.expected_incremental_recovery)


@app.post("/api/v1/recovery-twin/simulate", response_model=RecoveryTwinResponse)
async def recovery_twin(session: Session = Depends(get_db)) -> RecoveryTwinResponse:
    events = list(session.scalars(select(RecoveryEvent)))
    rows = [event.payload or {} for event in events if "original_amount" in (event.payload or {})]
    control = [row for row in rows if str(row.get("control_group", "")).lower() == "true"]; treatment = [row for row in rows if str(row.get("control_group", "")).lower() != "true"]
    organic = sum(float(row.get("original_amount", 0)) * float(row.get("organic_recovery_probability", 0)) for row in treatment); assisted = sum(float(row.get("amount_recovered", 0)) for row in treatment); baseline = sum(float(row.get("original_amount", 0)) for row in rows); control_rate = sum(str(row.get("eventually_recovered", "")).lower() == "true" for row in control) / len(control) if control else 0; treatment_rate = sum(str(row.get("eventually_recovered", "")).lower() == "true" for row in treatment) / len(treatment) if treatment else 0
    return RecoveryTwinResponse(baseline_at_risk=baseline, organic_recovery=organic, assisted_recovery=assisted, incremental_recovery=assisted - organic, recovery_rate_without_dhanrakshak=control_rate, recovery_rate_with_dhanrakshak=treatment_rate, confidence=min(1, len(rows) / 1000), sample_size=len(rows))


DEMO_STATE: dict[str, Any] = {"status": "not_started", "results": []}


@app.post("/api/v1/demo/reset")
async def demo_reset(session: Session = Depends(get_db)) -> GenericResponse:
    for model in [RecoveryOutcome, RecoveryAction, RecoveryEvent, Transaction, PromiseToPay, Customer]: session.execute(delete(model))
    session.commit(); DEMO_STATE.update(status="reset", results=[])
    return GenericResponse(status="ok", data={"label": "Deterministic Benchmark Demo - fictional merchant data"})


@app.post("/api/v1/demo/run")
async def demo_run(session: Session = Depends(get_db)) -> GenericResponse:
    if DEMO_STATE["status"] not in {"reset", "not_started", "completed"}: return GenericResponse(status=DEMO_STATE["status"], data=DEMO_STATE)
    customer = Customer(external_id="demo-high-value", name="Demo Customer", segment="high_value", language="Hinglish", preferred_channel="whatsapp", preferred_payment_method="upi"); session.add(customer); session.flush()
    event = RecoveryEvent(customer_id=customer.id, event_type="invoice_overdue", payload={"action": "payment_link", "channel": "whatsapp", "original_amount": "240000", "demo": True}); session.add(event); session.flush(); action = RecoveryAction(recovery_event_id=event.id, action_type="payment_link", status="EXECUTED", rationale="deterministic demo case"); session.add(action); session.commit()
    DEMO_STATE.update(status="completed", results=[{"case": "overdue_invoice", "customer_id": str(customer.id), "state": "VERIFICATION_PENDING"}]); return GenericResponse(status="completed", data=DEMO_STATE)


@app.get("/api/v1/demo/status")
async def demo_status() -> GenericResponse: return GenericResponse(status=DEMO_STATE["status"], data=DEMO_STATE)
