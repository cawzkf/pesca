import math
import types
import pytest

from src.infrastructure.sensors import sensor_simulator as sim


@pytest.fixture(autouse=True)
def reset_state():
    # limpa estado antes de cada teste
    sim.STATE.clear()
    # garante um profile de teste simples
    sim.TANK_PROFILES[1] = {
        "temperature_base": 26.0, "temp_var": 2.0,
        "ph_base": 7.2, "ph_var": 0.5,
        "oxygen_base": 85.0, "oxy_var": 10.0,
        "turbidity_base": 25.0, "turb_var": 15.0,
    }
    sim.TANK_PROFILES[2] = {
        "temperature_base": 25.0, "temp_var": 1.5,
        "ph_base": 7.0, "ph_var": 0.4,
        "oxygen_base": 80.0, "oxy_var": 8.0,
        "turbidity_base": 30.0, "turb_var": 10.0,
    }


def test_continuidade_temporal_sem_saltos():
    # primeira leitura (inicializa com base)
    v1 = sim.generate_reading(tank_id=1, minute_of_day=0)
    # segunda leitura próxima no tempo
    v2 = sim.generate_reading(tank_id=1, minute_of_day=1)

    # diferenças devem ser moderadas (sem saltos)
    assert abs(v2["temperature"] - v1["temperature"]) < 3.0
    assert abs(v2["ph"] - v1["ph"]) < 0.8
    assert abs(v2["oxygen"] - v1["oxygen"]) < 20.0
    assert abs(v2["turbidity"] - v1["turbidity"]) < 40.0


def test_ciclo_diario_manha_mais_quente_que_tarde():
    # 06:00 (seno positivo) vs 18:00 (seno negativo)
    six_am = 6 * 60
    six_pm = 18 * 60

    v_morning = sim.generate_reading(tank_id=1, minute_of_day=six_am)
    v_evening = sim.generate_reading(tank_id=1, minute_of_day=six_pm)

    # tendência: pela componente senoidal, manhã tende a puxar pra cima
    assert v_morning["temperature"] >= v_evening["temperature"] - 0.5


def test_injecao_de_problema_forcada_oxy_baixo(monkeypatch):
    """Força problema de O2 baixo sem afetar o ruído do smooth_value."""
    # garante que haverá problema
    monkeypatch.setattr(sim, "PROBLEM_PROBABILITY", 1.0, raising=False)

    # força tipo do problema = oxygen (mas não mexe no uniform global)
    monkeypatch.setattr(sim.random, "choice", lambda seq: "oxy")

    # patch direto da função de injeção para queda determinística de 30
    monkeypatch.setattr(sim, "inject_problem",
                        lambda values: values.__setitem__("oxygen", values["oxygen"] - 30.0))

    base = sim.generate_reading(tank_id=1, minute_of_day=0)
    after = sim.generate_reading(tank_id=1, minute_of_day=1)

    assert after["oxygen"] <= base["oxygen"] - 20.0



def test_perfis_independentes_e_estado_por_tanque():
    # gera leituras para tanques diferentes
    v1_t1 = sim.generate_reading(tank_id=1, minute_of_day=120)  # 02:00
    v1_t2 = sim.generate_reading(tank_id=2, minute_of_day=120)
    
    # os perfis têm bases diferentes -> temperaturas tendem a diferir
    assert abs(v1_t1["temperature"] - v1_t2["temperature"]) >= 0.2

    # segunda leitura mantém continuidade de cada tanque separadamente
    v2_t1 = sim.generate_reading(tank_id=1, minute_of_day=121)
    v2_t2 = sim.generate_reading(tank_id=2, minute_of_day=121)

    assert abs(v2_t1["temperature"] - v1_t1["temperature"]) < 3.0
    assert abs(v2_t2["temperature"] - v1_t2["temperature"]) < 3.0
