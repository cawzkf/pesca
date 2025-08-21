# usado por enquanto para simulação e testes
# src/infrastructure/sensors/sensor_simulator.py
import sqlite3
import time
import random
import math
from datetime import datetime, timezone

from config.database import DATABASE_PATH
from src.infrastructure.database.migrations import run_migrations

# ===== Config =====
# Perfis por tanque (pode sobrescrever em runtime nos testes)
TANK_PROFILES = {
    1: {
        "temperature_base": 26.0, "temp_var": 2.0,
        "ph_base": 7.2,         "ph_var": 0.5,
        "oxygen_base": 85.0,    "oxy_var": 10.0,
        "turbidity_base": 25.0, "turb_var": 15.0,
    }
}

PROBLEM_PROBABILITY = 0.10   # 10% de leituras com problema
INTERVAL = 30                # segundos entre leituras
PROBLEM_COOLDOWN = 10 
STARTUP_GRACE_TICKS = 3 
STATE: dict[int, dict[str, float]] = {}  # estado por tanque (continuidade)

# ===== Helpers =====
def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

def smooth_value(prev: float, base: float, variation: float, cycle_rad: float) -> float:
    """
    Próximo valor: ruído leve + ciclo diário senoidal + retorno suave ao 'base'
    """
    # ciclo diário (seno entre -1 e +1)
    drift = math.sin(cycle_rad) * (variation * 0.5)
    # ruído leve local
    noise = random.uniform(-0.3, 0.3)
    # aproximação suave ao base
    pull = (base - prev) * 0.05
    return prev + noise + drift + pull

def inject_problem(values: dict[str, float]) -> None:
    """
    Injeção controlada de problemas realistas.
    """
    problem = random.choice(["temp", "ph", "oxy", "turb"])
    if problem == "temp":
        values["temperature"] += random.choice([-5.0, +5.0])
    elif problem == "ph":
        values["ph"] += random.choice([-1.5, +1.5])
    elif problem == "oxy":
        values["oxygen"] -= random.uniform(20.0, 40.0)
    elif problem == "turb":
        values["turbidity"] += random.uniform(50.0, 100.0)

def minute_of_day(dt: datetime) -> int:
    return dt.hour * 60 + dt.minute

# ===== Core =====
def ensure_tank(conn: sqlite3.Connection, tank_id: int) -> None:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM tanks WHERE id = ?", (tank_id,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO tanks (id, name, capacity, fish_count, ip_address, active) "
            "VALUES (?, ?, ?, ?, ?, 1)",
            (tank_id, f"Tanque {tank_id}", 2000.0, 100, f"192.168.0.{10 + tank_id}"),
        )
        conn.commit()

def generate_reading(tank_id: int, minute_of_day: int) -> dict[str, float]:
    profile = TANK_PROFILES[tank_id]
    prev = STATE.get(tank_id)

    if prev is None:
        prev = {
            "temperature": profile["temperature_base"],
            "ph":          profile["ph_base"],
            "oxygen":      profile["oxygen_base"],
            "turbidity":   profile["turbidity_base"],
            "_tick": -1,                   # <— meta
            "_last_problem_tick": -10,     # <— meta
        }

    tick = int(prev.get("_tick", -1)) + 1
    last_prob = int(prev.get("_last_problem_tick", -10))

    cycle = (minute_of_day / 1440.0) * 2.0 * math.pi

    new_values = {
        "temperature": smooth_value(prev["temperature"], profile["temperature_base"], profile["temp_var"], cycle),
        "ph":          smooth_value(prev["ph"],          profile["ph_base"],          profile["ph_var"],   cycle),
        "oxygen":      smooth_value(prev["oxygen"],      profile["oxygen_base"],      profile["oxy_var"],  cycle),
        "turbidity":   smooth_value(prev["turbidity"],   profile["turbidity_base"],   profile["turb_var"], cycle),
    }

    if new_values["ph"] > profile["ph_base"] + 0.5:
        new_values["oxygen"] -= 5.0

    # ---------- anomalias: grace inicial + cooldown + modo forçado ----------
    # "force" é usado nos testes quando PROBLEM_PROBABILITY ≈ 1.0
    force = PROBLEM_PROBABILITY >= 0.99
    can_force_now = (tick >= 1)  # pode forçar já no 2º passo
    can_normal = (tick >= STARTUP_GRACE_TICKS) and ((tick - last_prob) >= PROBLEM_COOLDOWN)

    if force:
        if can_force_now:
            inject_problem(new_values)
            last_prob = tick
    else:
        if can_normal and (random.random() < PROBLEM_PROBABILITY):
            inject_problem(new_values)
            last_prob = tick
    # -----------------------------------------------------------------------


    new_values["temperature"] = clamp(new_values["temperature"], 0.0, 50.0)
    new_values["ph"]          = clamp(new_values["ph"],          0.0, 14.0)
    new_values["oxygen"]      = clamp(new_values["oxygen"],      0.0, 100.0)
    new_values["turbidity"]   = clamp(new_values["turbidity"],   0.0, 200.0)

    # salva valores + meta
    STATE[tank_id] = {**new_values, "_tick": tick, "_last_problem_tick": last_prob}
    return new_values

def insert_reading(conn: sqlite3.Connection, tank_id: int, values: dict[str, float]) -> None:
    conn.execute(
        "INSERT INTO sensor_readings (tank_id, timestamp, temperature, ph, oxygen, turbidity) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (tank_id, _utc_iso(), values["temperature"], values["ph"], values["oxygen"], values["turbidity"]),
    )
    conn.commit()

# ===== Runner =====
def main() -> None:
    print(f"Usando banco: {DATABASE_PATH}")
    run_migrations()

    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")

        # garante todos os tanques configurados
        for tid in TANK_PROFILES.keys():
            ensure_tank(conn, tid)

        print(f"Simulador avançado rodando… tanks={list(TANK_PROFILES.keys())} (CTRL+C para parar)")
        while True:
            now = datetime.now(timezone.utc)
            mod = minute_of_day(now.astimezone())  # ciclo local
            for tid in TANK_PROFILES.keys():
                vals = generate_reading(tid, mod)
                insert_reading(conn, tid, vals)
                print(f"[{now.isoformat(timespec='seconds')}] tank={tid} -> {vals}")
            time.sleep(INTERVAL)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nEncerrado pelo usuário.")
