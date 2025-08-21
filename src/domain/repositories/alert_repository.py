# src/domain/repositories/alert_repository.py
from __future__ import annotations
from typing import Protocol, Iterable
from datetime import datetime
from src.domain.enums import Severity

class IAlertRepository(Protocol):
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
    ) -> None: ...

    def list_open_by_tank(self, tank_id: int) -> Iterable[dict]: ...
