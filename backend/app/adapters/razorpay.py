import hashlib
import hmac
import json
from decimal import Decimal
from typing import Any

import httpx

from app.adapters.base import PaymentAdapter, PaymentResult


class RazorpayAdapter(PaymentAdapter):
    """TEST-mode provider boundary with signature verification and no secret logging."""

    def __init__(self, key_id: str = "", key_secret: str = "", webhook_secret: str = "", test_mode: bool = True):
        self.key_id, self.key_secret, self.webhook_secret, self.test_mode = key_id, key_secret, webhook_secret, test_mode

    @staticmethod
    def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
        if not secret or not signature: return False
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def normalize_webhook(self, payload: bytes) -> dict[str, Any]:
        try: data = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError("invalid_webhook_json") from error
        event_type = data.get("event")
        if not event_type: raise ValueError("webhook_event_missing")
        return {"event_type": event_type, "payload": data}

    async def verify_payment(self, external_id: str) -> PaymentResult:
        if not self.test_mode: raise NotImplementedError("live Razorpay mode is disabled")
        if not self.key_id or not self.key_secret: raise ValueError("RAZORPAY_TEST_CREDENTIALS_NOT_CONFIGURED")
        async with httpx.AsyncClient(base_url="https://api.razorpay.com/v1", timeout=10) as client:
            response = await client.get(f"/payments/{external_id}", auth=(self.key_id, self.key_secret))
        if response.is_error: raise ValueError(f"RAZORPAY_LOOKUP_FAILED:{response.status_code}")
        data = response.json()
        return PaymentResult(external_id=external_id, status=str(data.get("status", "unknown")), amount=Decimal(str(data.get("amount", 0))) / Decimal("100"), currency=str(data.get("currency", "INR")))

    async def initiate_recovery(self, external_id: str, amount: Decimal) -> PaymentResult:
        if not self.test_mode: raise NotImplementedError("live Razorpay mode is disabled")
        if not self.key_id or not self.key_secret: raise ValueError("RAZORPAY_TEST_CREDENTIALS_NOT_CONFIGURED")
        payload = {"amount": int(amount * 100), "currency": "INR", "reference_id": external_id, "description": "DhanRakshak recovery payment link"}
        async with httpx.AsyncClient(base_url="https://api.razorpay.com/v1", timeout=10) as client:
            response = await client.post("/payment_links", json=payload, auth=(self.key_id, self.key_secret))
        if response.is_error: raise ValueError(f"RAZORPAY_PAYMENT_LINK_FAILED:{response.status_code}")
        data = response.json()
        return PaymentResult(external_id=str(data.get("id", external_id)), status=str(data.get("status", "created")), amount=amount)
