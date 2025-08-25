# run.py — Dashboard
# =============================================================================
# HOME: tanques em 2 colunas (cards)
# ALERTAS: gráfico de timeline de alertas (com hover e clique opcional)
# TANQUE: mostra o ÚLTIMO alerta + gráfico + plano de ração
# Datas/horas "DD/MM HH:MM"
# =============================================================================

from __future__ import annotations

import random
import sqlite3
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

from src.infrastructure.ai.genetic_feed_optimizer import recommend_feed_plan, GAConfig

# =============================================================================
# ROTAS / NAV INFERIOR
# =============================================================================
ROUTES = ("home", "tank", "settings", "alerts")
if "route" not in st.session_state:
    st.session_state.route = "home"

def navigate(to: str, **params):
    st.session_state.route = to
    for k, v in params.items():
        st.session_state[f"param_{k}"] = v
    st.rerun()

def bottom_nav(active: str):
    st.markdown("""
    <style>
    .bottom-nav{
      position:fixed;bottom:0;left:0;right:0;background:rgba(11,18,32,.95);
      backdrop-filter:blur(12px);border-top:1px solid rgba(34,211,238,.2);
      padding:8px 12px;z-index:9999;box-shadow:0 -8px 32px rgba(0,0,0,.3);height:56px;
    }
    .bottom-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;max-width:600px;margin:0 auto;}
    </style>
    """, unsafe_allow_html=True)

    current_tid = st.session_state.get("param_tank_id") or st.session_state.get("last_selected_tank_id")

    with st.container():
        st.markdown('<div class="bottom-nav"><div class="bottom-grid">', unsafe_allow_html=True)
        cols = st.columns(3)
        items = [("Tanques","home"),("Configurações","settings"),("Alertas","alerts")]
        for col,(label,route) in zip(cols, items):
            if col.button(label, key=f"bn_{route}", use_container_width=True):
                params = {}
                if route in ("tank", "alerts") and current_tid:
                    params["tank_id"] = int(current_tid)
                navigate(route, **params)
        st.markdown('</div></div>', unsafe_allow_html=True)

# =============================================================================
# IMPORTS DO PROJETO
# =============================================================================
from config.database import DATABASE_PATH
from config.settings import WATER_QUALITY_THRESHOLDS as WQT

from src.domain.entities.sensor_reading import SensorReading
from src.domain.entities.tank import Tank
from src.domain.enums import Severity

from src.domain.repositories.sensor_repository import ISensorRepository
from src.domain.repositories.alert_repository import IAlertRepository
from src.domain.repositories.tank_repository import ITankRepository
from src.domain.repositories.feed_repository import IFeedRecommendationRepository

from src.domain.use_cases.monitor_sensors_use_case import MonitorSensorsUseCase
from src.infrastructure.sensors.sensor_simulator import generate_reading, minute_of_day

# IA (Random Forest)
try:
    from src.infrastructure.ai.random_forest_model import train_and_save
    _HAS_RF = True
except Exception:
    _HAS_RF = False

# =============================================================================
# CSS BASE / LAYOUT
# =============================================================================
def load_base_css(ui_scale: float, alto_contraste: bool):
    base_font_px = int(15 * ui_scale)
    btn_height = int(42 * ui_scale)

    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    *{{font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif!important}}

    :root{{
      --ui-font:{base_font_px}px;
      --primary:#22d3ee; --primary2:#0891b2;
      --bg:#0b1220; --bg2:#0f172a; --bg3:#1e293b;
      --text:#e2e8f0; --sub:#cbd5e1; --muted:#64748b;
      --ok:#10b981; --warn:#f59e0b; --err:#ef4444;
      --border:rgba(226,232,240,.08);
      --nav-h:56px;
    }}

    /* Esconde header do Streamlit */
    [data-testid="stHeader"]{{display:none!important}}

    /* Viewport travado; só o miolo rola */
    html,body{{height:100vh!important;overflow:hidden!important;background:var(--bg)!important}}
    [data-testid="stAppViewContainer"]>.main{{
      padding-top:10px!important;
      padding-bottom:calc(var(--nav-h) + 12px)!important;
      height:100vh!important;box-sizing:border-box;
    }}
    .block-container{{
      padding:8px 10px!important;max-width:1100px!important;
      height:calc(100vh - var(--nav-h) - 16px)!important;
      display:flex!important;flex-direction:column;
    }}

    /* Wrappers por página */
    .page{{flex:1 1 auto;min-height:0;display:flex;flex-direction:column;gap:8px}}
    .page-header{{flex:0 0 auto}}
    .page-scroll{{flex:1 1 auto;min-height:0;overflow:auto;padding-bottom:8px}}

    .card{{
      background:linear-gradient(145deg,rgba(15,23,42,.85),rgba(30,41,59,.35));
      border:1px solid var(--border);border-radius:12px;padding:10px;
    }}

    .alerts-hscroll{{
      display:grid;grid-auto-flow:column;grid-auto-columns:minmax(360px, 1fr);
      gap:12px;overflow-x:auto;padding:6px 2px 10px;scroll-snap-type:x mandatory;
      -webkit-overflow-scrolling:touch;border-radius:12px;
    }}
    .alerts-hscroll .card{{ scroll-snap-align:start; min-height:120px; }}

    .clamp-2{{display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;overflow:hidden}}

    .metric-card{{background:linear-gradient(145deg,rgba(15,23,42,.85),rgba(30,41,59,.35));
      border:1px solid var(--border);border-radius:12px;padding:10px;min-height:84px;margin-bottom:4px}}
    .metric-title{{font-size:{int(11*ui_scale)}px;color:var(--sub);margin-bottom:4px;display:flex;gap:6px;align-items:center}}
    .metric-value{{font-size:{int(18*ui_scale)}px;font-weight:800;color:var(--text);line-height:1}}
    .metric-delta{{font-size:{int(10*ui_scale)}px;color:var(--sub)}}
    .metric-status{{font-size:{int(9*ui_scale)}px;color:var(--muted)}}
    .status-dot{{width:8px;height:8px;border-radius:50%;display:inline-block}}
    .status-normal{{background:var(--ok)}}.status-warning{{background:var(--warn)}}.status-critical{{background:var(--err)}}

    .tank-card{{background:linear-gradient(145deg,rgba(15,23,42,.85),rgba(30,41,59,.35));
      border:1px solid var(--border);border-radius:12px;padding:12px;cursor:pointer}}
    .tank-card:hover{{border-color:rgba(34,211,238,.35);box-shadow:0 0 0 1px rgba(34,211,238,.15) inset}}
    .tank-top{{display:flex;justify-content:space-between;align-items:center}}
    .tank-name{{font-weight:800;color:var(--text)}}
    .tank-meta{{font-size:.85rem;color:var(--sub)}}
    .mini-metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}}
    .mini{{background:rgba(2,6,23,.2);border:1px solid var(--border);border-radius:10px;padding:8px;text-align:center}}
    .mini .lbl{{font-size:.75rem;color:var(--muted)}}
    .mini .val{{font-weight:800;color:var(--text);line-height:1}}
    .mini .dot{{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:4px;vertical-align:middle}}

    .bottom-row{{display:grid;grid-template-columns:4fr 2fr;gap:10px;min-height:0}}
    .scroll-card{{overflow:auto;max-height:100%}}

    .ga-panel{{margin:6px 0 4px 0}}
    .ga-suggest{{background:rgba(2,6,23,.35);border:1px solid var(--border);border-radius:10px;padding:10px}}

    .js-plotly-plot .plotly .modebar{{opacity:0!important}}
    .stButton>button{{min-height:{btn_height}px!important;border-radius:10px!important;font-weight:600!important}}
    </style>
    """, unsafe_allow_html=True)

    # warm cache/model
    if "warm_done" not in st.session_state:
        st.session_state.warm_done = True
        try:
            ts = get_tanks()
            for t in ts:
                _ = get_latest_two_readings(t["id"])
        except Exception:
            pass

# =============================================================================
# SIDEBAR
# =============================================================================
st.sidebar.header("Controles")
ui_scale = st.sidebar.slider("Escala da UI (toque)", 0.9, 1.6, 1.20, 0.05)
alto_contraste = st.sidebar.toggle("Alto contraste", value=True)

if _HAS_RF and st.sidebar.button("Treinar/Atualizar modelo (RF)"):
    with st.spinner("Treinando modelo de crescimento (Random Forest)…"):
        info = train_and_save()
    st.success(f"Modelo treinado. R²={info['r2']:.3f}")
    st.cache_data.clear()

load_base_css(ui_scale, alto_contraste)

# =============================================================================
# HELPERS DE DATA/HORA
# =============================================================================

# === Normalizador de datas: converte para fuso local e remove tz ===
LOCAL_TZ = datetime.now().astimezone().tzinfo
_DEFAULT_DT_COLS = {"timestamp", "created_at", "resolved_at", "recommended_time"}

def normalize_datetime_cols(df: pd.DataFrame, cols: list[str] | None = None) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    # detecta colunas de data por nome, se não passar explicitamente
    cols = cols or [c for c in df.columns if c in _DEFAULT_DT_COLS or c.endswith(("_at", "_time", "_ts"))]
    for c in cols:
        if c in df.columns:
            s = pd.to_datetime(df[c], errors="coerce", utc=True)
            df[c] = s.dt.tz_convert(LOCAL_TZ).dt.tz_localize(None)
    return df

# ---- Labels PT-BR para exibir na UI ----
ALERT_PT = {
    "temperature": "Temperatura",
    "ph": "pH",
    "oxygen": "Oxigênio",
    "turbidity": "Turbidez",
}
SEVERITY_PT = {
    "NORMAL": "Normal",
    "WARNING": "Atenção",
    "CRITICAL": "Crítico",
}
STATUS_PT = {0: "Pendente", 1: "Resolvido"}

def pt_alert_label(alert_type: str) -> str:
    if alert_type is None: 
        return "—"
    return ALERT_PT.get(str(alert_type).lower(), str(alert_type))

def pt_severity_label(sev: str) -> str:
    if sev is None:
        return "—"
    return SEVERITY_PT.get(str(sev).upper(), str(sev))

def fmt_num(v, casas=2) -> str:
    """Formata número no padrão brasileiro (2 casas, vírgula decimal)."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    s = f"{x:,.{casas}f}"          # ex: 1,234.56
    s = s.replace(",", " ").replace(".", ",").replace(" ", ".")
    return s

def fmt_ts(ts) -> str:
    if ts is None:
        return "—"
    try:
        dt_utc = pd.to_datetime(ts, utc=True)
        py = dt_utc.to_pydatetime()
        if py.tzinfo is None:
            py = py.replace(tzinfo=timezone.utc)
        return py.astimezone().strftime("%d/%m %H:%M")
    except Exception:
        if isinstance(ts, datetime):
            py = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
            return py.astimezone().strftime("%d/%m %H:%M")
        return str(ts)

# =============================================================================
# DB HELPERS
# =============================================================================
def db() -> sqlite3.Connection:
    con = sqlite3.connect(DATABASE_PATH, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA temp_store=MEMORY;")
    con.execute("PRAGMA mmap_size=300000000;")
    con.execute("PRAGMA foreign_keys=ON;")
    return con

@st.cache_data(ttl=5)
def get_tanks() -> List[Dict[str, Any]]:
    with db() as con:
        cur = con.execute("""
            SELECT id, name, capacity, fish_count, ip_address, active,
                   COALESCE(peso_medio_g, 0.0) AS peso_medio_g
              FROM tanks
             WHERE active = 1
             ORDER BY id
        """)
        return [dict(r) for r in cur.fetchall()]

@st.cache_data(ttl=5)
def get_last_alert_any(tank_id: int) -> Dict[str, Any] | None:
    with db() as con:
        r = con.execute("""
            SELECT id, alert_type, severity, description, value, threshold,
                   created_at, IFNULL(resolved,0) AS resolved, resolved_at
              FROM alerts
             WHERE tank_id=?
             ORDER BY created_at DESC
             LIMIT 1
        """, (tank_id,)).fetchone()
    return dict(r) if r else None

@st.cache_data(ttl=5)
def get_latest_two_readings(tank_id: int) -> List[Dict[str, Any]]:
    with db() as con:
        cur = con.execute("""
            SELECT id, tank_id, timestamp, temperature, ph, oxygen, turbidity
              FROM sensor_readings
             WHERE tank_id=?
             ORDER BY timestamp DESC
             LIMIT 2
        """, (tank_id,))
        return [dict(r) for r in cur.fetchall()]

@st.cache_data(ttl=10)
def get_history(tank_id: int, limit: int = 300) -> pd.DataFrame:
    with db() as con:
        rows = con.execute("""
            SELECT timestamp, temperature, ph, oxygen, turbidity
              FROM sensor_readings
             WHERE tank_id=?
             ORDER BY timestamp DESC
             LIMIT ?
        """, (tank_id, limit)).fetchall()
    if not rows:
        return pd.DataFrame(columns=["timestamp","temperature","ph","oxygen","turbidity"])
    df = pd.DataFrame([dict(r) for r in rows])
    # 🔽 aqui: normaliza para fuso local e sem tz
    df = normalize_datetime_cols(df, ["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df

@st.cache_data(ttl=5)
def get_open_alerts(tank_id: int) -> List[Dict[str, Any]]:
    with db() as con:
        cur = con.execute("""
            SELECT id, alert_type, severity, description, value, threshold, created_at, resolved
              FROM alerts
             WHERE tank_id=? AND IFNULL(resolved,0) = 0
             ORDER BY created_at DESC
             LIMIT 100
        """, (tank_id,))
        return [dict(r) for r in cur.fetchall()]

def table_has_column(table: str, column: str) -> bool:
    with db() as con:
        cols = [r["name"] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]
    return column in cols

# =============================================================================
# REPOSITÓRIOS
# =============================================================================
class SQLiteSensorRepo(ISensorRepository):
    def add(self, reading: SensorReading) -> None:
        with db() as con:
            con.execute("""
                INSERT INTO sensor_readings (tank_id, timestamp, temperature, ph, oxygen, turbidity)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                reading.tank_id,
                reading.timestamp.astimezone(timezone.utc).isoformat(),
                reading.temperatura, reading.ph, reading.oxigenio, reading.turbidez
            ))

    def last_for_tank(self, tank_id: int) -> SensorReading | None:
        with db() as con:
            r = con.execute("""
                SELECT tank_id, timestamp, temperature, ph, oxygen, turbidity
                  FROM sensor_readings
                 WHERE tank_id=?
                 ORDER BY timestamp DESC LIMIT 1
            """, (tank_id,)).fetchone()
            if not r: return None
        ts = pd.to_datetime(r["timestamp"], utc=True).to_pydatetime()
        return SensorReading(
            tank_id=r["tank_id"], temperatura=r["temperature"], ph=r["ph"],
            oxigenio=r["oxygen"], turbidez=r["turbidity"], timestamp=ts,
        )

class SQLiteAlertRepo(IAlertRepository):
    def save(self, *, tank_id: int, alert_type: str, severity: Severity, description: str,
             value: float, threshold: float, timestamp: datetime) -> None:
        with db() as con:
            con.execute("""
                INSERT INTO alerts (tank_id, alert_type, severity, description, value, threshold, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (tank_id, alert_type, severity.name, description, value, threshold,
                  timestamp.astimezone(timezone.utc).isoformat()))

    def list_open_by_tank(self, tank_id: int):
        return get_open_alerts(tank_id)

    def resolve_open_by_type(self, tank_id: int, alert_type: str, when: datetime) -> None:
        with db() as con:
            con.execute("""
                UPDATE alerts
                   SET resolved = 1,
                       resolved_at = ?
                 WHERE tank_id = ?
                   AND alert_type = ?
                   AND IFNULL(resolved,0) = 0
            """, (when.astimezone(timezone.utc).isoformat(), tank_id, alert_type))

class SQLiteTankRepo(ITankRepository):
    def get(self, tank_id: int) -> Tank | None:
        with db() as con:
            r = con.execute("""
                SELECT id, name, capacity, fish_count, ip_address, active
                  FROM tanks
                 WHERE id=?
            """, (tank_id,)).fetchone()
            if not r: return None
        return Tank(
            id=r["id"], nome=r["name"], capacidade=r["capacity"],
            quantidade_peixes=r["fish_count"], ip_adress=r["ip_address"], ativo=bool(r["active"])
        )

class SQLiteFeedRepo(IFeedRecommendationRepository):
    def save(self, *, tank_id: int, grams_per_fish: float, total_grams: float,
             algorithm: str, recommended_time: datetime, notes: str = "") -> None:
        with db() as con:
            con.execute("""
                INSERT INTO feed_recommendations
                (tank_id, recommended_amount, recommended_time, fish_weight_estimate, water_conditions_score, algorithm_used, executed, notes)
                VALUES (?, ?, ?, NULL, NULL, ?, 0, ?)
            """, (tank_id, total_grams, recommended_time.astimezone(timezone.utc).isoformat(), algorithm, notes))

# =============================================================================
# REGRAS / UTIL
# =============================================================================
def reading_to_severity(r: SensorReading) -> Dict[str, Severity]:
    return dict(
        temp=r.status_temperatura(),
        ph=r.status_ph(),
        oxy=r.status_oxigenio(),
        turb=r.status_turbidez(),
        geral=r.status_geral_severity()
    )

def auto_resolve_sweep():
    """Fecha alertas antigos que já voltaram ao normal, com base na última leitura de cada tanque."""
    arepo = SQLiteAlertRepo()
    srepo = SQLiteSensorRepo()
    now_utc = datetime.now(timezone.utc)

    for t in get_tanks():
        tid = int(t["id"])
        last = srepo.last_for_tank(tid)
        if not last:
            continue
        sev = reading_to_severity(last)
        if sev["temp"] == Severity.NORMAL: arepo.resolve_open_by_type(tid, "temperature", now_utc)
        if sev["ph"]   == Severity.NORMAL: arepo.resolve_open_by_type(tid, "ph",          now_utc)
        if sev["oxy"]  == Severity.NORMAL: arepo.resolve_open_by_type(tid, "oxygen",      now_utc)
        if sev["turb"] == Severity.NORMAL: arepo.resolve_open_by_type(tid, "turbidity",   now_utc)


def simulate_and_process(tank_id: int) -> List[Dict[str, Any]]:
    now_local = datetime.now().astimezone()
    mod = minute_of_day(now_local)
    values = generate_reading(tank_id, mod)

    srepo, arepo = SQLiteSensorRepo(), SQLiteAlertRepo()
    uc = MonitorSensorsUseCase(sensor_repo=srepo, alert_repo=arepo)
    reading = SensorReading(
        tank_id=tank_id,
        temperatura=float(values["temperature"]),
        ph=float(values["ph"]),
        oxigenio=float(values["oxygen"]),
        turbidez=float(values["turbidity"]),
        timestamp=datetime.now(timezone.utc),
    )
    res = uc.execute(reading)

    # AUTO-RESOLVE: fecha alertas daquele tipo quando normalizar
    sev = reading_to_severity(reading)
    now_utc = datetime.now(timezone.utc)
    if sev["temp"]  == Severity.NORMAL:  arepo.resolve_open_by_type(tank_id, "temperature", now_utc)
    if sev["ph"]    == Severity.NORMAL:  arepo.resolve_open_by_type(tank_id, "ph",          now_utc)
    if sev["oxy"]   == Severity.NORMAL:  arepo.resolve_open_by_type(tank_id, "oxygen",      now_utc)
    if sev["turb"]  == Severity.NORMAL:  arepo.resolve_open_by_type(tank_id, "turbidity",   now_utc)

    return res.alerts

# =============================================================================
# HOME
# =============================================================================
def page_home():
    st.markdown('<div class="page">', unsafe_allow_html=True)

    # header
    st.markdown('<div class="page-header">', unsafe_allow_html=True)
    tanks = get_tanks()
    st.markdown(f"""
    <div class="card" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
      <h4 style="margin:0;">Tanques ativos</h4>
      <div style=color:var(--bg);padding:4px 12px;border-radius:12px;font-weight:700;">
                {len(tanks)}
      </div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)  # /page-header

    # scroll
    st.markdown('<div class="page-scroll">', unsafe_allow_html=True)

    if not tanks:
        st.info("Nenhum tanque ativo.")
        st.markdown('</div></div>', unsafe_allow_html=True)
        return

    cols = st.columns(2, gap="large")
    for idx, t in enumerate(tanks):
        col = cols[idx % 2]
        with col:
            tid = int(t["id"])
            latest2 = get_latest_two_readings(tid)
            ts_lbl = "—"
            if latest2:
                latest = latest2[0]
                r = SensorReading(
                    tank_id=tid,
                    temperatura=latest["temperature"], ph=latest["ph"],
                    oxigenio=latest["oxygen"], turbidez=latest["turbidity"],
                    timestamp=pd.to_datetime(latest["timestamp"], utc=True).to_pydatetime()
                )
                sev = reading_to_severity(r)
                dot = {"NORMAL":"var(--ok)","WARNING":"var(--warn)","CRITICAL":"var(--err)"}
                ts_lbl = r.timestamp.astimezone().strftime('%d/%m %H:%M')
                st.markdown(f"""
                <div class="tank-card" onclick="document.getElementById('btn_go_{tid}').click();">
                  <div class="tank-top">
                    <div>
                      <div class="tank-name">{t['name']}</div>
                      <div class="tank-meta">Peixes: {t.get('fish_count',0)} • Volume: {t.get('capacity',0):.0f} L</div>
                    </div>
                    <div class="tank-meta">{ts_lbl}</div>
                  </div>
                  <div class="mini-metrics" style="margin-top:6px;">
                    <div class="mini"><div class="lbl"><span class="dot" style="background:{dot[sev['temp'].name]};"></span>Temp</div><div class="val">{r.temperatura:.1f}°C</div></div>
                    <div class="mini"><div class="lbl"><span class="dot" style="background:{dot[sev['ph'].name]};"></span>pH</div><div class="val">{r.ph:.2f}</div></div>
                    <div class="mini"><div class="lbl"><span class="dot" style="background:{dot[sev['oxy'].name]};"></span>O₂</div><div class="val">{r.oxigenio:.1f}%</div></div>
                    <div class="mini"><div class="lbl"><span class="dot" style="background:{dot[sev['turb'].name]};"></span>Turb</div><div class="val">{r.turbidez:.1f} NTU</div></div>
                  </div>
                  <div class="tank-meta" style="margin-top:6px;">Status geral: {sev['geral'].name}</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="tank-card" onclick="document.getElementById('btn_go_{tid}').click();">
                  <div class="tank-top">
                    <div>
                      <div class="tank-name">{t['name']}</div>
                      <div class="tank-meta">Peixes: {t.get('fish_count',0)} • Volume: {t.get('capacity',0):.0f} L</div>
                    </div>
                    <div class="tank-meta">{ts_lbl}</div>
                  </div>
                  <div class="mini-metrics" style="margin-top:6px;">
                    <div class="mini"><div class="lbl">Temp</div><div class="val">—</div></div>
                    <div class="mini"><div class="lbl">pH</div><div class="val">—</div></div>
                    <div class="mini"><div class="lbl">O₂</div><div class="val">—</div></div>
                    <div class="mini"><div class="lbl">Turb</div><div class="val">—</div></div>
                  </div>
                  <div class="tank-meta" style="margin-top:6px;">Sem leituras</div>
                </div>
                """, unsafe_allow_html=True)

            if st.button("Abrir", key=f"btn_go_{tid}", use_container_width=True):
                navigate("tank", tank_id=tid)

    st.markdown('</div></div>', unsafe_allow_html=True)  # /page-scroll /page

# cache do plano de ração
@st.cache_data(ttl=120, show_spinner=False)
def cached_feed_plan(tid: int, fish_count: int, weight_kg: float, dens: float,
                     temp: float, ph: float, oxy: float, turb: float) -> Dict[str, Any]:
    return recommend_feed_plan(
        fish_count=fish_count, weight_kg=weight_kg, density=dens,
        temperature=temp, ph=ph, oxygen=oxy, turbidity=turb,
        use_ga=True, ga_cfg=GAConfig()
    )

# =============================================================================
# TANK
# =============================================================================
def page_tank(tid: int):
    st.markdown('<div class="page">', unsafe_allow_html=True)

    rows = get_latest_two_readings(tid)
    if not rows:
        st.info("Sem leituras ainda para este tanque. Clique em “Gerar nova leitura”.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    latest = rows[0]
    prev   = rows[1] if len(rows) > 1 else None

    r_latest = SensorReading(
        tank_id=tid,
        temperatura=latest["temperature"], ph=latest["ph"],
        oxigenio=latest["oxygen"], turbidez=latest["turbidity"],
        timestamp=pd.to_datetime(latest["timestamp"], utc=True).to_pydatetime()
    )
    sev = reading_to_severity(r_latest)

    # header (título + métricas)
    st.markdown('<div class="page-header">', unsafe_allow_html=True)
    st.subheader(f"Tanque {tid}")
    st.caption(f"Última leitura: {r_latest.timestamp.astimezone().strftime('%d/%m %H:%M')}")

    def _delta(cur: float, prev_value: float | None) -> str:
        if prev_value is None: return "—"
        d = cur - prev_value
        sign = "↑" if d > 0 else ("↓" if d < 0 else "→")
        return f"{sign} {d:+.2f}"

    def metric_card(title: str, value: str, delta_text: str, sev: Severity):
        status_class = f"status-{sev.name.lower()}"
        st.markdown(f"""
        <div class="metric-card">
          <div class="metric-title"><span class="status-dot {status_class}"></span>{title}</div>
          <div class="metric-value">{value}</div>
          <div class="metric-delta">{delta_text}</div>
          <div class="metric-status">Status: {sev.name}</div>
        </div>
        """, unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("Temperatura", f"{r_latest.temperatura:.1f} °C",
                    _delta(latest["temperature"], prev["temperature"] if prev else None), sev["temp"])
    with c2:
        metric_card("pH", f"{r_latest.ph:.2f}",
                    _delta(latest["ph"], prev["ph"] if prev else None), sev["ph"])
    with c3:
        metric_card("Oxigênio", f"{r_latest.oxigenio:.1f} %",
                    _delta(latest["oxygen"], prev["oxygen"] if prev else None), sev["oxy"])
    with c4:
        metric_card("Turbidez", f"{r_latest.turbidez:.1f} NTU",
                    _delta(latest["turbidity"], prev["turbidity"] if prev else None), sev["turb"])
    st.markdown('</div>', unsafe_allow_html=True)  # /page-header

    # scroll: gráfico + último alerta + GA
    st.markdown('<div class="page-scroll">', unsafe_allow_html=True)

    def _last_ts_for_tank(tid_: int) -> str | None:
        rows_ = get_latest_two_readings(tid_)
        return rows_[0]["timestamp"] if rows_ else None

    @st.cache_resource(show_spinner=False)
    def rf_get_model():
        try:
            from src.infrastructure.ai.random_forest_model import _ensure_model, FEATURES
            model, feats = _ensure_model()
            return model, feats
        except Exception:
            return None, None

    @st.cache_data(show_spinner=False)
    def compute_prod_pred_figure(tid_: int, dias_cultivo: int, last_ts: str,
                                 capacidade_l: float, fish_count: int, wqt: Dict[str, float],
                                 ui_scale_val: float):
        hist = get_history(tid_, limit=200)
        if hist.empty:
            return None, {"empty": True}

        m3 = max(0.001, float(capacidade_l)/1000.0)
        dens = float(fish_count)/m3

        rf_model, rf_feats = rf_get_model()

        def _pred_row(temp, ph, oxy, turb):
            if rf_model is not None and rf_feats is not None:
                payload = {
                    "temperatura": float(temp), "ph": float(ph), "oxigenio": float(oxy), "turbidez": float(turb),
                    "dias_cultivo": float(dias_cultivo), "densidade": float(dens),
                }
                arr = np.array([[payload[k] for k in rf_feats]], float)
                per_fish = float(rf_model.predict(arr)[0])
                return per_fish * fish_count

            cond = 1.0
            if not (wqt["temp_min"] <= temp <= wqt["temp_max"]): cond *= 0.85
            if not (wqt["ph_min"]   <= ph   <= wqt["ph_max"]):   cond *= 0.90
            if oxy < wqt["oxygen_min"]:                          cond *= 0.80
            if wqt.get("turbidez_max") and turb > wqt["turbidez_max"]: cond *= 0.92
            if dens > 60: cond *= 0.9
            x = float(np.clip(dias_cultivo, 0, 240))
            kg = 1.0/(1.0+np.exp(-(x-120)/20.0))
            return max(0.0, kg*cond)*fish_count

        hist = hist.copy()
        preds = [_pred_row(row.temperature, row.ph, row.oxygen, row.turbidity) for row in hist.itertuples(index=False)]
        hist["pred_total_kg"] = preds
        hist["real_total_kg"] = pd.Series(preds).ewm(alpha=0.35).mean()

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=hist['timestamp'], y=hist['real_total_kg'], mode='lines',
                                 name='Produção', line=dict(color='#22d3ee', width=2)))
        fig.add_trace(go.Scatter(x=hist['timestamp'], y=hist['pred_total_kg'], mode='lines',
                                 name='Predição', line=dict(color="#a676ff", width=2, dash='dot')))
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#cbd5e1', family='Inter'),
            xaxis=dict(gridcolor='rgba(34,211,238,.08)', linecolor='rgba(34,211,238,.2)', tickformat="%d/%m %H:%M"),
            yaxis=dict(gridcolor='rgba(34,211,238,.08)', linecolor='rgba(34,211,238,.2)', title="Peso total (kg)"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=6,r=6,t=6,b=6), height=int(260*ui_scale_val), hovermode="x unified"
        )
        return fig, {"empty": False, "points": len(hist)}

    last_ts = _last_ts_for_tank(tid)
    st.markdown('<div class="bottom-row">', unsafe_allow_html=True)
    left, right = st.columns([3,1])

    with left:
        if last_ts is None:
            st.info("Sem histórico suficiente para o gráfico.")
        else:
            tinfo = SQLiteTankRepo().get(tid)
            fig, meta = compute_prod_pred_figure(
                tid, st.session_state.get("dias_cultivo_val", 120), last_ts,
                float(tinfo.capacidade), int(tinfo.quantidade_peixes), WQT, ui_scale
            )
            if meta.get("empty"):
                st.info("Sem histórico suficiente para o gráfico.")
            else:
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with right:
        st.markdown("**Último alerta**")

        alerts_open = get_open_alerts(tid)
        last_any    = get_last_alert_any(tid) 

        color_map = {"NORMAL":"#10b981","WARNING":"#f59e0b","CRITICAL":"#ef4444"}

        def _alert_card(a: Dict[str,Any], status_badge: str, badge_bg: str, badge_bd: str, badge_fg: str):
            tipo_lbl = pt_alert_label(a["alert_type"]).upper()
            sev_lbl  = pt_severity_label(a["severity"])
            when_lbl = fmt_ts(a["created_at"])
            value_s  = fmt_num(a.get("value"))
            thr_s    = fmt_num(a.get("threshold"))
            st.markdown(f"""
            <div style="border-left:3px solid {color_map.get(a['severity'],'#64748b')}; padding-left:8px; margin:6px 0;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <div style="font-weight:700; color:#e2e8f0;">{tipo_lbl}</div>
                <span style="font-size:.75rem;background:{badge_bg};color:{badge_fg};
                            border:1px solid {badge_bd};padding:2px 8px;border-radius:999px;">
                {status_badge}
                </span>
            </div>
            <div style="color:#cbd5e1; font-size:.9rem; margin-top:4px;">{a.get('description','')}</div>
            <div style="color:#94a3b8; font-size:.8rem; margin-top:4px;">
                Disparou: {when_lbl} • Severidade: {sev_lbl}
                {"• Valor: " + value_s if a.get("value") is not None else ""}
            </div>
            </div>
            """, unsafe_allow_html=True)

        if alerts_open:
            a = alerts_open[0]
            _alert_card(a, "PENDENTE", "#3b1d06", "rgba(245,158,11,.3)", "#f59e0b")
        elif last_any:
            a = last_any
            # resolved_at opcional
            resolved_lbl = fmt_ts(a.get("resolved_at")) if a.get("resolved_at") else "—"
            # reaproveita o card e acrescenta info de resolução
            tipo_lbl = pt_alert_label(a["alert_type"]).upper()
            sev_lbl  = pt_severity_label(a["severity"])
            when_lbl = fmt_ts(a["created_at"])
            value_s  = fmt_num(a.get("value"))
            thr_s    = fmt_num(a.get("threshold"))
            st.markdown(f"""
            <div style="border-left:3px solid {color_map.get(a['severity'],'#64748b')}; padding-left:8px; margin:6px 0;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <div style="font-weight:700; color:#e2e8f0;">{tipo_lbl}</div>
                <span style="font-size:.75rem;background:#0b2a1f;color:#10b981;
                            border:1px solid rgba(16,185,129,.35);padding:2px 8px;border-radius:999px;">
                RESOLVIDO
                </span>
            </div>
            <div style="color:#cbd5e1; font-size:.9rem; margin-top:4px;">{a.get('description','')}</div>
            <div style="color:#94a3b8; font-size:.8rem; margin-top:4px;">
                Disparou: {when_lbl} • Resolvido: {resolved_lbl} • Severidade: {sev_lbl}
                {"• Valor: " + value_s if a.get("value") is not None else ""}
            </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("Nenhum alerta registrado ainda.")


    st.markdown('</div>', unsafe_allow_html=True)


    st.markdown('</div>', unsafe_allow_html=True)  # /bottom-row

    # Plano de ração
    tinfo = SQLiteTankRepo().get(tid)
    m3 = max(0.001, float(tinfo.capacidade)/1000.0)
    dens = float(tinfo.quantidade_peixes)/m3

    # peso médio (kg) por tanque, se existir no banco
    peso_medio_g = 0.0
    try:
        tanks_all = get_tanks()
        tm = next((t for t in tanks_all if int(t["id"]) == tid), None)
        if tm:
            peso_medio_g = float(tm.get("peso_medio_g", 0.0))
    except Exception:
        pass
    weight_kg = (peso_medio_g/1000.0) if peso_medio_g > 0 else 0.10

    plan = cached_feed_plan(
        tid, int(tinfo.quantidade_peixes), float(weight_kg), float(dens),
        float(r_latest.temperatura), float(r_latest.ph), float(r_latest.oxigenio), float(r_latest.turbidez)
    )

    st.markdown("**Otimização de ração (GA)**")
    st.caption(
        f"Densidade: {tinfo.quantidade_peixes:.0f} peixes/m³ • Peso médio: {weight_kg:.3f} kg/peixe • "
        f"FR base: {plan['base_feed_rate_percent']:.2f}% → Ajustada: {plan['adjusted_feed_rate_percent']:.2f}%"
    )
    st.success(f"**Ração sugerida:** {plan['grams_per_fish']:.2f} g/peixe · **Total:** {plan['total_grams']:.0f} g/dia")

    if plan["meals"]:
        st.markdown(
            f"- **Refeições:** {len(plan['meals'])}× de ~{plan['per_meal_grams_per_fish']:.2f} g/peixe "
            f"({int(plan['meals'][0]['total_grams']):.0f} g/meal total)\n\n"
            f"- **Próxima**: {plan['meals'][0]['time'].strftime('%d/%m %H:%M')} ({plan['meals'][0]['label']})\n\n"
            f"- {plan['notes']}"
        )

    st.markdown('</div>', unsafe_allow_html=True)  # /page-scroll
    st.markdown('</div>', unsafe_allow_html=True)  # /page

# =============================================================================
# SETTINGS
# =============================================================================
def page_settings():
    st.markdown('<div class="page">', unsafe_allow_html=True)
    st.markdown('<div class="page-header">', unsafe_allow_html=True)
    st.header("Configurações dos Tanques")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="page-scroll">', unsafe_allow_html=True)

    tanks = get_tanks()
    if not tanks:
        st.info("Nenhum tanque ativo.")
        st.markdown('</div></div>', unsafe_allow_html=True)
        return

    tank_names = {t["id"]: t["name"] for t in tanks}
    tank_ids   = [t["id"] for t in tanks]
    sel = st.selectbox("Tanque", options=tank_ids, format_func=lambda i: tank_names[i], index=0)

    t = next(t for t in tanks if t["id"] == sel)
    with st.form(key="form_tank_conf", clear_on_submit=False):
        q   = st.number_input("Quantidade de peixes", min_value=0,   value=int(t.get("fish_count", 0)))
        vol = st.number_input("Volume (L)",            min_value=0.0, value=float(t.get("capacity", 0.0)), step=10.0, format="%.1f")
        show_weight = table_has_column("tanks", "peso_medio_g")
        w_val = float(t.get("peso_medio_g", 0.0)) if show_weight else 0.0
        w   = st.number_input("Peso médio (g)", min_value=0.0, value=w_val, step=10.0, format="%.0f", disabled=not show_weight)
        ok = st.form_submit_button("Salvar")

    if ok:
        with db() as con:
            if show_weight:
                con.execute("""
                    UPDATE tanks
                       SET fish_count=?, capacity=?, peso_medio_g=?
                     WHERE id=?
                """, (q, vol, w, sel))
            else:
                con.execute("""
                    UPDATE tanks
                       SET fish_count=?, capacity=?
                     WHERE id=?
                """, (q, vol, sel))
            con.commit()
        st.success("Configurações salvas.")
        st.cache_data.clear()

    st.markdown('</div></div>', unsafe_allow_html=True)

# =============================================================================
# ALERTS (gráfico)
# =============================================================================
def page_alerts():
    st.markdown('<div class="page">', unsafe_allow_html=True)
    st.markdown('<div class="page-header">', unsafe_allow_html=True)
    st.header("Central de Alertas")

    # --- tanques + tanque seed (veio da tela Tank ou da sidebar) ---
    tanks = get_tanks()
    if not tanks:
        st.info("Nenhum tanque ativo.")
        st.markdown('</div></div>', unsafe_allow_html=True)
        return
    tank_map = {t["id"]: t["name"] for t in tanks}

    seeded_tid = st.session_state.get("param_tank_id") or st.session_state.get("last_selected_tank_id")
    seeded_tid = int(seeded_tid) if seeded_tid is not None else int(next(iter(tank_map.keys())))
    sel_ids = [seeded_tid]
    auto_resolve_sweep()
    st.cache_data.clear() 
    st.caption(f"Mostrando alertas de **{tank_map.get(seeded_tid, f'Tanque {seeded_tid}')}**.")

    # --- parâmetros fixos (sem UI) ---
    only_open   = False    # True => só pendentes
    bin_minutes = 15       # tamanho do bucket (min)
    limit       = 1200     # máximo de alertas carregados

    # --- área scroll ---
    st.markdown('<div class="page-scroll">', unsafe_allow_html=True)

    # --- consulta ao banco ---
    with db() as con:
        where, params = [], []
        if sel_ids:
            where.append("a.tank_id IN (" + ",".join("?"*len(sel_ids)) + ")")
            params += sel_ids
        if only_open:
            where.append("IFNULL(a.resolved,0)=0")
        where_sql = "WHERE " + " AND ".join(where) if where else ""
        q = f"""
        SELECT a.id, a.tank_id, a.alert_type, a.severity, a.description,
               a.value, a.threshold, a.created_at, IFNULL(a.resolved,0) AS resolved
          FROM alerts a
          {where_sql}
         ORDER BY a.created_at DESC
         LIMIT ?
        """
        rows = con.execute(q, params + [limit]).fetchall()

    if not rows:
        st.info("Sem eventos para os filtros atuais.")
        st.markdown('</div></div>', unsafe_allow_html=True)
        return

    # --- dataframe base ---
    df = pd.DataFrame([dict(r) for r in rows])
    local_tz = datetime.now().astimezone().tzinfo
    df["created_at"] = (
        pd.to_datetime(df["created_at"], utc=True, errors="coerce")
        .dt.tz_convert(local_tz)      # converte UTC -> fuso local
        .dt.tz_localize(None)         # remove o tz depois de converter
    )
    df["tanque"] = df["tank_id"].map(lambda i: tank_map.get(i, f"Tanque {i}"))
    df["status"] = np.where(df["resolved"] == 1, "Resolvido", "Pendente")
    # y = VALOR do alerta
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value"])

    # --- agrega por intervalo (média do valor; mantém contagem p/ hover) ---
    df["bin"] = df["created_at"].dt.floor(f"{bin_minutes}min")
    series = (
        df.groupby(["bin", "alert_type"]).agg(
            value_mean=("value", "mean"),
            count=("id", "count"),
            thr_mean=("threshold", "mean")
        ).reset_index().sort_values("bin")
    )

    # --- mesmo "look" do gráfico preditivo (linhas + hover unificado) ---
    fig = go.Figure()
    for typ in series["alert_type"].unique():
        dft = series[series["alert_type"] == typ]
        fig.add_trace(go.Scatter(
            x=dft["bin"], y=dft["value_mean"],
            mode="lines+markers",
            name=str(typ),
            line=dict(width=2),  # sem cor fixa → segue tema
            hovertemplate="<b>%{x|%d/%m %H:%M}</b>"
                          "<br>Tipo: " + str(typ) +
                          "<br>Média do valor: %{y:.2f}"
                          "<br>Alertas no intervalo: %{customdata[0]}"
                          "<br>Limite médio: %{customdata[1]:.2f}"
                          "<extra></extra>",
            customdata=np.stack([dft["count"].values, dft["thr_mean"].fillna(np.nan).values], axis=-1)
        ))

    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#cbd5e1', family='Inter'),
        xaxis=dict(
            title=None, tickformat="%d/%m %H:%M",
            gridcolor='rgba(34,211,238,.08)', linecolor='rgba(34,211,238,.2)'
        ),
        yaxis=dict(
            title="Valor do alerta (média por intervalo)",
            gridcolor='rgba(34,211,238,.08)', linecolor='rgba(34,211,238,.2)'
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=6, r=6, t=6, b=6),
        height=int(300*ui_scale),
        hovermode="x unified"
    )

    # --- clique opcional num ponto (sem duplicar render) ---
    clicked_bin = None
    _rendered = False
    try:
        from streamlit_plotly_events import plotly_events  # type: ignore
        pts = plotly_events(
            fig, click_event=True, hover_event=False, select_event=False,
            key="alerts_value_line"
        )
        _rendered = True
        if pts:
            clicked_bin = pd.to_datetime(pts[0].get("x")).floor(f"{bin_minutes}min")
    except Exception:
        pass

    if not _rendered:
        st.plotly_chart(
            fig, use_container_width=True, config={"displayModeBar": True},
            key="alerts_value_line"
        )

    # --- detalhes do intervalo clicado ---
    if clicked_bin is not None:
        win_start = clicked_bin
        win_end   = clicked_bin + pd.Timedelta(minutes=bin_minutes)
        sel = df[(df["created_at"] >= win_start) & (df["created_at"] < win_end)].copy()
        st.markdown("#### Alertas no intervalo selecionado")
        if sel.empty:
            st.info("Sem alertas nesse intervalo.")
        else:
            for _, r in sel.sort_values("created_at").iterrows():
                when = r["created_at"].strftime("%d/%m %H:%M")
                st.markdown(
                    f"""
                    <div class="card" style="margin-bottom:6px;">
                      <div style="display:flex;justify-content:space-between;">
                        <div><b>{r['tanque']}</b> — {r['alert_type']} — {r['severity']} ({r['status']})</div>
                        <div style="color:#94a3b8;">{when}</div>
                      </div>
                      <div style="color:#cbd5e1;margin-top:4px;">{r.get('description','')}</div>
                      <div style="color:#94a3b8;margin-top:4px;">
                        Valor: {r.get('value','—')} • Limite: {r.get('threshold','—')}
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

    # --- métricas rápidas ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total", len(df))
    c2.metric("Pendentes", int((df["status"] == "Pendente").sum()))
    c3.metric("WARNING", int((df["severity"] == "WARNING").sum()))
    c4.metric("CRITICAL", int((df["severity"] == "CRITICAL").sum()))

    st.markdown('</div></div>', unsafe_allow_html=True)  # /page-scroll /page

# =============================================================================
# SIDEBAR (controles globais) — precisa existir ANTES do dispatcher
# =============================================================================
tanks = get_tanks()
if not tanks:
    st.sidebar.error("Nenhum tanque ativo encontrado. Rode as migrations e/ou o simulador.")
    bottom_nav(st.session_state.route)
    st.stop()

tank_options = {f'#{t["id"]} — {t["name"]}': t["id"] for t in tanks}
tank_label = st.sidebar.selectbox("Selecionar tanque", list(tank_options.keys()))
sidebar_tank_id = tank_options[tank_label]
st.session_state["last_selected_tank_id"] = sidebar_tank_id  # usado pela página de Alertas

dias_cultivo = st.sidebar.slider("Dias de cultivo (IA / ração)", 10, 240, 120, 5)
st.session_state["dias_cultivo_val"] = dias_cultivo
debug_mode   = st.sidebar.toggle("Modo debug", value=False)

col_sim1, col_sim2 = st.sidebar.columns(2)
gen_btn     = col_sim1.button("Gerar nova leitura", use_container_width=True)
refresh_btn = col_sim2.button("Atualizar",           use_container_width=True)

auto = st.sidebar.toggle("Auto-refresh", value=False, help="Atualiza a cada N segundos")
if auto:
    secs = st.sidebar.slider("Intervalo (s)", 5, 60, 15)
    st.write(f"<meta http-equiv='refresh' content='{secs}'>", unsafe_allow_html=True)

st.sidebar.caption(
    f"Faixa ideal: Temp {WQT['temp_min']}–{WQT['temp_max']}°C · "
    f"pH {WQT['ph_min']}–{WQT['ph_max']} · O2 ≥{WQT['oxygen_min']}% · "
    f"Turbidez ≤{WQT.get('turbidez_max',50.0)} NTU"
)

if gen_btn:
    alerts_new = simulate_and_process(sidebar_tank_id)
    if alerts_new:
        for a in alerts_new:
            st.toast(f"[{a.alert_type}] {a.description}")
    else:
        st.toast("Leitura gerada.")
    st.cache_data.clear()
    st.rerun()
if refresh_btn:
    st.cache_data.clear()
    st.rerun()

# =============================================================================
# DISPATCHER
# =============================================================================
route = st.session_state.route
if route == "settings":
    page_settings();  bottom_nav(route); st.stop()
elif route == "alerts":
    page_alerts(); bottom_nav(route); st.stop()
elif route == "tank":
    tid = int(st.session_state.get("param_tank_id", sidebar_tank_id))
    page_tank(tid); bottom_nav(route); st.stop()
else:
    page_home(); bottom_nav(route); st.stop()
