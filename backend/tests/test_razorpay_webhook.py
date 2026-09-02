import hashlib
import hmac
import json
import os
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.db import Base, get_db
from app.main import app
from app.models import WebhookEvent


def test_webhook_signature_and_duplicate_protection() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    os.environ["RAZORPAY_WEBHOOK_SECRET"] = "test-secret"
    get_settings.cache_clear()
    body = json.dumps({"event": "payment.failed", "payload": {"payment": {"entity": {"id": "pay_test"}}}}).encode()
    signature = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()

    def override_get_db():
        with Session(engine) as session: yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            headers = {"X-Razorpay-Signature": signature, "X-Razorpay-Event-Id": str(uuid4())}
            first = client.post("/api/v1/webhooks/razorpay", content=body, headers=headers)
            second = client.post("/api/v1/webhooks/razorpay", content=body, headers=headers)
            invalid = client.post("/api/v1/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": "bad"})
        assert first.status_code == 200 and first.json()["accepted"] is True
        assert second.status_code == 200 and second.json()["duplicate"] is True
        assert invalid.status_code == 401
    finally:
        app.dependency_overrides.clear()
        os.environ.pop("RAZORPAY_WEBHOOK_SECRET", None)
        get_settings.cache_clear()