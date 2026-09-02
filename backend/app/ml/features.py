from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

BASE_NUMERIC = ["amount", "customer_lifetime_value", "historical_payment_success_rate", "historical_recovery_rate", "retry_count", "days_overdue", "customer_tenure", "previous_failed_attempts", "previous_recovery_actions", "days_since_last_payment"]
BASE_CATEGORICAL = ["payment_method", "failure_reason", "subscription_status", "checkout_stage", "preferred_channel", "time_of_day", "day_of_week", "segment"]


@dataclass(frozen=True)
class FeatureDefinition:
    name: str
    numeric: list[str]
    categorical: list[str]

    @property
    def all(self) -> list[str]:
        return self.numeric + self.categorical


class RecoveryFeatureEngineer:
    """One source of truth for pre-intervention recovery features."""

    def __init__(self, include_action: bool = False):
        self.definition = FeatureDefinition("recovery_features_v1_action" if include_action else "recovery_features_v1", BASE_NUMERIC, BASE_CATEGORICAL + (["action"] if include_action else []))

    def transform_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        result = frame.copy()
        for column in self.definition.numeric:
            if column not in result: result[column] = 0.0
            result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0.0)
        for column in self.definition.categorical:
            if column not in result: result[column] = "unknown"
            result[column] = result[column].fillna("unknown").astype(str)
        return result[self.definition.all]

    def preprocessor(self) -> ColumnTransformer:
        return ColumnTransformer([("numeric", StandardScaler(), self.definition.numeric), ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=False), self.definition.categorical)], remainder="drop")

    def metadata(self) -> dict[str, Any]:
        return {"feature_set": self.definition.name, "numeric": self.definition.numeric, "categorical": self.definition.categorical, "all": self.definition.all}
