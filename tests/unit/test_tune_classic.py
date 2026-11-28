"""Unit tests for scripts/tune_classic.py."""

from __future__ import annotations

import numpy as np

from scripts import tune_classic


def test_generate_candidates_is_deterministic_product():
    space = {"C": [0.1, 1.0], "gamma": ["scale", 0.001]}
    candidates = tune_classic.generate_candidates(space)

    assert len(candidates) == 4
    assert candidates[0] == {"C": 0.1, "gamma": "scale"}
    assert candidates[-1] == {"C": 1.0, "gamma": 0.001}
    assert tune_classic.generate_candidates({}) == [{}]


def test_select_best_uses_mean_then_std():
    results = [
        {"params": {"C": 0.1}, "mean_macro_f1": 0.70, "std_macro_f1": 0.02},
        {"params": {"C": 1.0}, "mean_macro_f1": 0.80, "std_macro_f1": 0.03},
        {"params": {"C": 2.0}, "mean_macro_f1": 0.80, "std_macro_f1": 0.01},
    ]

    best = tune_classic.select_best(results)

    assert best["params"] == {"C": 2.0}


def test_group_importance_aggregates_known_feature_groups():
    importances = np.ones(tune_classic.FEATURE_DIM, dtype=np.float64)
    result = tune_classic.group_importance(importances)

    assert result["layout"] == 64.0
    assert result["orientation"] == 8.0
    assert result["hog"] == 1764.0
    assert len(result["top_features"]) == 20


def test_cross_validation_runs_on_synthetic_features():
    rng = np.random.default_rng(42)
    text = rng.normal(loc=0.0, scale=0.3, size=(10, 4))
    formula = rng.normal(loc=2.0, scale=0.3, size=(10, 4))
    features = np.vstack([text, formula]).astype(np.float32)
    labels = np.asarray(["text"] * 10 + ["formula"] * 10)
    groups = ["text-0"] * 5 + ["text-1"] * 5 + ["formula-0"] * 5 + ["formula-1"] * 5

    result = tune_classic.cross_validate_candidate(
        "rf",
        {"n_estimators": 10},
        features,
        labels,
        groups,
        cv_folds=2,
        seed=42,
    )

    assert result is not None
    assert result["n_folds"] >= 1
    assert 0.0 <= result["mean_macro_f1"] <= 1.0
    assert len(result["scores"]) == result["n_folds"]
