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
    """
    DTO imutável para retorno do caso de uso.

    Atributos:
        summary: dicionário com agregações calculadas. Espera-se as chaves:
            - 'count': int
            - 'avg_temperature': float | None
            - 'avg_ph': float | None
            - 'avg_oxygen': float | None
            - 'avg_turbidity': float | None
            - 'open_alerts': int
    """
    summary: Dict[str, Any]

class GenerateAnalyticsUseCase:
    """
    Agrega métricas simples das últimas leituras + alertas abertos.
    """

    def __init__(self, sensor_repo: ISensorRepository, alert_repo: IAlertRepository) -> None:
        """
        Injeta dependências de leitura de sensores e de alertas.

        Args:
            sensor_repo: Repositório de leituras (fonte de SensorReading).
            alert_repo: Repositório de alertas (fonte de alertas em aberto).
        """
        self.sensor_repo = sensor_repo
        self.alert_repo = alert_repo

    def execute(self, tank_id: int, last_n: int = 50) -> AnalyticsResult:
        """
        Executa a agregação para um tanque.

        Args:
            tank_id: Identificador do tanque alvo.
            last_n: Quantidade de leituras recentes a considerar (default=50).

        Returns:
            AnalyticsResult: objeto com o dicionário 'summary' contendo
            contagem, médias por métrica e número de alertas abertos.
        """
        # Obtém as últimas leituras do tanque e materializa para lista
        readings: Iterable[SensorReading] = self.sensor_repo.list_for_tank(tank_id, last_n)
        readings = list(readings)

        # Função auxiliar para calcular média de um atributo extraído por 'get'.
        # Retorna None se não houver valores (evita ZeroDivisionError).
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
        # Log informativo para auditoria/observabilidade
        log.info("analytics_generated tank=%s count=%s", tank_id, summary["count"])
        return AnalyticsResult(summary=summary)
