from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import AuditLog, Customer
from app.services.policy_guard import PolicyGuard
from app.services.promise_parser import parse_promise
from app.services.recovery_economics import RecoveryEconomicsService


def test_economics_ranks_real_memory_actions() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    customer_id = uuid4()
    with Session(engine) as session:
        session.add(Customer(id=customer_id, name="Economics customer")); session.commit()
        actions = RecoveryEconomicsService(session).rank_actions(customer_id, 5000, "upi")
        assert len(actions) == 9
        assert actions[0]["expected_incremental_recovery_value"] >= actions[-1]["expected_incremental_recovery_value"]


def test_policy_guard_creates_audit_and_blocks_failed_rule() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    customer_id = uuid4()
    with Session(engine) as session:
        result = PolicyGuard(session).check(customer_id, 500, "sms", .4, messages_last_7_days=2)
        assert result["decision"] == "BLOCK"
        assert "minimum_model_confidence" in result["rules_failed"]
        assert session.scalar(select(AuditLog).where(AuditLog.action == "policy_check")) is not None


def test_promise_parser_extracts_hinglish_amount_and_day() -> None:
    parsed = parse_promise("Monday ko ₹50,000 clear kar dunga")
    assert parsed["amount"] == 50000
    assert parsed["language"] == "Hindi"
    assert parsed["confidence"] >= .9