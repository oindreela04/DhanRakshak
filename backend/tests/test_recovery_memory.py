from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Customer, RecoveryAction, RecoveryEvent, RecoveryOutcome, Transaction
from app.services.recovery_memory import RecoveryMemoryService


def test_recovery_dna_builds_from_verified_customer_facts() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    customer_id = uuid4()
    with Session(engine) as session:
        session.add(Customer(id=customer_id, name="Asha", language="Hindi", preferred_channel="whatsapp", preferred_payment_method="upi"))
        session.add_all([
            Transaction(customer_id=customer_id, amount=Decimal("100"), status="success", payment_method="upi", occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
            Transaction(customer_id=customer_id, amount=Decimal("100"), status="failed", payment_method="credit_card", occurred_at=datetime(2026, 1, 2, tzinfo=timezone.utc)),
        ])
        event = RecoveryEvent(customer_id=customer_id, event_type="payment_link", payload={"action": "payment_link", "channel": "whatsapp", "original_amount": "100.00", "timestamp": "2026-01-02T10:00:00+00:00", "retry_count": 1})
        session.add(event); session.flush()
        action = RecoveryAction(recovery_event_id=event.id, action_type="payment_link", status="completed")
        session.add(action); session.flush()
        outcome = RecoveryOutcome(recovery_action_id=action.id, status="verified", recovered_amount=Decimal("100"), verified_at=datetime(2026, 1, 2, 12, tzinfo=timezone.utc))
        session.add(outcome); session.commit()
        dna = RecoveryMemoryService(session).calculate_recovery_dna(customer_id)
        assert dna["preferred_payment_method"] == "upi"
        assert dna["payment_method_success_by_method"]["upi"] == 1.0
        assert dna["payment_success"] == dna["payment_method_success_by_method"]
        assert dna["recovery_success_by_action"]["payment_link"] == 1.0
        assert dna["recovery_success"] == dna["recovery_success_by_action"]
        assert dna["lifetime_recovered_amount"] == 100.0
        assert dna["average_recovery_time"] == 2.0
        assert dna["recovery_fatigue"] == "LOW"


def test_update_after_recovery_persists_current_snapshot() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    customer_id = uuid4()
    with Session(engine) as session:
        session.add(Customer(id=customer_id, name="Ravi"))
        event = RecoveryEvent(customer_id=customer_id, event_type="retry", payload={"action": "retry", "channel": "email", "original_amount": "50", "timestamp": "2026-01-02T10:00:00+00:00"})
        session.add(event); session.flush()
        action = RecoveryAction(recovery_event_id=event.id, action_type="retry", status="completed")
        session.add(action); session.flush()
        outcome = RecoveryOutcome(recovery_action_id=action.id, status="verified", recovered_amount=Decimal("50"), verified_at=datetime(2026, 1, 2, 11, tzinfo=timezone.utc))
        session.add(outcome); session.commit()
        snapshot = RecoveryMemoryService(session).update_after_recovery(outcome.id)
        assert snapshot["lifetime_recovered_amount"] == 50.0
        stored = RecoveryMemoryService(session).get_customer_memory(customer_id)
        assert stored.memory == snapshot