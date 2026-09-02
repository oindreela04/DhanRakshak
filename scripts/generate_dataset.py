"""Generate the reproducible Synthetic Benchmark Dataset.

The generator uses only the Python standard library so it can run before ML
dependencies are installed. Customer profiles are generated once and reused
by every downstream stream, preserving behavioral and temporal correlation.
"""
from __future__ import annotations

import argparse
import csv
import math
import random
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

SEED = 2026
START = datetime(2023, 1, 1, tzinfo=timezone.utc)
END = datetime(2026, 8, 31, 23, 59, tzinfo=timezone.utc)
LANGUAGES = ["English", "Hindi", "Hinglish", "Bengali", "Tamil", "Telugu", "Marathi", "Gujarati", "Kannada", "Malayalam"]
CITIES = ["Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Chennai", "Kolkata", "Pune", "Ahmedabad", "Jaipur", "Kochi", "Lucknow", "Indore", "Surat", "Chandigarh", "Coimbatore"]
SEGMENTS = ["consumer", "SMB", "enterprise", "high_value"]
PAYMENTS = ["upi", "credit_card", "debit_card", "netbanking", "wallet", "emi"]
FAILURES = ["insufficient_funds", "bank_declined", "expired_card", "authentication_failure", "network_error", "mandate_cancelled", "customer_abandoned", "unknown"]
ACTIONS = ["retry", "payment_link", "whatsapp", "email", "sms", "delayed_retry", "promise_to_pay", "human_escalation", "no_action"]
EVENT_ACTIONS = ["checkout_started", "payment_attempted", "payment_failed", "recovery_action", "payment_success", "invoice_created", "overdue", "promise_to_pay", "reminder", "subscription_charge", "failed", "retry", "payment_method_change", "success"]

CUSTOMER_COLUMNS = ["customer_id", "name", "language", "city", "segment", "customer_since", "lifetime_value", "avg_order_value", "preferred_payment_method", "preferred_channel", "historical_payment_success_rate", "historical_recovery_rate", "days_since_last_payment", "customer_tenure", "risk_segment"]
TRANSACTION_COLUMNS = ["transaction_id", "customer_id", "amount", "payment_method", "status", "failure_reason", "timestamp", "order_type", "retry_count"]
SUBSCRIPTION_COLUMNS = ["subscription_id", "customer_id", "plan", "amount", "billing_cycle", "status", "failed_attempts", "next_billing_date", "created_at"]
INVOICE_COLUMNS = ["invoice_id", "customer_id", "amount", "issue_date", "due_date", "status", "days_overdue"]
CHECKOUT_COLUMNS = ["session_id", "customer_id", "cart_value", "items", "started_at", "payment_attempted", "payment_method_attempted", "abandoned_at", "status", "device"]
RECOVERY_COLUMNS = ["recovery_id", "customer_id", "event_id", "action", "channel", "timestamp", "message", "outcome", "amount_recovered", "eventually_recovered", "recovered_amount", "recovery_timestamp", "recovery_action", "time_to_recovery_hours", "organic_recovery_probability", "incremental_recovery", "control_group", "original_amount", "payment_method"]


def iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def money(value: float) -> str:
    return f"{max(0.0, value):.2f}"


def choose(rng: random.Random, values: list[str], weights: list[float] | None = None) -> str:
    return rng.choices(values, weights=weights, k=1)[0]


def timestamp_for(rng: random.Random, since: datetime = START, until: datetime = END) -> datetime:
    seconds = int((until - since).total_seconds())
    return since + timedelta(seconds=rng.randrange(max(1, seconds)))


def weighted_payment(rng: random.Random) -> str:
    return choose(rng, PAYMENTS, [42, 18, 14, 11, 8, 7])


def customer_profile(rng: random.Random, index: int) -> dict[str, object]:
    segment = choose(rng, SEGMENTS, [72, 18, 7, 3])
    multipliers = {"consumer": 1, "SMB": 4, "enterprise": 13, "high_value": 25}
    base = rng.lognormvariate(math.log(900 * multipliers[segment]), 0.55)
    success = min(0.995, max(0.48, rng.normalvariate(0.86 if segment != "consumer" else 0.79, 0.09)))
    recovery = min(0.92, max(0.08, rng.normalvariate(0.50 if segment != "consumer" else 0.38, 0.14)))
    since = timestamp_for(rng, START, END - timedelta(days=120))
    return {
        "customer_id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"dhanrakshak-customer-{index}")),
        "name": f"Customer {index:06d}", "language": choose(rng, LANGUAGES), "city": choose(rng, CITIES),
        "segment": segment, "customer_since": iso(since), "lifetime_value": money(base * rng.uniform(1.2, 12)),
        "avg_order_value": money(base), "preferred_payment_method": weighted_payment(rng),
        "preferred_channel": choose(rng, ["whatsapp", "email", "sms"], [48, 37, 15]),
        "historical_payment_success_rate": f"{success:.4f}", "historical_recovery_rate": f"{recovery:.4f}",
        "days_since_last_payment": rng.randint(0, 90), "customer_tenure": max(1, (END - since).days),
        "risk_segment": choose(rng, ["low", "medium", "high", "critical"], [48, 31, 16, 5]),
        "_since": since, "_success": success, "_recovery": recovery,
        "_channel_response": {"whatsapp": rng.uniform(.55, .95), "email": rng.uniform(.40, .86), "sms": rng.uniform(.25, .72)},
        "_promise_reliability": min(.96, max(.08, rng.normalvariate(recovery, .13))),
    }


def payment_success(rng: random.Random, profile: dict[str, object], method: str, moment: datetime, amount: float) -> bool:
    probability = float(profile["_success"])
    probability += 0.12 if method == profile["preferred_payment_method"] else -0.06
    probability += {"upi": .04, "credit_card": .01, "debit_card": -.02, "netbanking": -.01, "wallet": .02, "emi": -.04}[method]
    probability += .04 if 9 <= moment.hour <= 14 else -.05 if moment.hour >= 22 or moment.hour <= 5 else 0
    probability -= min(.12, amount / 200000)
    return rng.random() < max(.05, min(.98, probability))


def recovery_label(rng: random.Random, profile: dict[str, object], action: str, channel: str, method: str, amount: float, moment: datetime) -> dict[str, object]:
    organic = max(.02, min(.88, float(profile["_recovery"]) * .75 + (0.08 if payment_success(rng, profile, method, moment, amount) else -.08)))
    control = rng.random() < .20
    action_effect = {"retry": .13, "payment_link": .22, "whatsapp": .17, "email": .11, "sms": .08, "delayed_retry": .16, "promise_to_pay": .25, "human_escalation": .29, "no_action": 0}[action]
    channel_effect = float(profile["_channel_response"][channel]) if channel in profile["_channel_response"] else .05
    intervention_probability = min(.96, max(.01, organic + action_effect * .55 + channel_effect * .15 - amount / 2500000))
    recovered = rng.random() < (organic if control else intervention_probability)
    recovered_amount = amount * rng.uniform(.72, 1.0) if recovered else 0
    recovery_time = min(END, moment + timedelta(hours=rng.uniform(2, 240))) if recovered else None
    return {"eventually_recovered": str(recovered).lower(), "recovered_amount": money(recovered_amount), "recovery_timestamp": iso(recovery_time), "time_to_recovery_hours": f"{(recovery_time - moment).total_seconds() / 3600:.2f}" if recovery_time else "", "organic_recovery_probability": f"{organic:.4f}", "incremental_recovery": money(max(0, recovered_amount if not control else 0)), "control_group": str(control).lower()}


def write_rows(path: Path, columns: list[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def split_timestamp(value: str) -> str:
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment < datetime(2025, 1, 1, tzinfo=timezone.utc): return "train"
    if moment < datetime(2026, 1, 1, tzinfo=timezone.utc): return "validation"
    return "test"


def split_file(raw_path: Path, columns: list[str], timestamp_column: str, output_root: Path) -> None:
    handles: dict[str, object] = {}
    writers: dict[str, csv.DictWriter] = {}
    try:
        for split in ["train", "validation", "test"]:
            destination = output_root / split / raw_path.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            handle = destination.open("w", newline="", encoding="utf-8")
            handles[split] = handle; writers[split] = csv.DictWriter(handle, fieldnames=columns); writers[split].writeheader()
        with raw_path.open(newline="", encoding="utf-8") as stream:
            for row in csv.DictReader(stream): writers[split_timestamp(row[timestamp_column])].writerow(row)
    finally:
        for handle in handles.values(): handle.close()


def generate(args: argparse.Namespace) -> None:
    rng = random.Random(args.seed)
    root = Path(args.output_root)
    if root.exists() and args.clean:
        if root.is_symlink() or getattr(root, "is_junction", lambda: False)():
            for child in root.iterdir():
                shutil.rmtree(child) if child.is_dir() else child.unlink()
        else:
            shutil.rmtree(root)
    raw = root / "raw"; raw.mkdir(parents=True, exist_ok=True)
    profiles = [customer_profile(rng, index) for index in range(1, args.customers + 1)]
    write_rows(raw / "customers.csv", CUSTOMER_COLUMNS, profiles)

    def profile() -> dict[str, object]: return profiles[rng.randrange(len(profiles))]
    transactions: list[dict[str, object]] = []
    for index in range(1, args.transactions + 1):
        customer = profile(); moment = timestamp_for(rng, customer["_since"]); method = choose(rng, PAYMENTS, [52 if p == customer["preferred_payment_method"] else 10 for p in PAYMENTS]); amount = max(50, rng.lognormvariate(math.log(float(customer["avg_order_value"])), .48)); success = payment_success(rng, customer, method, moment, amount); status = "success" if success else choose(rng, ["failed", "pending", "refunded"], [78, 12, 10]);
        transactions.append({"transaction_id": str(uuid.uuid4()), "customer_id": customer["customer_id"], "amount": money(amount), "payment_method": method, "status": status, "failure_reason": "" if success else choose(rng, FAILURES), "timestamp": iso(moment), "order_type": choose(rng, ["one_time", "subscription", "invoice"]), "retry_count": rng.randint(0, 3)})
    write_rows(raw / "transactions.csv", TRANSACTION_COLUMNS, transactions)

    subscriptions = []
    for _ in range(args.subscriptions):
        customer = profile(); created = timestamp_for(rng, customer["_since"], END - timedelta(days=30)); failed = max(0, int(rng.normalvariate(0.6 if customer["risk_segment"] in ["high", "critical"] else .15, .8))); subscriptions.append({"subscription_id": str(uuid.uuid4()), "customer_id": customer["customer_id"], "plan": choose(rng, ["starter", "growth", "scale", "enterprise"], [40, 35, 18, 7]), "amount": money(float(customer["avg_order_value"]) * rng.uniform(.7, 4)), "billing_cycle": choose(rng, ["monthly", "quarterly", "annual"], [72, 20, 8]), "status": choose(rng, ["active", "paused", "cancelled", "past_due"], [72, 8, 10, 10]), "failed_attempts": failed, "next_billing_date": iso(created + timedelta(days=rng.choice([7, 14, 30]))), "created_at": iso(created)})
    write_rows(raw / "subscriptions.csv", SUBSCRIPTION_COLUMNS, subscriptions)

    invoices = []
    for _ in range(args.invoices):
        customer = profile(); issue = timestamp_for(rng, customer["_since"], END - timedelta(days=20)); due = issue + timedelta(days=rng.choice([7, 15, 30])); overdue = max(0, (END - due).days) if rng.random() < .22 else 0; status = "paid" if overdue == 0 or rng.random() < .55 else choose(rng, ["overdue", "partially_paid", "void"], [70, 20, 10]); invoices.append({"invoice_id": str(uuid.uuid4()), "customer_id": customer["customer_id"], "amount": money(float(customer["avg_order_value"]) * rng.uniform(1, 8)), "issue_date": iso(issue), "due_date": iso(due), "status": status, "days_overdue": overdue if status == "overdue" else 0})
    write_rows(raw / "invoices.csv", INVOICE_COLUMNS, invoices)

    checkouts = []
    for _ in range(args.checkouts):
        customer = profile(); started = timestamp_for(rng, customer["_since"]); attempted = rng.random() < .68; abandoned = started + timedelta(minutes=rng.randint(2, 180)) if not attempted or rng.random() < .25 else None; checkouts.append({"session_id": str(uuid.uuid4()), "customer_id": customer["customer_id"], "cart_value": money(float(customer["avg_order_value"]) * rng.uniform(.5, 3)), "items": rng.randint(1, 8), "started_at": iso(started), "payment_attempted": str(attempted).lower(), "payment_method_attempted": weighted_payment(rng) if attempted else "", "abandoned_at": iso(abandoned), "status": "abandoned" if abandoned else "completed", "device": choose(rng, ["android", "ios", "web", "tablet"], [42, 28, 25, 5])})
    write_rows(raw / "checkout_sessions.csv", CHECKOUT_COLUMNS, checkouts)

    recoveries = []
    for _ in range(args.recovery_events):
        customer = profile(); moment = timestamp_for(rng, customer["_since"]); method = weighted_payment(rng); action = choose(rng, ACTIONS, [14, 13, 14, 14, 8, 10, 10, 3, 14]); channel = action if action in ["whatsapp", "email", "sms"] else customer["preferred_channel"]; amount = max(50, float(customer["avg_order_value"]) * rng.uniform(.7, 4)); labels = recovery_label(rng, customer, action, channel, method, amount, moment); recovered = labels["eventually_recovered"] == "true"; recoveries.append({"recovery_id": str(uuid.uuid4()), "customer_id": customer["customer_id"], "event_id": str(uuid.uuid4()), "action": action, "channel": channel, "timestamp": iso(moment), "message": f"{action.replace('_', ' ').title()} for {customer['segment']} account", "outcome": "recovered" if recovered else "unrecovered", "amount_recovered": labels["recovered_amount"], "recovery_action": action, "original_amount": money(amount), "payment_method": method, **labels})
    write_rows(raw / "recovery_events.csv", RECOVERY_COLUMNS, recoveries)

    for name, columns, stamp in [("transactions", TRANSACTION_COLUMNS, "timestamp"), ("subscriptions", SUBSCRIPTION_COLUMNS, "created_at"), ("invoices", INVOICE_COLUMNS, "issue_date"), ("checkout_sessions", CHECKOUT_COLUMNS, "started_at"), ("recovery_events", RECOVERY_COLUMNS, "timestamp"), ("customers", CUSTOMER_COLUMNS, "customer_since")]: split_file(raw / f"{name}.csv", columns, stamp, root)
    print(f"Generated Synthetic Benchmark Dataset in {root} with seed {args.seed}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", default="data")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--customers", type=int, default=100_000)
    parser.add_argument("--transactions", type=int, default=500_000)
    parser.add_argument("--subscriptions", type=int, default=100_000)
    parser.add_argument("--invoices", type=int, default=150_000)
    parser.add_argument("--checkouts", type=int, default=200_000)
    parser.add_argument("--recovery-events", type=int, default=300_000)
    generate(parser.parse_args())


if __name__ == "__main__": main()