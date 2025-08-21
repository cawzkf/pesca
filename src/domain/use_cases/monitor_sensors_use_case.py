# o que o sistema pode fazer, comandos de uso 
# a dash chama esses uses cases quando algo, tipo um botão, é clicado 
# src/domain/use_cases/monitor_sensors_use_case.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Dict
import logging

from config.settings import WATER_QUALITY_THRESHOLDS as WQT
from src.domain.entities.sensor_reading import SensorReading
from src.domain.enums import Severity
from src.domain.repositories.sensor_repository import ISensorRepository
from src.domain.repositories.alert_repository import IAlertRepository

log = logging.getLogger("pesca.usecases.monitor")

@dataclass(frozen=True)
class MonitorSensorsResult:
    alerts: List[Dict]

class MonitorSensorsUseCase:
    """
    Salva a leitura, compara com limites ideais e gera alertas se necessário.
    Retorna a lista de alertas gerados (como dicts simples).
    """

    def __init__(self, sensor_repo: ISensorRepository, alert_repo: IAlertRepository) -> None:
        self.sensor_repo = sensor_repo
        self.alert_repo = alert_repo

    def execute(self, reading: SensorReading) -> MonitorSensorsResult:
        # 1) persistir
        self.sensor_repo.add(reading)
        log.info("reading_saved tank=%s ts=%s", reading.tank_id, reading.timestamp.isoformat())

        alerts: List[Dict] = []
        ts = datetime.now(timezone.utc)

        checks = [
            ("temperature", reading.temperatura, (WQT["temp_min"], WQT["temp_max"])),
            ("ph",          reading.ph,          (WQT["ph_min"],  WQT["ph_max"])),
            ("oxygen",      reading.oxigenio,    (WQT["oxygen_min"], float("inf"))),
            ("turbidity",   reading.turbidez,    (0.0, WQT.get("turbidez_max", 50.0))),
        ]

        for key, value, (lo, hi) in checks:
            sev = self._severity_for(key, value, lo, hi)
            if sev is Severity.NORMAL:
                continue

            desc = self._build_description(key, value, lo, hi, sev)
            threshold = hi if key in ("temperature", "ph") and value > hi else lo
            if key == "oxygen":
                threshold = WQT["oxygen_min"]
            if key == "turbidity":
                threshold = WQT.get("turbidez_max", 50.0)

            alert = dict(
                tank_id=reading.tank_id,
                alert_type=key,
                severity=sev,
                description=desc,
                value=float(value),
                threshold=float(threshold),
                timestamp=ts,
            )
            self.alert_repo.save(**alert)
            alerts.append(alert)
            log.warning("alert_generated tank=%s type=%s sev=%s value=%.3f thr=%.3f",
                        reading.tank_id, key, sev.name, value, threshold)

        return MonitorSensorsResult(alerts=alerts)

    @staticmethod
    def _severity_for(key: str, v: float, lo: float, hi: float) -> Severity:
        # usa as regras do SensorReading para ser consistente
        # fallback: checagem simples
        if key == "temperature":
            return SensorReading(0, v, 7.0, 80.0, 10.0).status_temperatura()
        if key == "ph":
            return SensorReading(0, 26.0, v, 80.0, 10.0).status_ph()
        if key == "oxygen":
            return SensorReading(0, 26.0, 7.0, v, 10.0).status_oxigenio()
        if key == "turbidity":
            return SensorReading(0, 26.0, 7.0, 80.0, v).status_turbidez()

        # fallback
        if v < lo or v > hi:
            return Severity.CRITICAL
        return Severity.NORMAL

    @staticmethod
    def _build_description(key: str, value: float, lo: float, hi: float, sev: Severity) -> str:
        if key == "oxygen":
            return f"Nível de oxigênio abaixo do mínimo ({value:.1f}% < {WQT['oxygen_min']}%). Severidade: {sev.name}"
        if key == "turbidity":
            return f"Turbidez acima do limite ({value:.1f} NTU > {WQT.get('turbidez_max',50.0)}). Severidade: {sev.name}"
        if key == "temperature":
            return f"Temperatura fora da faixa ideal ({lo}-{hi} °C). Medida: {value:.1f} °C. Severidade: {sev.name}"
        if key == "ph":
            return f"pH fora da faixa ideal ({lo}-{hi}). Medida: {value:.2f}. Severidade: {sev.name}"
        return f"{key} fora do ideal. Severidade: {sev.name}"
