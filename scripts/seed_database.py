"""Bulk seed the core ORM tables from raw synthetic CSV files."""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from uuid import UUID
from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).parents[1] / "backend"))
from app.db import Base, build_engine  # noqa: E402
from app.models import CheckoutSession, Customer, Invoice, RecoveryEvent, Subscription, Transaction  # noqa: E402


def parse_datetime(value: str) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def batches(path: Path, size: int = 5000):
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream); batch = []
        for row in reader:
            batch.append(row)
            if len(batch) == size: yield batch; batch = []
        if batch: yield batch


def seed(root: Path, database_url: str, limit: int | None = None) -> None:
    engine = build_engine(database_url); Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.execute(delete(RecoveryEvent)); session.execute(delete(Transaction)); session.execute(delete(CheckoutSession)); session.execute(delete(Invoice)); session.execute(delete(Subscription)); session.execute(delete(Customer)); session.commit()
        files = [("customers.csv", Customer, lambda row: {"id": UUID(row["customer_id"]), "external_id": row["customer_id"], "name": row["name"], "email": f"{row['customer_id']}@synthetic.invalid", "language": row["language"], "preferred_channel": row["preferred_channel"], "preferred_payment_method": row["preferred_payment_method"], "segment": row["segment"]}), ("transactions.csv", Transaction, lambda row: {"id": UUID(row["transaction_id"]), "customer_id": UUID(row["customer_id"]), "amount": row["amount"], "currency": "INR", "status": row["status"], "failure_code": row["failure_reason"] or None, "payment_method": row["payment_method"], "occurred_at": parse_datetime(row["timestamp"])}), ("subscriptions.csv", Subscription, lambda row: {"id": UUID(row["subscription_id"]), "customer_id": UUID(row["customer_id"]), "external_id": row["subscription_id"], "status": row["status"], "amount": row["amount"]}), ("invoices.csv", Invoice, lambda row: {"id": UUID(row["invoice_id"]), "customer_id": UUID(row["customer_id"]), "amount": row["amount"], "status": row["status"], "due_at": parse_datetime(row["due_date"])}), ("checkout_sessions.csv", CheckoutSession, lambda row: {"id": UUID(row["session_id"]), "customer_id": UUID(row["customer_id"]), "status": row["status"], "amount": row["cart_value"]}), ("recovery_events.csv", RecoveryEvent, lambda row: {"id": UUID(row["recovery_id"]), "customer_id": UUID(row["customer_id"]), "event_type": row["action"], "payload": row})]
        for filename, model, transform in files:
            count = 0
            for batch in batches(root / "raw" / filename):
                if limit is not None: batch = batch[: max(0, limit - count)]
                session.bulk_insert_mappings(model, [transform(row) for row in batch]); session.commit(); count += len(batch)
                if limit is not None and count >= limit: break
            print(f"Seeded {count} {model.__tablename__}")


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--root", default="data"); parser.add_argument("--database-url", default="sqlite:///./dhanrakshak.db"); parser.add_argument("--limit", type=int)
    args = parser.parse_args(); seed(Path(args.root), args.database_url, args.limit)


if __name__ == "__main__": main()