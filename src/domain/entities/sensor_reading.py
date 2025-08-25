from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, ClassVar
from config.settings import WATER_QUALITY_THRESHOLDS
from src.domain.enums import Severity


@dataclass(frozen=True)
class SensorReading:
    """
    Representa uma leitura pontual da qualidade da água de um tanque.

    - Imutável.
    - Valida limites físicos (hard limits) no __post_init__.
    - Lê limiares operacionais de WATER_QUALITY_THRESHOLDS.
    - Expõe status por métrica e status agregado.
    """

    tank_id: int
    temperatura: float
    ph: float
    oxigenio: float           # saturação de O2 em %, 0–100
    turbidez: float
    timestamp: datetime | None = None  # sempre normalizado para UTC

    # -------- Hard limits (físicos) --------
    _TEMP_MIN_HARD: ClassVar[float] = 0.0
    _TEMP_MAX_HARD: ClassVar[float] = 50.0
    _PH_MIN_HARD:   ClassVar[float] = 0.0
    _PH_MAX_HARD:   ClassVar[float] = 14.0
    _OXY_MIN_HARD:  ClassVar[float] = 0.0
    _OXY_MAX_HARD:  ClassVar[float] = 100.0
    _TURB_MIN_HARD: ClassVar[float] = 0.0
    _TURB_MAX_HARD: ClassVar[float] = 200.0

    def __post_init__(self) -> None:
        """
        - Garante timestamp em UTC.
        - Valida hard limits; valores fora disparam ValueError.
        """
        # Normaliza timestamp para UTC
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", datetime.now(timezone.utc))
        elif self.timestamp.tzinfo is None:
            object.__setattr__(self, "timestamp", self.timestamp.replace(tzinfo=timezone.utc))

        # Validações físicas (não negociáveis)
        if not (self._TEMP_MIN_HARD <= self.temperatura <= self._TEMP_MAX_HARD):
            raise ValueError(
                f"Temperatura inválida: {self.temperatura}°C. "
                f"Range: {self._TEMP_MIN_HARD}-{self._TEMP_MAX_HARD}°C"
            )
        if not (self._PH_MIN_HARD <= self.ph <= self._PH_MAX_HARD):
            raise ValueError(
                f"pH inválido: {self.ph}. Range: {self._PH_MIN_HARD}-{self._PH_MAX_HARD}"
            )
        if not (self._OXY_MIN_HARD <= self.oxigenio <= self._OXY_MAX_HARD):
            raise ValueError(
                f"Oxigênio inválido: {self.oxigenio}. Range: {self._OXY_MIN_HARD}-{self._OXY_MAX_HARD}"
            )
        if not (self._TURB_MIN_HARD <= self.turbidez <= self._TURB_MAX_HARD):
            raise ValueError(
                f"Turbidez inválida: {self.turbidez}. Range: {self._TURB_MIN_HARD}-{self._TURB_MAX_HARD}"
            )

    # -------- Limiar operacional (fonte: settings) --------
    @property
    def _tmin(self) -> float:
        """Temperatura mínima recomendada (°C)."""
        return float(WATER_QUALITY_THRESHOLDS.get("temp_min", 24.0))

    @property
    def _tmax(self) -> float:
        """Temperatura máxima recomendada (°C)."""
        return float(WATER_QUALITY_THRESHOLDS.get("temp_max", 28.0))

    @property
    def _phmin(self) -> float:
        """pH mínimo recomendado."""
        return float(WATER_QUALITY_THRESHOLDS.get("ph_min", 6.5))

    @property
    def _phmax(self) -> float:
        """pH máximo recomendado."""
        return float(WATER_QUALITY_THRESHOLDS.get("ph_max", 8.5))

    @property
    def _oxymin(self) -> float:
        """Saturação mínima de oxigênio (%) recomendada."""
        return float(WATER_QUALITY_THRESHOLDS.get("oxygen_min", 70.0))

    @property
    def _turb_max_warn(self) -> float:
        """Turbidez máxima antes de sinalizar alerta."""
        return float(WATER_QUALITY_THRESHOLDS.get("turbidez_max", 50.0))

    # -------- Status por métrica --------
    def status_temperatura(self) -> Severity:
        """
        Retorna o status da temperatura considerando o limiar operacional.
        Hard limits já foram validados no __post_init__.
        """
        return Severity.NORMAL if self._tmin <= self.temperatura <= self._tmax else Severity.WARNING

    def status_ph(self) -> Severity:
        """Retorna o status do pH considerando o limiar operacional."""
        return Severity.NORMAL if self._phmin <= self.ph <= self._phmax else Severity.WARNING

    def status_oxigenio(self) -> Severity:
        """Retorna o status do oxigênio (saturação %) considerando o mínimo recomendado."""
        return Severity.NORMAL if self.oxigenio >= self._oxymin else Severity.WARNING

    def status_turbidez(self) -> Severity:
        """Retorna o status da turbidez considerando o máximo recomendado."""
        return Severity.NORMAL if self.turbidez <= self._turb_max_warn else Severity.WARNING

    # -------- Status agregado --------
    def status_geral_severity(self) -> Severity:
        """
        Consolida os status de todas as métricas.
        Prioridade: CRITICAL > WARNING > NORMAL.
        """
        s = [
            self.status_temperatura(),
            self.status_ph(),
            self.status_oxigenio(),
            self.status_turbidez(),
        ]
        if Severity.CRITICAL in s:
            return Severity.CRITICAL
        if Severity.WARNING in s:
            return Severity.WARNING
        return Severity.NORMAL

    def get_status(self) -> Literal["normal", "alerta", "critico"]:
        """
        Mapeia o Severity agregado para rótulos string de consumo externo.
        """
        sev = self.status_geral_severity()
        if sev == Severity.CRITICAL:
            return "critico"
        if sev == Severity.WARNING:
            return "alerta"
        return "normal"

    def is_healthy(self) -> bool:
        """True se o status agregado for 'normal'."""
        return self.get_status() == "normal"

    def to_dict(self) -> dict:
        """
        Serializa a leitura para dicionário pronto para transporte/persistência.
        O timestamp é formatado como '%d-%m-%Y %H:%M:%S' em UTC.
        """
        return {
            "tank_id": self.tank_id,
            "temperatura": self.temperatura,
            "ph": self.ph,
            "oxigenio": self.oxigenio,
            "turbidez": self.turbidez,
            "timestamp": self.timestamp.strftime("%d-%m-%Y %H:%M:%S") if self.timestamp else None,
            "status": self.get_status(),
        }
