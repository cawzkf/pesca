# src/domain/use_cases/monitor_sensors_use_case.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Dict, Tuple
import logging

from config.settings import WATER_QUALITY_THRESHOLDS as WQT
from src.domain.entities.sensor_reading import SensorReading
from src.domain.enums import Severity
from src.domain.repositories.sensor_repository import ISensorRepository
from src.domain.repositories.alert_repository import IAlertRepository

log = logging.getLogger("pesca.usecases.monitor")

@dataclass(frozen=True)
class MonitorSensorsResult:
    """
    DTO imutável retornado pelo caso de uso.

    Atributos:
        alerts: lista de dicionários representando os alertas
                gerados nesta execução (pode ser vazia).
    """
    alerts: List[Dict]

class MonitorSensorsUseCase:
    """
    Persiste a leitura e gera alertas SOMENTE quando houver mudança de severidade
    (ex.: NORMAL→WARNING, WARNING→CRITICAL, CRITICAL→WARNING). Isso evita alertas
    duplicados a cada leitura quando o parâmetro já está fora da faixa.
    """

    def __init__(self, sensor_repo: ISensorRepository, alert_repo: IAlertRepository) -> None:
        """
        Injeta repositórios do domínio.

        Args:
            sensor_repo: fonte de histórico/persistência de leituras.
            alert_repo: persistência/consulta de alertas.
        """
        self.sensor_repo = sensor_repo
        self.alert_repo = alert_repo

    def execute(self, reading: SensorReading) -> MonitorSensorsResult:
        """
        Executa o monitoramento para uma leitura.

        Fluxo:
            0) Lê a última leitura do tanque (antes de salvar a atual)
            1) Persiste a leitura atual
            2) Calcula severidades por métrica (atual e anterior)
            3) Para cada métrica, dispara alerta se houve mudança de severidade
               (ou se é a primeira leitura já fora de NORMAL)

        Args:
            reading: Leitura atual validada pelo domínio.

        Returns:
            MonitorSensorsResult: contendo a lista de alertas gerados.
        """
        # 0) pega a leitura anterior ANTES de salvar a atual
        prev = self.sensor_repo.last_for_tank(reading.tank_id)

        # 1) persistir leitura atual
        self.sensor_repo.add(reading)
        log.info("reading_saved tank=%s ts=%s", reading.tank_id, reading.timestamp.isoformat())

        # 2) severidades por parâmetro
        cur_sev = self._sev_map(reading)
        prev_sev = self._sev_map(prev) if prev else None

        # 3) dispara alertas quando muda a severidade (ou na 1ª leitura já fora da faixa)
        alerts: List[Dict] = []
        ts = datetime.now(timezone.utc)

        for key, value, lo, hi in self._checks(reading):
            cur = cur_sev[key]
            # Sem histórico: assume NORMAL para comparação
            prv = prev_sev[key] if prev_sev else Severity.NORMAL  # sem histórico = assume NORMAL

            if cur is Severity.NORMAL:
                # Voltou/está em NORMAL → não abre alerta.
                # (Opcional: implementação futura de "recovery" no repo.)
                continue

            if prv != cur:
                # Houve transição de severidade → gera alerta
                desc = self._build_description(key, value, lo, hi, cur)
                thr = self._threshold_for(key, value, lo, hi)
                alert = dict(
                    tank_id=reading.tank_id,
                    alert_type=key,            # mantém nomes: temperature/ph/oxygen/turbidity
                    severity=cur,
                    description=desc,
                    value=float(value),
                    threshold=float(thr),
                    timestamp=ts,
                )
                self.alert_repo.save(**alert)
                alerts.append(alert)
                log.warning("alert_generated tank=%s type=%s from=%s to=%s value=%.3f thr=%.3f",
                            reading.tank_id, key, prv.name, cur.name, value, thr)

        return MonitorSensorsResult(alerts=alerts)

    # ---------- helpers ----------
    @staticmethod
    def _sev_map(r: SensorReading) -> Dict[str, Severity]:
        """
        Mapeia uma leitura para o status por métrica.

        Returns:
            dict com chaves: temperature, ph, oxygen, turbidity.
        """
        return dict(
            temperature=r.status_temperatura(),
            ph=r.status_ph(),
            oxygen=r.status_oxigenio(),
            turbidity=r.status_turbidez(),
        )

    @staticmethod
    def _checks(r: SensorReading) -> List[Tuple[str, float, float, float]]:
        """
        Produz a lista de checagens (métrica, valor, limite inferior, limite superior).

        Notas:
            - oxygen usa apenas limite inferior (min); 'hi' é infinito.
            - turbidity usa limite superior (max); 'lo' é 0.
        """
        return [
            ("temperature", r.temperatura, WQT["temp_min"], WQT["temp_max"]),
            ("ph",          r.ph,          WQT["ph_min"],  WQT["ph_max"]),
            ("oxygen",      r.oxigenio,    WQT["oxygen_min"], float("inf")),
            ("turbidity",   r.turbidez,    0.0, WQT.get("turbidez_max", 50.0)),
        ]

    @staticmethod
    def _threshold_for(key: str, value: float, lo: float, hi: float) -> float:
        """
        Determina o limiar a ser registrado no alerta para a métrica informada.
        """
        if key == "oxygen":
            return WQT["oxygen_min"]
        if key == "turbidity":
            return WQT.get("turbidez_max", 50.0)
        # temperature/ph: se estourou em cima usa hi; se embaixo usa lo
        return hi if value > hi else lo

    @staticmethod
    def _build_description(key: str, value: float, lo: float, hi: float, sev: Severity) -> str:
        """
        Gera a mensagem textual do alerta, contextualizando valor medido e faixa/limite.
        """
        if key == "oxygen":
            return f"Nível de oxigênio abaixo do mínimo ({value:.1f}% < {WQT['oxygen_min']}%). Severidade: {sev.name}"
        if key == "turbidity":
            return f"Turbidez acima do limite ({value:.1f} NTU > {WQT.get('turbidez_max',50.0)}). Severidade: {sev.name}"
        if key == "temperature":
            return f"Temperatura fora da faixa ideal ({lo}-{hi} °C). Medida: {value:.1f} °C. Severidade: {sev.name}"
        if key == "ph":
            return f"pH fora da faixa ideal ({lo}-{hi}). Medida: {value:.2f}. Severidade: {sev.name}"
        return f"{key} fora do ideal. Severidade: {sev.name}"
