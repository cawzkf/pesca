import pytest
from src.infrastructure.sensors import sensor_simulator as sim

@pytest.fixture(autouse=True)
def reset_state():
    sim.STATE.clear()
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
    v1 = sim.generate_reading(tank_id=1, minute_of_day=0)
    v2 = sim.generate_reading(tank_id=1, minute_of_day=1)
    assert abs(v2["temperature"] - v1["temperature"]) < 3.0
    assert abs(v2["ph"] - v1["ph"]) < 0.8
    assert abs(v2["oxygen"] - v1["oxygen"]) < 20.0
    assert abs(v2["turbidity"] - v1["turbidity"]) < 40.0

def test_ciclo_diario_manha_mais_quente_que_tarde():
    v_morning = sim.generate_reading(tank_id=1, minute_of_day=6*60)
    v_evening = sim.generate_reading(tank_id=1, minute_of_day=18*60)
    assert v_morning["temperature"] >= v_evening["temperature"] - 0.5

def test_injecao_de_problema_forcada_oxy_baixo(monkeypatch):
    monkeypatch.setattr(sim, "PROBLEM_PROBABILITY", 1.0, raising=False)
    monkeypatch.setattr(sim.random, "choice", lambda seq: "oxy")
    # patch direto na função para não afetar o ruído do smooth_value
    monkeypatch.setattr(sim, "inject_problem",
                        lambda values: values.__setitem__("oxygen", values["oxygen"] - 30.0))
    base = sim.generate_reading(tank_id=1, minute_of_day=0)
    after = sim.generate_reading(tank_id=1, minute_of_day=1)
    assert after["oxygen"] <= base["oxygen"] - 20.0

def test_perfis_independentes_e_estado_por_tanque():
    v1_t1 = sim.generate_reading(tank_id=1, minute_of_day=120)
    v1_t2 = sim.generate_reading(tank_id=2, minute_of_day=120)
    assert abs(v1_t1["temperature"] - v1_t2["temperature"]) >= 0.2
    v2_t1 = sim.generate_reading(tank_id=1, minute_of_day=121)
    v2_t2 = sim.generate_reading(tank_id=2, minute_of_day=121)
    assert abs(v2_t1["temperature"] - v1_t1["temperature"]) < 3.0
    assert abs(v2_t2["temperature"] - v1_t2["temperature"]) < 3.0
