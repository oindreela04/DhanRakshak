from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PaymentResult:
    external_id: str
    status: str
    amount: Decimal
    currency: str = "INR"


class PaymentAdapter(ABC):
    @abstractmethod
    async def verify_payment(self, external_id: str) -> PaymentResult:
        raise NotImplementedError

    @abstractmethod
    async def initiate_recovery(self, external_id: str, amount: Decimal) -> PaymentResult:
        raise NotImplementedError
