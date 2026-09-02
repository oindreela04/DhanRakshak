from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Customer, Transaction
from app.services.root_cause_engine import RootCauseEngine


def test_root_cause_uses_customer_history_and_actual_evidence() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    customer_id = uuid4()
    with Session(engine) as session:
        session.add(Customer(id=customer_id, name="Root cause customer", segment="consumer", preferred_payment_method="upi", preferred_channel="whatsapp"))
        session.add(Transaction(customer_id=customer_id, amount=Decimal("100"), status="success", payment_method="upi", occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
        session.add_all([Transaction(customer_id=customer_id, amount=Decimal("100"), status="failed", payment_method="credit_card", failure_code="bank_declined", occurred_at=datetime(2026, 1, 2, tzinfo=timezone.utc)), Transaction(customer_id=customer_id, amount=Decimal("100"), status="failed", payment_method="credit_card", failure_code="bank_declined", occurred_at=datetime(2026, 1, 3, tzinfo=timezone.utc))])
        session.commit()
        result = RootCauseEngine(session).analyze(customer_id)
        assert result["root_cause"] == "payment_method_mismatch"
        assert result["recommended_intervention"] == "payment_link"
        assert any("credit_card" in item for item in result["evidence"])
        assert any("historical upi success rate" in item for item in result["evidence"])
