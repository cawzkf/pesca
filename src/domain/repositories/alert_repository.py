# src/domain/repositories/alert_repository.py
from __future__ import annotations
from typing import Protocol, Iterable
from datetime import datetime
from src.domain.enums import Severity

class IAlertRepository(Protocol):
    """
    Contrato de repositório para alertas.
    Implementações concretas (SQL, NoSQL, etc.) devem fornecer persistência
    e consulta de alertas em aberto por tanque.
    """

    def save(
        self,
        *,
        tank_id: int,
        alert_type: str,
        severity: Severity,
        description: str,
        value: float,
        threshold: float,
        timestamp: datetime,
    ) -> None:
        """
        Persiste um alerta com metadados completos.

        Args:
            tank_id: Identificador do tanque.
            alert_type: Tipo/categoria do alerta (ex.: "temperatura", "ph").
            severity: Nível de severidade (enum Severity).
            description: Texto curto explicando a condição.
            value: Valor que disparou o alerta.
            threshold: Limiar considerado para disparo.
            timestamp: Instante do evento (idealmente em UTC).

        Returns:
            None. Efeito colateral: gravação do alerta.
        """
        ...

    def list_open_by_tank(self, tank_id: int) -> Iterable[dict]:
        """
        Lista os alertas em aberto de um tanque.

        Args:
            tank_id: Identificador do tanque a consultar.

        Returns:
            Iterable[dict]: coleção iterável de dicionários representando
            os alertas abertos do tanque informado. O formato exato do dict
            depende da implementação, mas recomenda-se incluir id, type,
            severity, description, value, threshold, timestamp e status.
        """
        ...
