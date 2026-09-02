from decimal import Decimal

from app.adapters.base import PaymentAdapter, PaymentResult


class DemoAdapter(PaymentAdapter):
    """Deterministic adapter for local demos; it does not call a payment provider."""

    async def verify_payment(self, external_id: str) -> PaymentResult:
        return PaymentResult(external_id=external_id, status="verified", amount=Decimal("0.00"))

    async def initiate_recovery(self, external_id: str, amount: Decimal) -> PaymentResult:
        return PaymentResult(external_id=external_id, status="accepted", amount=amount)
