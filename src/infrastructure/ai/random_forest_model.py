# src/infrastructure/ai/random_forest_model.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import math
import numpy as np
from numpy.random import default_rng
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score
import joblib

# Limiar/espaços ideais vindos do projeto; mantém fallback para uso isolado
try:
    from config.settings import WATER_QUALITY_THRESHOLDS as WQT
except Exception:
    WQT = {
        "temp_min": 24.0, "temp_max": 28.0,
        "ph_min": 6.5, "ph_max": 8.5,
        "oxygen_min": 70.0,
        "turbidez_max": 50.0,
    }

# Diretório/arquivo do modelo treinado
MODEL_DIR = Path("data/models")
MODEL_DIR.mkdir(parents=True, exist_ok=True)
MODEL_PATH = MODEL_DIR / "rf_growth.joblib"

# Ordem fixa das features esperadas pelo modelo
FEATURES: List[str] = [
    "temperatura", "ph", "oxigenio", "turbidez", "dias_cultivo", "densidade"
]

# Pontos de referência ambientais (alvo "ideal" para escoragem auxiliar)
IDEAL = {
    "temperatura": (WQT.get("temp_min", 24.0) + WQT.get("temp_max", 28.0)) / 2,
    "ph":          (WQT.get("ph_min", 6.5) + WQT.get("ph_max", 8.5)) / 2,
    "oxigenio":    max(85.0, WQT.get("oxygen_min", 70.0) + 10.0),
    "turbidez":    min(20.0, WQT.get("turbidez_max", 50.0) / 2),
}
TARGET_WEIGHT_KG = 1.0

# ---------------- CACHE DE MODELO EM MEMÓRIA ----------------
_MODEL_CACHE: Optional[Dict[str, Any]] = None

def model_exists(path: Path = MODEL_PATH) -> bool:
    """Indica se o arquivo do modelo já foi gerado/salvo."""
    return Path(path).exists()

def _ensure_model(model_path: Path = MODEL_PATH):
    """Carrega o modelo 1x e retém em cache (_MODEL_CACHE)."""
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        _MODEL_CACHE = joblib.load(model_path)
    return _MODEL_CACHE["model"], _MODEL_CACHE["features"]
# ------------------------------------------------------------

def _gauss_score(x: float, mu: float, sigma: float) -> float:
    """Escore gaussiano em torno de mu (σ controla a tolerância)."""
    return float(math.exp(- ((x - mu) ** 2) / (2 * sigma ** 2)))

def _lin_clamp(x: float, lo: float, hi: float) -> float:
    """Limita x ao intervalo [lo, hi] (linear)."""
    return float(max(lo, min(hi, x)))

def env_score(temp: float, ph: float, oxy: float, turb: float, dens: float) -> float:
    """
    Multiplicador ambiental [0..1] combinando subescores:
    - Temperatura e pH: gaussiano em torno do ponto IDEAL.
    - Oxigênio: regime por faixas (depletado <30%; rampa até mínimo do WQT; ganho moderado acima).
    - Turbidez e Densidade: esquemas por degraus/faixas.
    Pesos: [0.28, 0.18, 0.28, 0.12, 0.14].
    """
    s_temp = _gauss_score(temp, IDEAL["temperatura"], 2.0)
    s_ph   = _gauss_score(ph,   IDEAL["ph"],         0.6)

    if oxy <= 30: s_oxy = 0.1
    elif oxy <= WQT.get("oxygen_min", 70.0):
        s_oxy = 0.3 + 0.7 * (oxy - 30) / (WQT.get("oxygen_min", 70.0) - 30)
    else:
        s_oxy = 0.7 + 0.3 * _lin_clamp((oxy - WQT.get("oxygen_min", 70.0)) / 30.0, 0, 1)

    if turb <= 20: s_turb = 1.0
    elif turb <= WQT.get("turbidez_max", 50.0): s_turb = 0.8
    elif turb <= 100: s_turb = 0.5
    else: s_turb = 0.25

    if   dens <= 20: dens_score = 1.0
    elif dens <= 25: dens_score = 0.9
    elif dens <= 35: dens_score = 0.7
    elif dens <= 50: dens_score = 0.5
    else:            dens_score = 0.3

    weights = np.array([0.28, 0.18, 0.28, 0.12, 0.14], float)
    return float(np.clip(np.dot(np.array([s_temp, s_ph, s_oxy, s_turb, dens_score]), weights), 0.0, 1.0))

def synth_weight_kg(temp: float, ph: float, oxy: float, turb: float,
                    dias: float, dens: float, rng: np.random.Generator) -> float:
    """
    Gera peso sintético (kg) segundo uma curva assintótica:
      W(dias) = Wmax * (1 - exp(-k * dias)), onde k depende do ambiente.
    Adiciona ruído gaussiano proporcional à severidade ambiental.
    """
    Wmax = 1.5
    k_base = 0.016
    Famb = env_score(temp, ph, oxy, turb, dens)
    k = k_base * (0.6 + 0.8 * Famb)
    weight = Wmax * (1.0 - math.exp(-k * dias))
    noise = rng.normal(0.0, 0.03 + 0.02 * (1 - Famb))
    return float(max(0.03, weight + noise))

def make_synth_dataset(n: int = 6000, seed: int = 42) -> Tuple[np.ndarray, np.ndarray]:
    """
    Cria dataset sintético (X, y) com n amostras para treino/validação.
    Faixas amplas de variação para cobrir regimes práticos de cultivo.
    """
    rng = default_rng(seed)
    temp = rng.uniform(18, 35, size=n)
    ph   = rng.uniform(5.5, 9.5, size=n)
    oxy  = rng.uniform(40, 100, size=n)
    turb = rng.uniform(5, 150, size=n)
    dias = rng.integers(5, 200, size=n).astype(float)
    dens = rng.uniform(10, 60, size=n)
    y = np.array([synth_weight_kg(t, p, o, tu, d, de, rng)
                  for t, p, o, tu, d, de in zip(temp, ph, oxy, turb, dias, dens)], float)
    X = np.stack([temp, ph, oxy, turb, dias, dens], axis=1).astype(float)
    return X, y

@dataclass
class RFConfig:
    """Hiperparâmetros principais do Random Forest."""
    n_estimators: int = 120
    max_depth: int | None = None
    random_state: int = 2024
    min_samples_leaf: int = 2

def train_and_save(config: RFConfig = RFConfig(),
                   dataset_n: int = 8000,
                   model_path: Path = MODEL_PATH) -> Dict[str, Any]:
    """
    Treina o RandomForest em dados sintéticos e salva o artefato .joblib.

    Retorna:
        dict com métricas e metadados do treino (R², caminho do modelo, tamanhos).
    """
    X, y = make_synth_dataset(n=dataset_n, seed=config.random_state)
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=config.random_state)
    rf = RandomForestRegressor(
        n_estimators=config.n_estimators,
        max_depth=config.max_depth,
        random_state=config.random_state,
        min_samples_leaf=config.min_samples_leaf,
        n_jobs=-1,
    )
    rf.fit(Xtr, ytr)
    ypred = rf.predict(Xte)
    r2 = r2_score(yte, ypred)
    joblib.dump({"model": rf, "features": FEATURES}, model_path)
    # Zera cache para forçar recarregamento no próximo uso
    global _MODEL_CACHE
    _MODEL_CACHE = None
    return {"r2": float(r2), "path": str(model_path), "n_train": len(Xtr), "n_test": len(Xte)}

def _to_feature_array(payload: Dict[str, float]) -> np.ndarray:
    """Monta o array 2D (1 x n_features) na ordem definida em FEATURES."""
    return np.array([[payload[k] for k in FEATURES]], float)

def predict_weight(payload: Dict[str, float], model_path: Path = MODEL_PATH) -> float:
    """
    Retorna o peso previsto (kg) para o payload informado.

    Requisitos:
        - payload deve conter as chaves em FEATURES.
        - modelo salvo precisa existir (use train_and_save antes, se necessário).
    """
    model, _ = _ensure_model(model_path)
    return float(model.predict(_to_feature_array(payload))[0])

def _idealized_payload_like(p: Dict[str, float]) -> Dict[str, float]:
    """Cria um payload 'gêmeo' com as mesmas variáveis de cultivo e ambiente idealizado."""
    return {
        "temperatura": IDEAL["temperatura"],
        "ph":          IDEAL["ph"],
        "oxigenio":    IDEAL["oxigenio"],
        "turbidez":    IDEAL["turbidez"],
        "dias_cultivo": p["dias_cultivo"],
        "densidade":    p["densidade"],
    }

def growth_metrics(payload: Dict[str, float],
                   model_path: Path = MODEL_PATH,
                   target_kg: float = TARGET_WEIGHT_KG) -> Dict[str, Any]:
    """
    Gera métricas de crescimento a partir do modelo:
        - peso_previsto_kg
        - growth_efficiency_percent: relação (peso / peso_ideal) em %
        - days_to_harvest: projeção de dias até a meta (target_kg)
        - optimal_conditions_assessment: avaliação qualitativa por variável
        - ideal_weight_kg: peso com ambiente idealizado

    Observação:
        days_to_harvest usa diferença semanal prevista para estimar ganho diário.
    """
    w = predict_weight(payload, model_path)
    w_ideal = predict_weight(_idealized_payload_like(payload), model_path)
    eff = float(100.0 * (w / w_ideal if w_ideal > 1e-6 else 0.0))
    p_plus = dict(payload); p_plus["dias_cultivo"] = float(p_plus["dias_cultivo"]) + 7.0
    w_plus = predict_weight(p_plus, model_path)
    daily_gain = max(1e-4, (w_plus - w) / 7.0)
    days_to = 0.0 if w >= target_kg else float(math.ceil((target_kg - w) / daily_gain))
    days_to = float(min(365.0, max(0.0, days_to)))
    assess = {
        "temperatura": "ótima" if WQT["temp_min"] <= payload["temperatura"] <= WQT["temp_max"]
                       else "aceitável" if abs(payload["temperatura"] - IDEAL["temperatura"]) <= 3 else "ruim",
        "ph": "ótimo" if WQT["ph_min"] <= payload["ph"] <= WQT["ph_max"]
              else "aceitável" if abs(payload["ph"] - IDEAL["ph"]) <= 0.8 else "ruim",
        "oxigenio": "ótimo" if payload["oxigenio"] >= max(IDEAL["oxigenio"] - 5, WQT["oxygen_min"]) else "baixa",
        "turbidez": "boa" if payload["turbidez"] <= WQT["turbidez_max"] else "alta",
        "densidade": "ok" if payload["densidade"] <= 25 else "alta",
    }
    return {
        "peso_previsto_kg": round(w, 3),
        "growth_efficiency_percent": round(min(max(eff, 0.0), 150.0), 1),
        "days_to_harvest": int(days_to),
        "optimal_conditions_assessment": assess,
        "ideal_weight_kg": round(w_ideal, 3),
    }

if __name__ == "__main__":
    # Executa treino rápido em dataset sintético e salva o modelo localmente.
    info = train_and_save()
    print(f"RF treinado: R²={info['r2']:.3f} • {info['n_train']}/{info['n_test']}")
    print(f"Modelo salvo em: {info['path']}")
