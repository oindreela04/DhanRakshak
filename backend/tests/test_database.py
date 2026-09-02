from sqlalchemy import inspect

from app.db import Base, build_engine
from app import models  # noqa: F401


def test_database_initialization() -> None:
    engine = build_engine("sqlite://")
    Base.metadata.create_all(engine)
    table_names = set(inspect(engine).get_table_names())
    assert {"customers", "transactions", "recovery_actions", "audit_logs", "webhook_events"}.issubset(table_names)
