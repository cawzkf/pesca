from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, ClassVar
from config.settings import WATER_QUALITY_THRESHOLDS
from src.domain.enums import Severity  


@dataclass(frozen=True)
class SensorReading:
    """
    Entidade imutável representando uma leitura de qualidade da água.
    - Valida limites duros (hard limits) no __post_init__
    - Fornece status por métrica e status agregado
    - Usa WATER_QUALITY_THRESHOLDS para faixas ótimas/alerta
    """
    tank_id: int
    temperatura: float      
    ph: float              
    oxigenio: float        
    turbidez: float        
    timestamp: datetime | None = None

    # ---------- LIMITES DUROS (como constantes de classe) ----------
    _TEMP_MIN_HARD: ClassVar[float] = 0.0
    _TEMP_MAX_HARD: ClassVar[float] = 50.0
    _PH_MIN_HARD:   ClassVar[float] = 0.0
    _PH_MAX_HARD:   ClassVar[float] = 14.0
    _OXY_MIN_HARD:  ClassVar[float] = 0.0
    _OXY_MAX_HARD:  ClassVar[float] = 100.0 
    _TURB_MIN_HARD: ClassVar[float] = 0.0
    _TURB_MAX_HARD: ClassVar[float] = 200.0

    def __post_init__(self):
        # timestamp em UTC
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", datetime.now(timezone.utc))
        elif self.timestamp.tzinfo is None:
            object.__setattr__(self, "timestamp", self.timestamp.replace(tzinfo=timezone.utc))

        # validações de limites duros
        if not (self._TEMP_MIN_HARD <= self.temperatura <= self._TEMP_MAX_HARD):
            raise ValueError(f"Temperatura inválida: {self.temperatura}°C. Range: {self._TEMP_MIN_HARD}-{self._TEMP_MAX_HARD}°C")
        if not (self._PH_MIN_HARD <= self.ph <= self._PH_MAX_HARD):
            raise ValueError(f"pH inválido: {self.ph}. Range: {self._PH_MIN_HARD}-{self._PH_MAX_HARD}")
        if not (self._OXY_MIN_HARD <= self.oxigenio <= self._OXY_MAX_HARD):
            raise ValueError(f"Oxigênio inválido: {self.oxigenio}. Range: {self._OXY_MIN_HARD}-{self._OXY_MAX_HARD}")
        if not (self._TURB_MIN_HARD <= self.turbidez <= self._TURB_MAX_HARD):
            raise ValueError(f"Turbidez inválida: {self.turbidez}. Range: {self._TURB_MIN_HARD}-{self._TURB_MAX_HARD}")

    # ---------- Threshold ----------
    @property
    def _tmin(self) -> float:  return float(WATER_QUALITY_THRESHOLDS.get("temp_min", 24.0))
    @property
    def _tmax(self) -> float:  return float(WATER_QUALITY_THRESHOLDS.get("temp_max", 28.0))
    @property
    def _phmin(self) -> float: return float(WATER_QUALITY_THRESHOLDS.get("ph_min", 6.5))
    @property
    def _phmax(self) -> float: return float(WATER_QUALITY_THRESHOLDS.get("ph_max", 8.5))
    @property
    def _oxymin(self) -> float: return float(WATER_QUALITY_THRESHOLDS.get("oxygen_min", 70.0)) 
    @property
    def _turb_max_warn(self) -> float: return float(WATER_QUALITY_THRESHOLDS.get("turbidez_max", 50.0))

    # ---------- Status por métrica ----------
    def status_temperatura(self) -> Severity:
        # hard limits já checados (0–50)
        return Severity.NORMAL if self._tmin <= self.temperatura <= self._tmax else Severity.WARNING

    def status_ph(self) -> Severity:
        # hard limits já checados (0–14)
        return Severity.NORMAL if self._phmin <= self.ph <= self._phmax else Severity.WARNING

    def status_oxigenio(self) -> Severity:
        # usando % de saturação: 0–100 como hard; alerta se < oxygen_min
        return Severity.NORMAL if self.oxigenio >= self._oxymin else Severity.WARNING

    def status_turbidez(self) -> Severity:
        # hard 0–200 já checado; alerta se passar do turbidez_max
        return Severity.NORMAL if self.turbidez <= self._turb_max_warn else Severity.WARNING

    # ---------- Status agregado ----------
    def status_geral_severity(self) -> Severity:
        s = [self.status_temperatura(), self.status_ph(), self.status_oxigenio(), self.status_turbidez()]
        if Severity.CRITICAL in s: return Severity.CRITICAL
        if Severity.WARNING in s:  return Severity.WARNING
        return Severity.NORMAL

    def get_status(self) -> Literal["normal", "alerta", "critico"]:
        sev = self.status_geral_severity()
        if sev == Severity.CRITICAL: return "critico"
        if sev == Severity.WARNING:  return "alerta"
        return "normal"

    def is_healthy(self) -> bool:
        return self.get_status() == "normal"

    def to_dict(self) -> dict:
        return {
            "tank_id": self.tank_id,
            "temperatura": self.temperatura,
            "ph": self.ph,
            "oxigenio": self.oxigenio,
            "turbidez": self.turbidez,
            "timestamp": self.timestamp.strftime("%d-%m-%Y %H:%M:%S") if self.timestamp else None,
            "status": self.get_status(),
        }
