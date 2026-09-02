from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import CheckoutSession, Customer, Invoice, PromiseToPay, Subscription, Transaction
from app.services.revenue_leakage_radar import RevenueLeakageRadar


def test_radar_uses_current_vs_prior_rolling_behavior() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    customer_id = uuid4(); anchor = datetime(2026, 3, 1, tzinfo=timezone.utc)
    with Session(engine) as session:
        session.add(Customer(id=customer_id, name="Radar customer", segment="SMB"))
        session.add(Transaction(customer_id=customer_id, amount=Decimal("100"), status="success", payment_method="upi", occurred_at=anchor - timedelta(days=45)))
        session.add(Transaction(customer_id=customer_id, amount=Decimal("900"), status="failed", payment_method="upi", occurred_at=anchor - timedelta(days=2)))
        session.add(CheckoutSession(customer_id=customer_id, amount=Decimal("400"), status="abandoned", created_at=anchor - timedelta(days=2)))
        session.add(Subscription(customer_id=customer_id, amount=Decimal("300"), status="past_due", created_at=anchor - timedelta(days=2)))
        session.add(Invoice(customer_id=customer_id, amount=Decimal("250"), status="overdue", due_at=anchor - timedelta(days=10), created_at=anchor - timedelta(days=40)))
        session.add(PromiseToPay(customer_id=customer_id, amount=Decimal("180"), promised_for=anchor - timedelta(days=1), status="missed"))
        session.commit()
        result = RevenueLeakageRadar(session).calculate_radar()
        reasons = {item["reason"] for item in result["top_risk_events"]}
        assert result["total_revenue_at_risk"] > 0
        assert "payment_degradation" in reasons
        assert "checkout_abandonment" in reasons
        assert "subscription_deterioration" in reasons
        assert "invoice_ageing" in reasons
        assert "missed_promise_to_pay" in reasons
        assert result["risk_trend"]["direction"] == "worsening"


def test_empty_radar_has_no_fabricated_exposure() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        result = RevenueLeakageRadar(session).calculate_radar()
        assert result["total_revenue_at_risk"] == 0
        assert result["top_risk_events"] == []