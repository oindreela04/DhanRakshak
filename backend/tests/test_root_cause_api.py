from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Customer


def test_root_cause_api_validates_customer_and_returns_analysis() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    customer_id = uuid4()
    with Session(engine) as session:
        session.add(Customer(id=customer_id, name="API root cause customer")); session.commit()

    def override_get_db():
        with Session(engine) as session: yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/root-cause/analyze", json={"customer_id": str(customer_id)})
        assert response.status_code == 200
        assert response.json()["root_cause"] == "unknown"
        assert response.json()["evidence"] == ["no qualifying stored customer events were found"]
    finally:
        app.dependency_overrides.clear()