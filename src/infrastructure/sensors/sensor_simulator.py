# Simulador contínuo de sensores (comportamento realista)
# Execução:
#   python -m src.infrastructure.sensors.sensor_simulator --all --interval 5 --problem-prob 0.15
# Mantém: generate_reading() e minute_of_day() para o front usar

from __future__ import annotations

import argparse
import math
import random
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from config.database import DATABASE_PATH
from src.infrastructure.database.migrations import run_migrations

# Use cases / entidades (para criar alertas de verdade)
from src.domain.entities.sensor_reading import SensorReading
from src.domain.use_cases.monitor_sensors_use_case import MonitorSensorsUseCase
from src.domain.enums import Severity

# =========================
# Perfis por tanque (1..4)
# =========================
TANK_PROFILES: Dict[int, Dict[str, float]] = {
    1: {"temperature_base": 26.0, "temp_var": 2.0,
        "ph_base": 7.2,          "ph_var": 0.35,
        "oxygen_base": 86.0,     "oxy_var": 10.0,
        "turbidity_base": 22.0,  "turb_var": 6.0},
    2: {"temperature_base": 27.0, "temp_var": 2.3,
        "ph_base": 7.0,          "ph_var": 0.30,
        "oxygen_base": 88.0,     "oxy_var": 9.0,
        "turbidity_base": 20.0,  "turb_var": 5.0},
    3: {"temperature_base": 25.5, "temp_var": 1.8,
        "ph_base": 7.3,          "ph_var": 0.40,
        "oxygen_base": 83.0,     "oxy_var": 11.0,
        "turbidity_base": 26.0,  "turb_var": 7.0},
    4: {"temperature_base": 26.5, "temp_var": 2.6,
        "ph_base": 6.9,          "ph_var": 0.45,
        "oxygen_base": 85.0,     "oxy_var": 12.0,
        "turbidity_base": 24.0,  "turb_var": 6.0},
}

def _ensure_profile(tid: int) -> Dict[str, float]:
    if tid not in TANK_PROFILES:
        offs = (tid % 4) * 0.3
        TANK_PROFILES[tid] = {
            "temperature_base": 26.0 + offs, "temp_var": 2.0 + offs/2,
            "ph_base": 7.1 + offs/10,        "ph_var": 0.35,
            "oxygen_base": 85.0 - offs,      "oxy_var": 10.0 + offs,
            "turbidity_base": 22.0 + offs,   "turb_var": 6.0,
        }
    return TANK_PROFILES[tid]

# =========================
# Parâmetros de simulação
# =========================
# Probabilidade de “spike” rápido de sensor (1 leitura ruim)
PROBLEM_PROBABILITY = 0.10
INTERVAL = 30                 # segundos entre leituras

# Eventos realistas (duração em minutos)
FEED_TIMES_MIN = [8*60, 12*60, 18*60]     # horários de arraçoamento (min do dia)
FEED_EVENT_MIN = 45                       # efeito típico pós-alimentação
AERATOR_FAIL_CHANCE_PER_HOUR = 0.08       # chance por hora de falha do aerador
AERATOR_FAIL_DURATION_MIN = (10, 40)      # duração de uma falha
WATER_RENEW_CHANCE_PER_DAY = 0.20         # chance/dia de troca parcial de água
WATER_RENEW_DURATION_MIN = (15, 30)

# Estado por tanque
STATE: Dict[int, Dict[str, float]] = {}

@dataclass
class Event:
    name: str
    remaining_ticks: int
    strength: float = 1.0         # 0..1

# eventos ativos por tanque
ACTIVE_EVENTS: Dict[int, List[Event]] = {}

# ===== Helpers =====
def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

def minute_of_day(dt: datetime) -> int:
    return dt.hour * 60 + dt.minute

def _ticks_for_minutes(minutes: float) -> int:
    # converte minutos para “ticks” do simulador
    tick_minutes = max(1, INTERVAL) / 60.0
    return max(1, int(round(minutes / tick_minutes)))

def _diurnal(min_of_day: int, peak_min: int) -> float:
    """
    Onda diária suave em [-1, 1], com pico em peak_min (min do dia).
    """
    # 1440 min no dia
    phase = 2.0 * math.pi * ((min_of_day - peak_min) % 1440) / 1440.0
    return math.sin(phase)

def _ensure_state(tid: int) -> Dict[str, float]:
    prof = _ensure_profile(tid)
    st = STATE.get(tid)
    if st is None:
        st = {
            "temperature": prof["temperature_base"],
            "ph":          prof["ph_base"],
            "oxygen":      prof["oxygen_base"],
            "turbidity":   prof["turbidity_base"],
            "_tick": 0,
            "bio_load": 0.10,             # carga orgânica acumulada (0..1+)
            "last_day_idx": -1,           # para sorteios diários
        }
        STATE[tid] = st
    if tid not in ACTIVE_EVENTS:
        ACTIVE_EVENTS[tid] = []
    return st

def _decay_events(tid: int):
    if tid not in ACTIVE_EVENTS:
        return
    new_list: List[Event] = []
    for ev in ACTIVE_EVENTS[tid]:
        ev.remaining_ticks -= 1
        if ev.remaining_ticks > 0:
            new_list.append(ev)
    ACTIVE_EVENTS[tid] = new_list

def _maybe_start_event_daily(tid: int, now_local: datetime):
    """
    Sorteia 1x por dia: troca de água.
    """
    st = _ensure_state(tid)
    day_idx = now_local.toordinal()
    if st["last_day_idx"] != day_idx:
        st["last_day_idx"] = day_idx
        if random.random() < WATER_RENEW_CHANCE_PER_DAY:
            dur = random.randint(*WATER_RENEW_DURATION_MIN)
            ACTIVE_EVENTS[tid].append(Event("water_renewal", _ticks_for_minutes(dur), strength=random.uniform(0.5, 1.0)))

def _maybe_start_event_per_tick(tid: int, now_local: datetime):
    """
    - Alimentação (nos horários definidos, com janela de ±5 min)
    - Falha do aerador (chance por hora)
    """
    # feeding window
    mod = minute_of_day(now_local)
    for feed_min in FEED_TIMES_MIN:
        if abs(mod - feed_min) <= 5:
            # evita iniciar várias vezes: só inicia se não existir evento "feeding"
            if not any(e.name == "feeding" for e in ACTIVE_EVENTS.get(tid, [])):
                ACTIVE_EVENTS[tid].append(Event("feeding", _ticks_for_minutes(FEED_EVENT_MIN), strength=1.0))

    # aerator failure — approx chance per hour
    chance_tick = AERATOR_FAIL_CHANCE_PER_HOUR * (INTERVAL / 3600.0)
    if random.random() < chance_tick:
        ACTIVE_EVENTS[tid].append(Event("aerator_failure", _ticks_for_minutes(random.randint(*AERATOR_FAIL_DURATION_MIN)),
                                        strength=random.uniform(0.6, 1.0)))

def _apply_events_effects(tid: int, values: Dict[str, float]) -> None:
    """
    Aplica efeitos de eventos ativos (com decaimento leve).
    """
    events = ACTIVE_EVENTS.get(tid, [])
    for ev in events:
        t = ev.remaining_ticks
        # decaimento linear 0..1 ao longo do evento
        # (quanto menor remaining, menor o impacto)
        decay = max(0.15, t / max(1.0, float(t + 4)))
        s = ev.strength * decay

        if ev.name == "feeding":
            # pós-alimentação: turbidez ↑, oxigênio ↓ leve, pH ↓ leve
            values["turbidity"] += 12.0 * s + random.uniform(0, 4.0)
            values["oxygen"]    -= 3.0 * s + random.uniform(0, 1.0)
            values["ph"]        -= 0.03 * s
        elif ev.name == "aerator_failure":
            # falha no aerador: O2 cai rápido, turbidez sobe um pouco
            values["oxygen"]    -= 25.0 * s + random.uniform(3, 7)
            values["turbidity"] += 3.0 * s + random.uniform(0, 2.0)
        elif ev.name == "water_renewal":
            # renovação parcial: turbidez ↓, temp ↓ leve, pH ↓ levemente (dep. da fonte)
            values["turbidity"] -= 10.0 * s
            values["temperature"] -= 0.4 * s
            values["ph"] -= 0.02 * s

def _update_bio_load(tid: int, now_local: datetime):
    """
    Carga orgânica acumula lentamente e é reduzida por 'water_renewal'.
    """
    st = _ensure_state(tid)
    # efeito de eventos de troca de água
    if any(e.name == "water_renewal" for e in ACTIVE_EVENTS.get(tid, [])):
        st["bio_load"] = max(0.0, st["bio_load"] - 0.015)  # reduz durante a renovação
    else:
        # acumula ~0.004 por hora
        st["bio_load"] = min(2.0, st["bio_load"] + 0.004 * (INTERVAL / 3600.0))

def _sensor_spike(values: Dict[str, float]):
    """
    Simula um 'spike' de leitura (1 única amostra esquisita).
    """
    problem = random.choice(["temperature", "ph", "oxygen", "turbidity"])
    if problem == "temperature":
        values["temperature"] += random.choice([-4.0, +4.0])
    elif problem == "ph":
        values["ph"] += random.choice([-1.2, +1.2])
    elif problem == "oxygen":
        values["oxygen"] -= random.uniform(15.0, 35.0)
    elif problem == "turbidity":
        values["turbidity"] += random.uniform(45.0, 90.0)

# ===== Infra repositórios mínimos (SQLite) para o Use Case =====
class SQLiteSensorRepo:
    def add(self, reading: SensorReading) -> None:
        with sqlite3.connect(DATABASE_PATH) as con:
            con.execute("""
                INSERT INTO sensor_readings (tank_id, timestamp, temperature, ph, oxygen, turbidity)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                reading.tank_id,
                reading.timestamp.astimezone(timezone.utc).isoformat(),
                reading.temperatura, reading.ph, reading.oxigenio, reading.turbidez
            ))

    def last_for_tank(self, tank_id: int) -> Optional[SensorReading]:
        with sqlite3.connect(DATABASE_PATH) as con:
            r = con.execute("""
                SELECT tank_id, timestamp, temperature, ph, oxygen, turbidity
                  FROM sensor_readings
                 WHERE tank_id=?
                 ORDER BY timestamp DESC LIMIT 1
            """, (tank_id,)).fetchone()
        if not r:
            return None
        ts = datetime.fromisoformat(r[1]).astimezone(timezone.utc)
        return SensorReading(tank_id=r[0], temperatura=r[2], ph=r[3], oxigenio=r[4], turbidez=r[5], timestamp=ts)

class SQLiteAlertRepo:
    def save(self, *, tank_id: int, alert_type: str, severity: Severity, description: str,
             value: float, threshold: float, timestamp: datetime) -> None:
        with sqlite3.connect(DATABASE_PATH) as con:
            con.execute("""
                INSERT INTO alerts (tank_id, alert_type, severity, description, value, threshold, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (tank_id, alert_type, severity.name, description, value, threshold,
                  timestamp.astimezone(timezone.utc).isoformat()))

# ===== Core (também usado pela dashboard) =====
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

def generate_reading(tank_id: int, minute_of_day_value: int) -> Dict[str, float]:
    """
    Gera uma leitura com:
      - ciclos diários (picos à tarde, vales ao amanhecer)
      - eventos com duração (alimentação, falha de aerador, renovação d'água)
      - carga orgânica acumulada
      - spikes ocasionais de sensor (controlados por PROBLEM_PROBABILITY)
    """
    prof = _ensure_profile(tank_id)
    st = _ensure_state(tank_id)
    now_local = datetime.now().astimezone()

    # 1) Decair eventos e talvez iniciar novos
    _decay_events(tank_id)
    _maybe_start_event_daily(tank_id, now_local)
    _maybe_start_event_per_tick(tank_id, now_local)
    _update_bio_load(tank_id, now_local)

    # 2) Targets com ciclo diário
    #    - temp pico ~15h; O2/pH também sobem de tarde (fotossíntese)
    cyc_temp = _diurnal(minute_of_day_value, peak_min=15*60)     # [-1..1]
    cyc_o2   = _diurnal(minute_of_day_value, peak_min=16*60)
    cyc_ph   = _diurnal(minute_of_day_value, peak_min=15*60)

    temp_target = prof["temperature_base"] + prof["temp_var"] * 0.7 * cyc_temp
    o2_target   = prof["oxygen_base"]     + prof["oxy_var"]  * 0.7 * cyc_o2
    ph_target   = prof["ph_base"]         + prof["ph_var"]    * 0.8 * cyc_ph
    turb_target = prof["turbidity_base"]  + prof["turb_var"]  * 0.5 * math.sin(2*math.pi*minute_of_day_value/1440.0)

    # 3) Efeito da carga orgânica
    bio = st["bio_load"]
    turb_target += 8.0 * bio
    o2_target   -= 3.0 * bio
    ph_target   -= 0.06 * bio

    # 4) Aproxima os valores ao target (dinâmica suave)
    def approach(prev: float, target: float, k: float, noise: float) -> float:
        return prev + k * (target - prev) + random.uniform(-noise, noise)

    new_values = {
        "temperature": approach(st["temperature"], temp_target, k=0.12, noise=0.15),
        "ph":          approach(st["ph"],          ph_target,   k=0.10, noise=0.03),
        "oxygen":      approach(st["oxygen"],      o2_target,   k=0.15, noise=1.2),
        "turbidity":   approach(st["turbidity"],   turb_target, k=0.18, noise=1.0),
    }

    # 5) Efeitos de eventos
    _apply_events_effects(tank_id, new_values)

    # 6) Acoplamentos fracos:
    #    temperatura ↑ → O2 ↓ levemente
    new_values["oxygen"] -= 0.35 * (new_values["temperature"] - prof["temperature_base"])
    #    pH↑ tende a reduzir levemente turbidez aparente (floculação em águas alcalinas)
    new_values["turbidity"] -= 0.6 * (new_values["ph"] - prof["ph_base"])

    # 7) Spikes ocasionais de sensor (uma amostra)
    if random.random() < PROBLEM_PROBABILITY * 0.05:
        _sensor_spike(new_values)

    # 8) Limites físicos
    new_values["temperature"] = clamp(new_values["temperature"], 0.0, 50.0)
    new_values["ph"]          = clamp(new_values["ph"],          4.0, 10.0)
    new_values["oxygen"]      = clamp(new_values["oxygen"],      0.0, 100.0)
    new_values["turbidity"]   = clamp(new_values["turbidity"],   0.0, 200.0)

    # 9) Persiste no estado para próxima iteração
    st.update({
        "temperature": new_values["temperature"],
        "ph":          new_values["ph"],
        "oxygen":      new_values["oxygen"],
        "turbidity":   new_values["turbidity"],
        "_tick": int(st["_tick"]) + 1,
    })
    return new_values

# ===== Runner CLI =====
def main() -> None:
    global PROBLEM_PROBABILITY, INTERVAL

    parser = argparse.ArgumentParser(description="Simulador contínuo de sensores (realista)")
    parser.add_argument("--all", action="store_true", help="Usar todos os tanques do perfil (1..4)")
    parser.add_argument("--tanks", nargs="*", type=int, help="IDs específicos: ex. --tanks 1 2 3 4")
    parser.add_argument("--interval", type=int, default=INTERVAL, help="Segundos entre leituras (default: 30)")
    parser.add_argument("--problem-prob", type=float, default=PROBLEM_PROBABILITY,
                        help="Probabilidade de spike rápido [0..1] (não confundir com eventos reais)")
    args = parser.parse_args()

    if args.all:
        tank_ids = sorted(set(TANK_PROFILES.keys()))
    elif args.tanks:
        tank_ids = sorted(set(args.tanks))
    else:
        tank_ids = [1, 2, 3, 4]

    PROBLEM_PROBABILITY = float(max(0.0, min(1.0, args.problem_prob)))
    INTERVAL = max(1, int(args.interval))

    print(f"DB: {DATABASE_PATH}")
    run_migrations()

    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        for tid in tank_ids:
            _ensure_profile(tid)
            ensure_tank(conn, tid)

    # Use case ligado aos repositórios SQLite (gera alertas)
    srepo = SQLiteSensorRepo()
    arepo = SQLiteAlertRepo()
    monitor = MonitorSensorsUseCase(sensor_repo=srepo, alert_repo=arepo)

    print(f"Simulador rodando | tanques={tank_ids} | intervalo={INTERVAL}s | spikes={PROBLEM_PROBABILITY:.0%}")
    try:
        while True:
            now = datetime.now(timezone.utc)
            mod = minute_of_day(now.astimezone())
            for tid in tank_ids:
                vals = generate_reading(tid, mod)
                reading = SensorReading(
                    tank_id=tid,
                    temperatura=float(vals["temperature"]),
                    ph=float(vals["ph"]),
                    oxigenio=float(vals["oxygen"]),
                    turbidez=float(vals["turbidity"]),
                    timestamp=now,
                )
                result = monitor.execute(reading)
                print(f"[{now.isoformat(timespec='seconds')}] tank={tid} -> "
                      f"T={vals['temperature']:.1f}°C pH={vals['ph']:.2f} O2={vals['oxygen']:.1f}% Turb={vals['turbidity']:.1f} | "
                      f"alerts={len(result.alerts)} | events={[e.name for e in ACTIVE_EVENTS.get(tid,[])]}")
            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        print("\nEncerrado pelo usuário.")

if __name__ == "__main__":
    main()
