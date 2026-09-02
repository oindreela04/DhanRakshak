from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Customer


def test_recovery_dna_api_returns_customer_snapshot() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    customer_id = uuid4()
    with Session(engine) as session:
        session.add(Customer(id=customer_id, name="API customer")); session.commit()

    def override_get_db():
        with Session(engine) as session: yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/customers/{customer_id}/recovery-dna")
        assert response.status_code == 200
        assert response.json()["customer_id"] == str(customer_id)
        assert "payment_success" in response.json()
        assert "recovery_success" in response.json()
        assert response.json()["recovery_fatigue"] == "LOW"
    finally:
        app.dependency_overrides.clear()