"""Model factory and training helpers."""

from __future__ import annotations

from typing import Any

from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC


def build_model(name: str, cfg: dict[str, Any], random_state: int = 42) -> Pipeline:
    model_cfg = dict(cfg.get(name, {}))

    if name == "random_forest":
        clf = RandomForestClassifier(random_state=random_state, **model_cfg)
        return Pipeline([("clf", clf)])

    if name == "gradient_boosting":
        clf = GradientBoostingClassifier(random_state=random_state, **model_cfg)
        return Pipeline([("scaler", StandardScaler()), ("clf", clf)])

    if name == "logistic_regression":
        clf = LogisticRegression(random_state=random_state, **model_cfg)
        return Pipeline([("scaler", StandardScaler()), ("clf", clf)])

    if name == "svm_rbf":
        clf = SVC(kernel="rbf", random_state=random_state, **model_cfg)
        return Pipeline([("scaler", StandardScaler()), ("clf", clf)])

    if name == "mlp":
        model_cfg.setdefault("random_state", random_state)
        # YAML may load tuple-like lists
        if "hidden_layer_sizes" in model_cfg:
            model_cfg["hidden_layer_sizes"] = tuple(model_cfg["hidden_layer_sizes"])
        clf = MLPClassifier(**model_cfg)
        return Pipeline([("scaler", StandardScaler()), ("clf", clf)])

    raise ValueError(f"Unknown model: {name}")
