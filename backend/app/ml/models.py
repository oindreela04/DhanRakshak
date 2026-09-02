from __future__ import annotations

import json
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.pipeline import Pipeline

from app.ml.features import RecoveryFeatureEngineer


def classifier() -> Any:
    try:
        from xgboost import XGBClassifier
        return XGBClassifier(n_estimators=220, max_depth=5, learning_rate=.08, subsample=.85, colsample_bytree=.85, random_state=2026, eval_metric="logloss", n_jobs=2)
    except Exception:
        return HistGradientBoostingClassifier(max_iter=180, learning_rate=.08, max_leaf_nodes=31, l2_regularization=1.0, random_state=2026)


class TrainedModel:
    model_name = "base"

    def __init__(self, pipeline: Pipeline, feature_engineer: RecoveryFeatureEngineer, metadata: dict[str, Any], metrics: dict[str, Any]):
        self.pipeline, self.feature_engineer, self.metadata, self.metrics = pipeline, feature_engineer, metadata, metrics

    def predict_proba(self, records: pd.DataFrame | dict[str, Any] | list[dict[str, Any]]) -> list[float]:
        frame = records if isinstance(records, pd.DataFrame) else pd.DataFrame(records if isinstance(records, list) else [records])
        probabilities = self.pipeline.predict_proba(self.feature_engineer.transform_frame(frame))[:, 1]
        return [float(value) for value in probabilities]

    def predict(self, records: pd.DataFrame | dict[str, Any] | list[dict[str, Any]]) -> list[int]:
        frame = records if isinstance(records, pd.DataFrame) else pd.DataFrame(records if isinstance(records, list) else [records])
        return [int(value) for value in self.pipeline.predict(self.feature_engineer.transform_frame(frame))]

    @classmethod
    def load(cls, artifact_dir: str | Path) -> "TrainedModel":
        directory = Path(artifact_dir)
        if not (directory / "model.pkl").exists(): raise FileNotFoundError("MODEL_NOT_TRAINED")
        with (directory / "model.pkl").open("rb") as stream: pipeline = pickle.load(stream)
        metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8")); metrics = json.loads((directory / "metrics.json").read_text(encoding="utf-8"))
        return cls(pipeline, RecoveryFeatureEngineer(include_action="action" in metadata.get("features", [])), metadata, metrics)


class RevenueRiskModel(TrainedModel):
    model_name = "revenue_risk"


class ActionRecoveryModel(TrainedModel):
    model_name = "action_recovery"


class IncrementalityModel(TrainedModel):
    model_name = "incrementality"
