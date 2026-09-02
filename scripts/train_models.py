"""Train and evaluate DhanRakshak models using chronological dataset splits."""
from __future__ import annotations

import argparse
import gc
import json
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parents[1] / "backend"))

import pandas as pd
from sklearn.metrics import (average_precision_score, brier_score_loss, f1_score,
                             precision_score, recall_score, roc_auc_score)
from sklearn.pipeline import Pipeline

from app.ml.features import RecoveryFeatureEngineer
from app.ml.models import ActionRecoveryModel, IncrementalityModel, RevenueRiskModel, classifier

SEED = 2026
DATASET_VERSION = "synthetic-benchmark-2026-v1"
ACTIONS = ["retry", "payment_link", "whatsapp", "email", "sms", "delayed_retry", "promise_to_pay", "human_escalation", "no_action"]


def read_split(root: Path, split: str) -> pd.DataFrame:
    events = pd.read_csv(root / split / "recovery_events.csv")
    customers = pd.read_csv(root / "raw" / "customers.csv", usecols=["customer_id", "lifetime_value", "avg_order_value", "preferred_payment_method", "preferred_channel", "historical_payment_success_rate", "historical_recovery_rate", "days_since_last_payment", "customer_tenure", "segment"])
    frame = events.merge(customers, on="customer_id", how="left", validate="many_to_one")
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    frame["time_of_day"] = timestamps.dt.hour.map(lambda hour: "night" if hour < 6 else "morning" if hour < 12 else "afternoon" if hour < 18 else "evening")
    frame["day_of_week"] = timestamps.dt.day_name()
    frame["amount"] = pd.to_numeric(frame["original_amount"], errors="coerce")
    frame["customer_lifetime_value"] = pd.to_numeric(frame["lifetime_value"], errors="coerce")
    frame["retry_count"] = frame["event_id"].map(lambda value: int(value[-2:], 16) % 4)
    frame["days_overdue"] = frame["event_id"].map(lambda value: int(value[-4:-2], 16) % 61)
    frame["previous_failed_attempts"] = (1 - pd.to_numeric(frame["historical_payment_success_rate"], errors="coerce")) * 8
    frame["previous_recovery_actions"] = pd.to_numeric(frame["historical_recovery_rate"], errors="coerce") * 6
    frame["failure_reason"] = frame["action"].map(lambda value: "customer_abandoned" if value in {"payment_link", "no_action"} else "bank_declined")
    frame["subscription_status"] = frame["action"].map(lambda value: "past_due" if value in {"retry", "delayed_retry", "promise_to_pay"} else "active")
    frame["checkout_stage"] = "payment_failed"
    frame["eventually_recovered"] = frame["eventually_recovered"].astype(str).str.lower().eq("true").astype(int)
    frame["control_group"] = frame["control_group"].astype(str).str.lower().eq("true")
    return frame


def metrics(y_true: pd.Series, probabilities: list[float]) -> dict[str, float]:
    predictions = [int(value >= .5) for value in probabilities]
    return {"roc_auc": float(roc_auc_score(y_true, probabilities)), "pr_auc": float(average_precision_score(y_true, probabilities)), "precision": float(precision_score(y_true, predictions, zero_division=0)), "recall": float(recall_score(y_true, predictions, zero_division=0)), "f1": float(f1_score(y_true, predictions, zero_division=0)), "brier_score": float(brier_score_loss(y_true, probabilities)), "calibration": float(1 - brier_score_loss(y_true, probabilities))}


def precision_at(y_true: pd.Series, probabilities: list[float], fraction: float) -> float:
    count = max(1, int(len(probabilities) * fraction)); ranked = pd.Series(probabilities).nlargest(count).index
    return float(y_true.iloc[ranked].mean())


def save_artifact(directory: Path, model: Any, engineer: RecoveryFeatureEngineer, target: str, train_rows: int, validation_rows: int, test_rows: int, model_metrics: dict[str, Any], model_name: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "model.pkl").open("wb") as stream: pickle.dump(model, stream, protocol=pickle.HIGHEST_PROTOCOL)
    metadata = {"model_version": f"{model_name}-v1", "training_timestamp": datetime.now(timezone.utc).isoformat(), "dataset_version": DATASET_VERSION, "training_rows": train_rows, "validation_rows": validation_rows, "test_rows": test_rows, "features": engineer.definition.all, "target": target, "metrics": model_metrics}
    (directory / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (directory / "features.json").write_text(json.dumps(engineer.metadata(), indent=2), encoding="utf-8")
    (directory / "metrics.json").write_text(json.dumps(model_metrics, indent=2), encoding="utf-8")


def make_pipeline(engineer: RecoveryFeatureEngineer) -> Pipeline:
    return Pipeline([("features", engineer.preprocessor()), ("model", classifier())])


def train(root: Path, output: Path) -> None:
    train_frame, validation_frame, test_frame = [read_split(root, split) for split in ["train", "validation", "test"]]
    base_engineer = RecoveryFeatureEngineer()
    risk_pipeline = make_pipeline(base_engineer)
    risk_features = base_engineer.transform_frame(train_frame); risk_pipeline.fit(risk_features, train_frame["eventually_recovered"].rsub(1))
    risk_val = risk_pipeline.predict_proba(base_engineer.transform_frame(validation_frame))[:, 1]; risk_test = risk_pipeline.predict_proba(base_engineer.transform_frame(test_frame))[:, 1]
    risk_metrics = {**metrics(1 - validation_frame["eventually_recovered"], list(risk_val)), "test": {**metrics(1 - test_frame["eventually_recovered"], list(risk_test)), "precision_at_top_5_pct": precision_at(1 - test_frame["eventually_recovered"], list(risk_test), .05), "precision_at_top_10_pct": precision_at(1 - test_frame["eventually_recovered"], list(risk_test), .10)}}
    save_artifact(output / "revenue_risk", risk_pipeline, base_engineer, "eventually_unrecovered", len(train_frame), len(validation_frame), len(test_frame), risk_metrics, "revenue_risk")
    del risk_pipeline, risk_features, risk_val, risk_test
    gc.collect()

    action_engineer = RecoveryFeatureEngineer(include_action=True)
    action_pipeline = make_pipeline(action_engineer); action_pipeline.fit(action_engineer.transform_frame(train_frame), train_frame["eventually_recovered"])
    action_probabilities = action_pipeline.predict_proba(action_engineer.transform_frame(test_frame))[:, 1]
    per_action = {}
    for action in ACTIONS:
        mask = test_frame["action"] == action
        if mask.any():
            per_action[action] = metrics(test_frame.loc[mask, "eventually_recovered"], list(action_probabilities[mask.to_numpy()]))
    save_artifact(output / "action_recovery", action_pipeline, action_engineer, "recovered_given_action", len(train_frame), len(validation_frame), len(test_frame), {"per_action": per_action}, "action_recovery")
    del action_pipeline, action_probabilities
    gc.collect()

    control_train = train_frame[train_frame["control_group"]]
    incrementality_engineer = RecoveryFeatureEngineer()
    incrementality_pipeline = make_pipeline(incrementality_engineer); incrementality_pipeline.fit(incrementality_engineer.transform_frame(control_train), control_train["eventually_recovered"])
    treatment = test_frame[~test_frame["control_group"]].copy(); control = test_frame[test_frame["control_group"]]
    organic = incrementality_pipeline.predict_proba(incrementality_engineer.transform_frame(treatment))[:, 1]
    control_rate = float(control["eventually_recovered"].mean()); treatment_rate = float(treatment["eventually_recovered"].mean()); actual = float(pd.to_numeric(treatment["amount_recovered"], errors="coerce").sum()); estimated = float((pd.to_numeric(treatment["original_amount"], errors="coerce") * organic).sum())
    incrementality_metrics = {"control_recovery_rate": control_rate, "treatment_recovery_rate": treatment_rate, "uplift": treatment_rate - control_rate, "incremental_recovered_revenue": actual - estimated, "test_treatment_rows": len(treatment), "test_control_rows": len(control)}
    save_artifact(output / "incrementality", incrementality_pipeline, incrementality_engineer, "organic_recovery_probability", len(control_train), len(validation_frame), len(test_frame), incrementality_metrics, "incrementality")
    print(json.dumps({"revenue_risk": risk_metrics, "action_recovery": {"per_action": per_action}, "incrementality": incrementality_metrics}, indent=2))


def train_incrementality_only(root: Path, output: Path, max_control_rows: int | None = None) -> None:
    train_frame = read_split(root, "train")
    test_frame = read_split(root, "test")
    control_train = train_frame[train_frame["control_group"]]
    if max_control_rows and len(control_train) > max_control_rows:
        control_train = control_train.iloc[:max_control_rows].copy()
    engineer = RecoveryFeatureEngineer()
    pipeline = make_pipeline(engineer)
    pipeline.fit(engineer.transform_frame(control_train), control_train["eventually_recovered"])
    treatment = test_frame[~test_frame["control_group"]].copy(); control = test_frame[test_frame["control_group"]]
    organic = pipeline.predict_proba(engineer.transform_frame(treatment))[:, 1]
    actual = float(pd.to_numeric(treatment["amount_recovered"], errors="coerce").sum()); estimated = float((pd.to_numeric(treatment["original_amount"], errors="coerce") * organic).sum())
    model_metrics = {"control_recovery_rate": float(control["eventually_recovered"].mean()), "treatment_recovery_rate": float(treatment["eventually_recovered"].mean()), "uplift": float(treatment["eventually_recovered"].mean() - control["eventually_recovered"].mean()), "incremental_recovered_revenue": actual - estimated, "test_treatment_rows": len(treatment), "test_control_rows": len(control)}
    save_artifact(output / "incrementality", pipeline, engineer, "organic_recovery_probability", len(control_train), 0, len(test_frame), model_metrics, "incrementality")
    print(json.dumps(model_metrics, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--data-root", default="data"); parser.add_argument("--output-root", default="models"); parser.add_argument("--only", choices=["all", "incrementality"], default="all"); parser.add_argument("--max-control-rows", type=int)
    args = parser.parse_args()
    if args.only == "incrementality": train_incrementality_only(Path(args.data_root), Path(args.output_root), args.max_control_rows)
    else: train(Path(args.data_root), Path(args.output_root))


if __name__ == "__main__": main()