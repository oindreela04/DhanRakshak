"""Validate the Synthetic Benchmark Dataset without loading it all into memory."""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ACTIONS = {"retry", "payment_link", "whatsapp", "email", "sms", "delayed_retry", "promise_to_pay", "human_escalation", "no_action"}
PAYMENTS = {"upi", "credit_card", "debit_card", "netbanking", "wallet", "emi"}
AMOUNT_COLUMNS = {"amount", "cart_value", "amount_recovered", "recovered_amount", "original_amount", "lifetime_value", "avg_order_value"}
TIMESTAMP_COLUMNS = {"customer_since", "timestamp", "created_at", "next_billing_date", "issue_date", "due_date", "started_at", "abandoned_at", "recovery_timestamp"}


def parse_time(value: str) -> datetime | None:
    if not value: return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate(root: Path) -> list[str]:
    errors: list[str] = []

    def add_error(message: str) -> None:
        if len(errors) < 50: errors.append(message)
    customer_ids: set[str] = set()
    customer_since: dict[str, datetime] = {}
    raw = root / "raw"
    customers = raw / "customers.csv"
    with customers.open(newline="", encoding="utf-8") as stream:
        for line, row in enumerate(csv.DictReader(stream), 2):
            identifier = row["customer_id"]
            if identifier in customer_ids: add_error(f"duplicate customer_id at line {line}")
            customer_ids.add(identifier); customer_since[identifier] = parse_time(row["customer_since"])  # type: ignore[assignment]
            for field in ["lifetime_value", "avg_order_value"]:
                if float(row[field]) < 0: add_error(f"negative {field} at line {line}")
    for path in sorted(raw.glob("*.csv")):
        seen: set[str] = set()
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            for line, row in enumerate(reader, 2):
                for field, value in row.items():
                    if field in AMOUNT_COLUMNS and value and float(value) < 0: add_error(f"negative {field} in {path.name}:{line}")
                    if field in TIMESTAMP_COLUMNS and value:
                        try:
                            moment = parse_time(value)
                            if moment and moment > datetime.now(timezone.utc) + __import__("datetime").timedelta(minutes=5): add_error(f"future timestamp in {path.name}:{line}")
                        except ValueError: add_error(f"invalid timestamp in {path.name}:{line}")
                identifier = row.get("customer_id", row.get("event_id", ""))
                if identifier and identifier not in customer_ids: add_error(f"unknown customer reference in {path.name}:{line}")
                event_time = next((row.get(field) for field in ["timestamp", "created_at", "issue_date", "started_at"] if row.get(field)), None)
                if identifier and event_time and customer_since.get(identifier) and parse_time(event_time) < customer_since[identifier]: add_error(f"event before customer creation in {path.name}:{line}")
                id_field = next((field for field in ["transaction_id", "subscription_id", "invoice_id", "session_id", "recovery_id", "event_id", "customer_id"] if field in row), None)
                if id_field:
                    value = row[id_field]
                    if value in seen: add_error(f"duplicate {id_field} in {path.name}:{line}")
                    seen.add(value)
                if "action" in row and row["action"] not in ACTIONS: add_error(f"invalid action in {path.name}:{line}")
                if "payment_method" in row and row["payment_method"] not in PAYMENTS: add_error(f"invalid payment method in {path.name}:{line}")
                if "amount_recovered" in row and row["amount_recovered"] and float(row["amount_recovered"]) > float(row["original_amount"]): add_error(f"recovered amount exceeds original in {path.name}:{line}")
                if "organic_recovery_probability" in row and not (0 <= float(row["organic_recovery_probability"]) <= 1): add_error(f"invalid organic probability in {path.name}:{line}")
                if row.get("control_group") == "true" and row.get("incremental_recovery") not in {"0.00", "0"}: add_error(f"target leakage in {path.name}:{line}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--root", default="data")
    errors = validate(Path(parser.parse_args().root))
    if errors:
        print(f"Validation failed with {len(errors)} errors")
        print("\n".join(errors[:20])); raise SystemExit(1)
    print("Synthetic Benchmark Dataset validation passed")


if __name__ == "__main__": main()