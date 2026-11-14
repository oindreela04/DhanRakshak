"""Build a compact, deployable SQLite demo database from the held-out test split.

The full synthetic dataset is ~400 MB, which is far too large for the in-memory
analytics services on a small cloud instance. This script samples a coherent
slice of customers (with *all* of their test-period activity), scores every
customer with the trained revenue-risk model, and writes:

  backend/dhanrakshak.db          - seeded SQLite database used by the live API
  models/demo_customer_profiles.csv - per-customer ML feature profile
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid5, NAMESPACE_URL

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.db import Base, build_engine  # noqa: E402
from app.ml.models import RevenueRiskModel  # noqa: E402
from app.models import (AuditLog, CheckoutSession, Customer, Experiment, Invoice,  # noqa: E402
                        PromiseToPay, RecoveryAction, RecoveryEvent, RecoveryOutcome,
                        RevenueRiskScore, Subscription, Transaction)
from sqlalchemy.orm import Session  # noqa: E402

PROFILE_COLUMNS = ["customer_id", "name", "language", "city", "segment", "lifetime_value", "avg_order_value", "preferred_payment_method", "preferred_channel", "historical_payment_success_rate", "historical_recovery_rate", "days_since_last_payment", "customer_tenure", "risk_segment"]


def ts(value: str | float | None) -> datetime | None:
    if value is None or (isinstance(value, float) and pd.isna(value)) or value == "": return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def build(data: Path, out_db: Path, profiles_out: Path, customers_n: int, seed: int) -> None:
    split = data / "test"
    events = pd.read_csv(split / "recovery_events.csv")
    events["ts"] = pd.to_datetime(events["timestamp"], utc=True)
    recent = events[events["ts"] >= events["ts"].max() - pd.Timedelta(days=75)]
    sample_ids = recent["customer_id"].drop_duplicates().sample(n=customers_n, random_state=seed)
    ids = set(sample_ids)

    customers = pd.read_csv(data / "raw" / "customers.csv")
    customers = customers[customers["customer_id"].isin(ids)]
    events = events[events["customer_id"].isin(ids)]
    transactions = pd.read_csv(split / "transactions.csv"); transactions = transactions[transactions["customer_id"].isin(ids)]
    invoices = pd.read_csv(split / "invoices.csv"); invoices = invoices[invoices["customer_id"].isin(ids)]
    subscriptions = pd.read_csv(split / "subscriptions.csv"); subscriptions = subscriptions[subscriptions["customer_id"].isin(ids)]
    checkouts = pd.read_csv(split / "checkout_sessions.csv"); checkouts = checkouts[checkouts["customer_id"].isin(ids)]

    # Score each customer with the trained risk model on their latest open exposure.
    risk_model = RevenueRiskModel.load(ROOT / "models" / "revenue_risk")
    latest = events.sort_values("ts").groupby("customer_id").tail(1).merge(customers, on="customer_id", how="left")
    feats = pd.DataFrame({
        "amount": latest["original_amount"], "customer_lifetime_value": latest["lifetime_value"],
        "historical_payment_success_rate": latest["historical_payment_success_rate"], "historical_recovery_rate": latest["historical_recovery_rate"],
        "retry_count": latest["event_id"].map(lambda v: int(v[-2:], 16) % 4), "days_overdue": latest["event_id"].map(lambda v: int(v[-4:-2], 16) % 61),
        "customer_tenure": latest["customer_tenure"], "previous_failed_attempts": (1 - latest["historical_payment_success_rate"]) * 8,
        "previous_recovery_actions": latest["historical_recovery_rate"] * 6, "days_since_last_payment": latest["days_since_last_payment"],
        "payment_method": latest["payment_method"], "failure_reason": "bank_declined", "subscription_status": "active", "checkout_stage": "payment_failed",
        "preferred_channel": latest["preferred_channel"], "time_of_day": latest["ts"].dt.hour.map(lambda h: "night" if h < 6 else "morning" if h < 12 else "afternoon" if h < 18 else "evening"),
        "day_of_week": latest["ts"].dt.day_name(), "segment": latest["segment"],
    })
    latest["risk_score"] = risk_model.predict_proba(feats)
    latest["open_amount"] = latest["original_amount"]

    profiles = customers[PROFILE_COLUMNS].merge(latest[["customer_id", "risk_score", "open_amount", "payment_method"]], on="customer_id", how="left")
    profiles_out.parent.mkdir(parents=True, exist_ok=True); profiles.to_csv(profiles_out, index=False)

    if out_db.exists(): out_db.unlink()
    engine = build_engine(f"sqlite:///{out_db}"); Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.bulk_insert_mappings(Customer, [{"id": UUID(r.customer_id), "external_id": r.customer_id, "name": r.name, "email": f"{r.name.lower().replace(' ', '.')}@demo.dhanrakshak.in", "language": r.language, "preferred_channel": r.preferred_channel, "preferred_payment_method": r.preferred_payment_method, "segment": r.segment} for r in customers.itertuples()])
        session.bulk_insert_mappings(Transaction, [{"id": UUID(r.transaction_id), "customer_id": UUID(r.customer_id), "amount": r.amount, "currency": "INR", "status": r.status, "failure_code": None if pd.isna(r.failure_reason) else r.failure_reason, "payment_method": r.payment_method, "occurred_at": ts(r.timestamp)} for r in transactions.itertuples()])
        session.bulk_insert_mappings(Invoice, [{"id": UUID(r.invoice_id), "customer_id": UUID(r.customer_id), "amount": r.amount, "status": r.status, "due_at": ts(r.due_date)} for r in invoices.itertuples()])
        session.bulk_insert_mappings(Subscription, [{"id": UUID(r.subscription_id), "customer_id": UUID(r.customer_id), "external_id": r.subscription_id, "status": r.status, "amount": r.amount, "created_at": ts(r.created_at)} for r in subscriptions.itertuples()])
        session.bulk_insert_mappings(CheckoutSession, [{"id": UUID(r.session_id), "customer_id": UUID(r.customer_id), "status": r.status, "amount": r.cart_value, "created_at": ts(r.started_at)} for r in checkouts.itertuples()])
        event_rows, action_rows, outcome_rows = [], [], []
        for r in events.drop(columns=["ts"]).itertuples(index=False):
            payload = {k: (None if pd.isna(v) else v) for k, v in r._asdict().items()}
            eid = UUID(r.recovery_id); event_rows.append({"id": eid, "customer_id": UUID(r.customer_id), "event_type": r.action, "payload": payload, "created_at": ts(r.timestamp)})
            if str(r.control_group).lower() != "true" and r.action != "no_action":
                aid = uuid5(NAMESPACE_URL, f"action:{r.recovery_id}"); recovered = str(r.eventually_recovered).lower() == "true"
                action_rows.append({"id": aid, "recovery_event_id": eid, "action_type": r.action, "status": "VERIFIED" if recovered else "EXECUTED", "rationale": r.message, "created_at": ts(r.timestamp)})
                outcome_rows.append({"id": uuid5(NAMESPACE_URL, f"outcome:{r.recovery_id}"), "recovery_action_id": aid, "recovered_amount": float(r.recovered_amount or 0), "status": "verified" if recovered else "unrecovered", "verified_at": ts(r.recovery_timestamp) if recovered else None})
        session.bulk_insert_mappings(RecoveryEvent, event_rows); session.bulk_insert_mappings(RecoveryAction, action_rows); session.bulk_insert_mappings(RecoveryOutcome, outcome_rows)
        session.bulk_insert_mappings(RevenueRiskScore, [{"customer_id": UUID(r.customer_id), "score": round(float(r.risk_score), 4), "amount_at_risk": r.open_amount} for r in latest.itertuples()])

        anchor = events["ts"].max().to_pydatetime(); languages = {"Hindi": "Hindi", "Hinglish": "Hinglish"}
        top = latest.sort_values("risk_score", ascending=False).head(24)
        for i, r in enumerate(top.itertuples()):
            status = ["scheduled", "kept", "missed", "scheduled"][i % 4]
            session.add(PromiseToPay(customer_id=UUID(r.customer_id), amount=Decimal(str(round(float(r.open_amount), 2))), promised_for=anchor + timedelta(days=(i % 9) - 3), status=status, language=languages.get(r.language, "English"), confidence=Decimal(str(round(0.72 + (i % 5) * 0.05, 2))), reminder_status="sent" if status != "scheduled" else "scheduled"))
        for i, r in enumerate(latest.sort_values("ts").tail(40).itertuples()):
            session.add(AuditLog(action=["risk_scored", "policy_check", "recovery_executed", "payment_verified"][i % 4], actor=["revenue_risk_model", "policy_guard", "recovery_agent", "verification_service"][i % 4], details={"customer_id": r.customer_id, "amount": float(r.open_amount), "risk_score": round(float(r.risk_score), 4), "action": r.action}, created_at=r.ts.to_pydatetime()))
        for name, cfg, active in [("whatsapp_vs_sms_upi", {"arms": ["whatsapp", "sms"], "traffic_split": [0.5, 0.5], "metric": "incremental_recovery"}, True), ("delayed_retry_window_6h", {"arms": ["retry", "delayed_retry"], "delay_hours": 6}, True), ("human_escalation_above_1L", {"threshold": 100000, "arms": ["payment_link", "human_escalation"]}, False)]:
            session.add(Experiment(name=name, configuration=cfg, active=active))
        session.commit()
    print(f"customers={len(customers)} transactions={len(transactions)} events={len(events)} invoices={len(invoices)} subscriptions={len(subscriptions)} checkouts={len(checkouts)} db={out_db.stat().st_size / 1e6:.1f}MB")


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--data-root", default=str(ROOT / "data")); parser.add_argument("--db", default=str(ROOT / "backend" / "dhanrakshak.db")); parser.add_argument("--profiles", default=str(ROOT / "models" / "demo_customer_profiles.csv")); parser.add_argument("--customers", type=int, default=600); parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args(); build(Path(args.data_root), Path(args.db), Path(args.profiles), args.customers, args.seed)


if __name__ == "__main__": main()
