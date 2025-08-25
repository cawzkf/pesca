# src/infrastructure/ai/genetic_feed_optimizer.py
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Tuple
from datetime import datetime, timedelta
import math
import random
import numpy as np

# Limiares do projeto; fallback se o import falhar (útil em testes isolados)
try:
    from config.settings import WATER_QUALITY_THRESHOLDS as WQT
except Exception:
    WQT = {
        "temp_min": 24.0, "temp_max": 28.0,
        "ph_min": 6.5, "ph_max": 8.5,
        "oxygen_min": 70.0,
        "turbidez_max": 50.0,
    }


# ============================
# Configuração do GA
# ============================
@dataclass
class GAConfig:
    """
    Hiperparâmetros do Algoritmo Genético e espaço de busca.

    Atributos:
        pop_size: Tamanho da população.
        max_generations: Número máximo de gerações.
        tournament_k: Tamanho do torneio para seleção.
        crossover_alpha_min/max: Faixa de α no crossover (blend).
        mutation_sigma: Desvio-padrão da mutação gaussiana.
        elite_frac: Fração elitista (indivíduos preservados).
        stagnation_patience: Nº de gerações sem melhora para parar.
        seed: Semente do PRNG para reprodutibilidade.

        min_g/max_g: Limites de g (g/peixe/dia).
        sweet_g: “Ponto doce” onde excesso começa a penalizar.
        waste_weight: Peso da penalização por excesso.
    """
    pop_size: int = 28
    max_generations: int = 60
    tournament_k: int = 2
    crossover_alpha_min: float = 0.15
    crossover_alpha_max: float = 0.85
    mutation_sigma: float = 0.25
    elite_frac: float = 0.12
    stagnation_patience: int = 12
    seed: int = 42

    # Espaço de busca (g/peixe)
    min_g: float = 0.5
    max_g: float = 5.0

    # “ponto doce” (onde excesso começa a punir)
    sweet_g: float = 2.8
    waste_weight: float = 1.0


# ============================
# Helpers de ambiente
# ============================
def _clamp(x: float, lo: float, hi: float) -> float:
    """Limita x ao intervalo [lo, hi]."""
    return float(max(lo, min(hi, x)))


def _range_score(x: float, lo: float, hi: float, soft: float) -> float:
    """
    Converte distância de x ao intervalo [lo, hi] em um escore [0..1].
    Dentro do intervalo → 1.0; fora → decai exponencialmente (parâmetro soft).
    """
    if lo <= x <= hi:
        return 1.0
    d = min(abs(x - lo), abs(x - hi))
    return math.exp(-d / float(soft))


def _env_multiplier(temp: float, ph: float, oxy: float, turb: float, dens: float) -> float:
    """
    Calcula multiplicador ambiental [0..1] combinando temperatura, pH, O2,
    turbidez e densidade (pesos: 0.28, 0.18, 0.28, 0.12, 0.14).
    """
    s_temp = _range_score(temp, WQT["temp_min"], WQT["temp_max"], soft=2.5)
    s_ph   = _range_score(ph,   WQT["ph_min"],   WQT["ph_max"],   soft=0.6)

    # Oxigênio: regime por faixas (duro abaixo de 30%, rampa até o mínimo recomendado)
    if oxy <= 30:
        s_oxy = 0.10
    elif oxy < WQT["oxygen_min"]:
        s_oxy = 0.30 + 0.70 * (oxy - 30.0) / max(WQT["oxygen_min"] - 30.0, 1e-6)
    else:
        s_oxy = 0.80 + 0.20 * _clamp((oxy - WQT["oxygen_min"]) / 30.0, 0.0, 1.0)

    # Turbidez: penalização por degraus
    turb_max = float(WQT.get("turbidez_max", 50.0))
    if   turb <= 20:     s_turb = 1.0
    elif turb <= turb_max: s_turb = 0.85
    elif turb <= 100:    s_turb = 0.60
    else:                s_turb = 0.35

    # Densidade: penalização por faixas
    if   dens <= 20: dens_s = 1.00
    elif dens <= 25: dens_s = 0.92
    elif dens <= 35: dens_s = 0.75
    elif dens <= 50: dens_s = 0.55
    else:            dens_s = 0.40

    # Combinação linear com pesos
    weights = np.array([0.28, 0.18, 0.28, 0.12, 0.14], dtype=float)
    vec     = np.array([s_temp, s_ph, s_oxy, s_turb, dens_s], dtype=float)
    return float(np.clip(np.dot(vec, weights), 0.0, 1.0))


# ============================
# Função objetivo do GA
# ============================
def _score_candidate(g: float, *, temp: float, ph: float, oxy: float, turb: float,
                     dens: float, cfg: GAConfig) -> float:
    """
    Avalia um candidato g (g/peixe/dia).

    Score = log1p(g) * env_multiplier - waste_pen(g)

    - Benefício de crescimento ~ log1p(g) (retornos decrescentes).
    - Penalização de desperdício somente acima de sweet_g.
    """
    g = _clamp(g, cfg.min_g, cfg.max_g)
    growth_benefit = math.log1p(g)
    env_mult = _env_multiplier(temp, ph, oxy, turb, dens)

    if g <= cfg.sweet_g:
        waste_pen = 0.0
    else:
        waste_pen = cfg.waste_weight * ((g - cfg.sweet_g) / (cfg.max_g - cfg.sweet_g + 1e-6)) ** 2

    return float(growth_benefit * env_mult - waste_pen)


# ============================
# GA principal
# ============================
def optimize_feed(*,
                  fish_count: int,
                  weight_kg: float,
                  density: float,
                  temperature: float,
                  ph: float,
                  oxygen: float,
                  turbidity: float,
                  config: GAConfig | None = None) -> Dict[str, Any]:
    """
    Executa o Algoritmo Genético para maximizar o score de g (g/peixe/dia).

    Seleção: torneio k=2.
    Crossover: blend com α ~ U[crossover_alpha_min, crossover_alpha_max].
    Mutação: ruído gaussiano (σ = mutation_sigma).
    Elitismo: elite_frac da população.
    Parada: estagnação por 'stagnation_patience' ou limite de gerações.

    Retorna dicionário com melhor g, score, histórico e metadados.
    """
    cfg = config or GAConfig()
    rnd = random.Random(cfg.seed)

    pop: List[float] = [rnd.uniform(cfg.min_g, cfg.max_g) for _ in range(cfg.pop_size)]

    def eval_score(x: float) -> float:
        return _score_candidate(
            x, temp=temperature, ph=ph, oxy=oxygen, turb=turbidity, dens=density, cfg=cfg
        )

    history: List[float] = []
    stagnation = 0
    best_g = None
    best_s = -1e9
    elite_n = max(1, int(round(cfg.elite_frac * cfg.pop_size)))

    for gen in range(cfg.max_generations):
        scored = sorted(((g, eval_score(g)) for g in pop), key=lambda t: t[1], reverse=True)

        if scored[0][1] > best_s + 1e-9:
            best_g, best_s = scored[0]
            stagnation = 0
        else:
            stagnation += 1

        history.append(best_s)

        if stagnation >= cfg.stagnation_patience:
            break

        elites = [g for g, _ in scored[:elite_n]]

        def tournament_pick() -> float:
            a, b = rnd.sample(pop, cfg.tournament_k)
            return a if eval_score(a) >= eval_score(b) else b

        new_pop: List[float] = elites[:]
        while len(new_pop) < cfg.pop_size:
            p1, p2 = tournament_pick(), tournament_pick()
            alpha = rnd.uniform(cfg.crossover_alpha_min, cfg.crossover_alpha_max)
            child = alpha * p1 + (1.0 - alpha) * p2
            child += rnd.gauss(0.0, cfg.mutation_sigma)
            child = _clamp(child, cfg.min_g, cfg.max_g)
            new_pop.append(child)

        pop = new_pop

    final_best = max(pop, key=eval_score)
    final_score = eval_score(final_best)
    if final_score > best_s:
        best_g, best_s = final_best, final_score

    env_mult = _env_multiplier(temperature, ph, oxygen, turbidity, density)
    total = best_g * float(max(0, fish_count))

    notes = (
        f"GA: densidade={density:.1f}/m³, temp={temperature:.1f}°C, pH={ph:.2f}, "
        f"O₂={oxygen:.0f}%, turbidez={turbidity:.1f} NTU, peso_médio={weight_kg:.3f} kg | "
        f"ambiente={env_mult:.2f}"
    )

    return {
        "grams_per_fish": float(best_g),
        "total_grams": float(total),
        "score": float(best_s),
        "env_multiplier": float(env_mult),
        "history": history,
        "converged": len(history) < cfg.max_generations,
        "generations": len(history),
        "notes": notes,
        "config": asdict(cfg),
    }


# ============================
# Plano de ração completo (com agenda)
# ============================
def recommend_feed_plan(
    *,
    fish_count: int,
    weight_kg: float,
    density: float,
    temperature: float,
    ph: float,
    oxygen: float,
    turbidity: float,
    use_ga: bool = True,
    ga_cfg: GAConfig | None = None,
) -> Dict[str, Any]:
    """
    Retorna um plano diário:
      grams_per_fish, total_grams, base/adusted FR,
      env_multiplier, meals (horários), per_meal_grams_per_fish, notes
    """
    # Tabela base de Feed Rate (%) por peso (kg) — regra de bolso
    w = max(0.01, float(weight_kg))
    if w < 0.020:      base_fr = 4.5
    elif w < 0.050:    base_fr = 3.0
    elif w < 0.100:    base_fr = 2.2
    elif w < 0.250:    base_fr = 1.6
    elif w < 0.500:    base_fr = 1.2
    elif w < 1.000:    base_fr = 1.0
    else:              base_fr = 0.8

    env_mult = _env_multiplier(temperature, ph, oxygen, turbidity, density)

    # FR base pelo multiplicador ambiental
    adjusted_fr = base_fr * env_mult
    g_table = (adjusted_fr / 100.0) * (w * 1000.0)  # g/peixe/dia (regra de bolso pela tabela)

    # Combinação GA + tabela (blend 60/40) ou somente tabela
    if use_ga:
        ga_out = optimize_feed(
            fish_count=fish_count,
            weight_kg=w,
            density=density,
            temperature=temperature,
            ph=ph,
            oxygen=oxygen,
            turbidity=turbidity,
            config=ga_cfg or GAConfig(),
        )
        g_ga = float(ga_out["grams_per_fish"])
        grams_per_fish = 0.6 * g_ga + 0.4 * g_table
        ga_note = f"GA={g_ga:.2f} g/peixe"
    else:
        grams_per_fish = g_table
        ga_note = "GA desativado"

    # Limites práticos de porção por peixe
    grams_per_fish = float(max(0.1, min(10.0, grams_per_fish)))
    total_grams = grams_per_fish * max(0, int(fish_count))

    # Nº de refeições e janelas por ambiente
    if env_mult >= 0.85:
        meals_n = 3
        slots = [(8, 0, "manhã"), (14, 0, "tarde"), (20, 0, "noite")]
    elif env_mult >= 0.60:
        meals_n = 2
        slots = [(9, 0, "manhã"), (18, 0, "tarde")]
    else:
        meals_n = 1
        slots = [(9, 0, "manhã")]

    # Agenda (timezone local)
    now = datetime.now().astimezone()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    def next_occurrence(h: int, m: int) -> datetime:
        """Próxima ocorrência do horário h:m (amanhã se já passou hoje)."""
        t = today.replace(hour=h, minute=m)
        if t <= now:
            t = t + timedelta(days=1)
        return t

    per_meal = grams_per_fish / meals_n
    meals: List[Dict[str, Any]] = []
    for h, m, label in slots[:meals_n]:
        tt = next_occurrence(h, m)
        meals.append({
            "time": tt,  # datetime timezone-aware (local)
            "label": label,
            "grams_per_fish": float(per_meal),
            "total_grams": float(per_meal * fish_count),
        })

    notes = (
        f"FR base={base_fr:.2f}% • Ajustada={adjusted_fr:.2f}% • "
        f"ambiente={env_mult:.2f} • {ga_note}"
    )

    return {
        "grams_per_fish": grams_per_fish,
        "total_grams": total_grams,
        "base_feed_rate_percent": base_fr,
        "adjusted_feed_rate_percent": adjusted_fr,
        "env_multiplier": env_mult,
        "meals": meals,
        "per_meal_grams_per_fish": per_meal,
        "notes": notes,
    }
