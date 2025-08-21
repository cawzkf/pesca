from pathlib import Path
from src.infrastructure.ai.random_forest_model import (
    RFConfig, train_and_save, predict_weight, growth_metrics
)

def _ensure_model_tmp(tmp_path: Path):
    mp = tmp_path / "rf_growth_test.joblib"
    info = train_and_save(
        config=RFConfig(n_estimators=60, min_samples_leaf=2, random_state=123),
        dataset_n=3000,
        model_path=mp
    )
    assert mp.exists()
    return mp

def test_better_conditions_predict_more(tmp_path):
    mp = _ensure_model_tmp(tmp_path)
    base = {"temperatura": 26.0, "ph": 7.2, "oxigenio": 88.0, "turbidez": 20.0, "dias_cultivo": 120, "densidade": 20.0}
    bad  = {"temperatura": 19.0, "ph": 9.2, "oxigenio": 55.0, "turbidez": 120.0, "dias_cultivo": 120, "densidade": 45.0}
    assert predict_weight(base, mp) > predict_weight(bad, mp)

def test_more_days_reduce_days_to_harvest(tmp_path):
    mp = _ensure_model_tmp(tmp_path)
    p1 = {"temperatura": 26.0, "ph": 7.2, "oxigenio": 85.0, "turbidez": 25.0, "dias_cultivo": 90, "densidade": 22.0}
    p2 = dict(p1); p2["dias_cultivo"] = 120
    m1 = growth_metrics(p1, mp); m2 = growth_metrics(p2, mp)
    assert m2["peso_previsto_kg"] >= m1["peso_previsto_kg"]
    assert m2["days_to_harvest"] <= m1["days_to_harvest"]
