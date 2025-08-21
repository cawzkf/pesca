# tests/unit/test_use_cases.py
from __future__ import annotations
from typing import Iterable, Optional, List
from datetime import datetime, timezone

from src.domain.entities.sensor_reading import SensorReading
from src.domain.entities.tank import Tank
from src.domain.enums import Severity

from src.domain.repositories.sensor_repository import ISensorRepository
from src.domain.repositories.tank_repository import ITankRepository
from src.domain.repositories.alert_repository import IAlertRepository
from src.domain.repositories.feed_repository import IFeedRecommendationRepository

from src.domain.use_cases.monitor_sensors_use_case import MonitorSensorsUseCase
from src.domain.use_cases.optimize_feed_use_case import OptimizeFeedUseCase
from src.domain.use_cases.generate_analytics_use_case import GenerateAnalyticsUseCase

# ---------- Fakes em memória ----------

class FakeSensorRepo(ISensorRepository):
    def __init__(self) -> None:
        self.store: List[SensorReading] = []
    def add(self, reading: SensorReading) -> None:
        self.store.append(reading)
    def last_for_tank(self, tank_id: int) -> Optional[SensorReading]:
        items = [r for r in self.store if r.tank_id == tank_id]
        return items[-1] if items else None
    def list_for_tank(self, tank_id: int, limit: int = 100) -> Iterable[SensorReading]:
        return [r for r in self.store if r.tank_id == tank_id][-limit:]

class FakeTankRepo(ITankRepository):
    def __init__(self, tank: Tank) -> None:
        self.tank = tank
    def get(self, tank_id: int) -> Optional[Tank]:
        return self.tank if self.tank.id == tank_id else None

class FakeAlertRepo(IAlertRepository):
    def __init__(self) -> None:
        self.items: List[dict] = []
    def save(self, **alert) -> None:
        self.items.append(alert)
    def list_open_by_tank(self, tank_id: int):
        return [a for a in self.items if a["tank_id"] == tank_id]

class FakeFeedRepo(IFeedRecommendationRepository):
    def __init__(self) -> None:
        self.saved: List[dict] = []
    def save(self, **data) -> None:
        self.saved.append(data)

# ---------- Tests ----------

def test_monitor_generates_alert_when_oxygen_low():
    sensors = FakeSensorRepo()
    alerts = FakeAlertRepo()
    uc = MonitorSensorsUseCase(sensors, alerts)

    r = SensorReading(1, temperatura=26.0, ph=7.2, oxigenio=60.0, turbidez=20.0)
    res = uc.execute(r)

    assert sensors.last_for_tank(1) is not None
    assert any(a["alert_type"] == "oxygen" for a in res.alerts)
    assert alerts.items[0]["severity"] in (Severity.WARNING, Severity.CRITICAL)

def test_optimize_feed_with_weight_predictor_and_reduction():
    tank = Tank(id=1, nome="A", capacidade=2000.0, quantidade_peixes=60, ip_adress="x")
    tanks = FakeTankRepo(tank)
    sensors = FakeSensorRepo()
    sensors.add(SensorReading(1, 28.0, 7.2, 68.0, 15.0))  # WARNING por O2
    feed = FakeFeedRepo()

    # preditor fixo: 0.10 kg (100g)
    uc = OptimizeFeedUseCase(tanks, sensors, feed_repo=feed, weight_predictor=lambda p: 0.10)
    res = uc.execute(1, dias_cultivo=120)

    # 2% de 100g = 2g, reduz 10% por WARNING => 1.8g/peixe
    assert 1.7 <= res.grams_per_fish <= 1.9
    assert feed.saved, "deveria ter persistido a recomendação"

def test_generate_analytics_summary():
    sensors = FakeSensorRepo()
    alerts = FakeAlertRepo()

    for _ in range(3):
        sensors.add(SensorReading(1, 26.5, 7.1, 82.0, 18.0))
    alerts.save(tank_id=1, alert_type="oxygen", severity=Severity.WARNING,
                description="x", value=60.0, threshold=70.0, timestamp=datetime.now(timezone.utc))

    uc = GenerateAnalyticsUseCase(sensors, alerts)
    res = uc.execute(1, last_n=10)

    assert res.summary["count"] == 3
    assert res.summary["open_alerts"] == 1
    assert res.summary["avg_temperature"] is not None
