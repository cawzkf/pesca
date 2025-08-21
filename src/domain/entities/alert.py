from __future__ import annotations
from dataclasses import dataclass, replace
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from src.domain.enums import AlertType, Severity

@dataclass(frozen=True)
class Alert:
    id: str
    tank_id: int
    type: AlertType
    severity: Severity
    message: str
    created_at: datetime
    metadata: Optional[Dict[str, Any]] = None
    resolved_at: Optional[datetime] = None

    def __post_init__(self):
        tz = timezone.utc
        if self.created_at.tzinfo is None:
            object.__setattr__(self, "created_at", self.created_at.replace(tzinfo=tz))
        if self.resolved_at and self.resolved_at.tzinfo is None:
            object.__setattr__(self, "resolved_at", self.resolved_at.replace(tzinfo=tz))

    def resolve(self, when: Optional[datetime] = None) -> "Alert":
        return replace(self, resolved_at=(when or datetime.now(timezone.utc)))

    @property
    def duration(self) -> Optional[timedelta]:
        return None if not self.resolved_at else (self.resolved_at - self.created_at)

    # factories
    @staticmethod
    def water_quality(tank_id: int, metric: str, value: float,
                      severity: Severity, limits: dict, alert_id: str) -> "Alert":
        msg = f"{metric}={value} fora da faixa ótima ({limits.get('warn_low','-')}–{limits.get('warn_high','-')})"
        return Alert(alert_id, tank_id, AlertType.WATER_QUALITY, severity, msg,
                     datetime.now(timezone.utc),
                     metadata={"metric": metric, "value": value, "limits": limits})

    @staticmethod
    def overcrowd(tank_id: int, density_m3: float, max_per_m3: float, alert_id: str) -> "Alert":
        msg = f"Densidade {density_m3:.2f}/m³ > limite {max_per_m3:.2f}/m³"
        return Alert(alert_id, tank_id, AlertType.OVERCROWD, Severity.CRITICAL, msg,
                     datetime.now(timezone.utc),
                     metadata={"density_m3": density_m3, "max_per_m3": max_per_m3})
