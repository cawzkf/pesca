import sqlite3, time, random, math
from datetime import datetime, timezone
from config.database import DATABASE_PATH
from src.infrastructure.database.migrations import run_migrations

# Configuração por tanque (pode expandir depois com mais perfis)
TANK_PROFILES = {
    1: {
        "temperature_base": 26.0, "temp_var": 2.0,
        "ph_base": 7.2, "ph_var": 0.5,
        "oxygen_base": 85.0, "oxy_var": 10.0,
        "turbidity_base": 25.0, "turb_var": 15.0,
    }
}

PROBLEM_PROBABILITY = 0.1   # 10% leituras problemáticas
INTERVAL = 30               # segundos entre leituras
STATE = {}                  # estado persistente por tanque

def ensure_tank(conn, tank_id: int):
    cur = conn.cursor()
    cur.execute("SELECT id FROM tanks WHERE id=?", (tank_id,))
    if not cur.fetchone():
        cur.execute("INSERT INTO tanks (id, name, capacity, fish_count, ip_address, active) VALUES (?,?,?,?,?,1)",
                    (tank_id, f"Tanque {tank_id}", 2000.0, 100, f"192.168.0.{10+tank_id}"))
        conn.commit()

def smooth_value(prev: float, base: float, variation: float, cycle: float) -> float:
    """gera próximo valor baseado no anterior + ciclo diário + ruído leve"""
    drift = math.sin(cycle) * variation * 0.5
    new_val = prev + random.uniform(-0.3, 0.3) + drift
    # força retorno gradual ao valor base
    return prev + (base - prev) * 0.05 + (new_val - prev) * 0.95

def inject_problem(values: dict):
    """Altera um dos parâmetros para simular problema"""
    problem_type = random.choice(["temp", "ph", "oxy", "turb"])
    if problem_type == "temp":
        values["temperature"] += random.choice([-5, +5])
    elif problem_type == "ph":
        values["ph"] += random.choice([-1.5, +1.5])
    elif problem_type == "oxy":
        values["oxygen"] -= random.uniform(20, 40)
    elif problem_type == "turb":
        values["turbidity"] += random.uniform(50, 100)

def generate_reading(tank_id: int, minute_of_day: int) -> dict:
    profile = TANK_PROFILES[tank_id]
    prev = STATE.get(tank_id)

    cycle = (minute_of_day / 1440.0) * 2 * math.pi  # ciclo diário

    if not prev:
        # inicializa com os valores base
        prev = {
            "temperature": profile["temperature_base"],
            "ph": profile["ph_base"],
            "oxygen": profile["oxygen_base"],
            "turbidity": profile["turbidity_base"],
        }

    new_values = {
        "temperature": smooth_value(prev["temperature"], profile["temperature_base"], profile["temp_var"], cycle),
        "ph": smooth_value(prev["ph"], profile["ph_base"], profile["ph_var"], cycle),
        "oxygen": smooth_value(prev["oxygen"], profile["oxygen_base"], profile["oxy_var"], cycle),
        "turbidity": smooth_value(prev["turbidity"], profile["turbidity_base"], profile["turb_var"], cycle),
    }

    # correlação: pH alto tende a baixar oxigênio
    if new_values["ph"] > profile["ph_base"] + 0.5:
        new_values["oxygen"] -= 5

    # 10% chance de problema
    if random.random() < PROBLEM_PROBABILITY:
        inject_problem(new_values)

    STATE[tank_id] = new_values
    return new_values

def insert_reading(conn, tank_id: int, values: dict):
    ts = datetime.now(timezone.utc).isoformat()
    conn.execute("""INSERT INTO sensor_readings
        (tank_id, timestamp, temperature, ph, oxygen, turbidity)
        VALUES (?,?,?,?,?,?)""",
        (tank_id, ts, values["temperature"], values["ph"], values["oxygen"], values["turbidity"]))
    conn.commit()

if __name__ == "__main__":
    with sqlite3.connect(DATABASE_PATH) as conn:
        run_migrations()
        for tank_id in TANK_PROFILES:
            ensure_tank(conn, tank_id)

        print(f"Simulador avançado rodando… tanks={list(TANK_PROFILES.keys())} (CTRL+C para parar)")
        while True:
            now = datetime.now()
            minute_of_day = now.hour * 60 + now.minute
            for tank_id in TANK_PROFILES:
                values = generate_reading(tank_id, minute_of_day)
                insert_reading(conn, tank_id, values)
                print(f"[{now.strftime('%H:%M:%S')}] Tank {tank_id}: {values}")
            time.sleep(INTERVAL)
