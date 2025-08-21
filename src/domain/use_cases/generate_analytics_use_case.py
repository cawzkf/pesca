# src/domain/use_cases/generate_analytics_use_case.py
from __future__ import annotations
from dataclasses import dataclass
from statistics import mean
from typing import Dict, Any, Iterable
import logging

from src.domain.repositories.sensor_repository import ISensorRepository
from src.domain.repositories.alert_repository import IAlertRepository
from src.domain.entities.sensor_reading import SensorReading

log = logging.getLogger("pesca.usecases.analytics")

@dataclass(frozen=True)
class AnalyticsResult:
    summary: Dict[str, Any]

class GenerateAnalyticsUseCase:
    """
    Agrega métricas simples das últimas leituras + alertas abertos.
    """

    def __init__(self, sensor_repo: ISensorRepository, alert_repo: IAlertRepository) -> None:
        self.sensor_repo = sensor_repo
        self.alert_repo = alert_repo

    def execute(self, tank_id: int, last_n: int = 50) -> AnalyticsResult:
        readings: Iterable[SensorReading] = self.sensor_repo.list_for_tank(tank_id, last_n)
        readings = list(readings)

        def _avg(get): 
            vals = [get(r) for r in readings]
            return round(mean(vals), 2) if vals else None

        summary = {
            "count": len(readings),
            "avg_temperature": _avg(lambda r: r.temperatura),
            "avg_ph":          _avg(lambda r: r.ph),
            "avg_oxygen":      _avg(lambda r: r.oxigenio),
            "avg_turbidity":   _avg(lambda r: r.turbidez),
            "open_alerts":     len(list(self.alert_repo.list_open_by_tank(tank_id))),
        }
        log.info("analytics_generated tank=%s count=%s", tank_id, summary["count"])
        return AnalyticsResult(summary=summary)
