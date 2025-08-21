# define como salvar/buscar os dados  mas nao onde devera ser salvo/buscado
# os outros modulos somente usam 
# src/domain/repositories/sensor_repository.py
from __future__ import annotations
from typing import Protocol, Iterable, Optional
from src.domain.entities.sensor_reading import SensorReading

class ISensorRepository(Protocol):
    """Persistência de leituras de sensores."""

    def add(self, reading: SensorReading) -> None: ...
    def last_for_tank(self, tank_id: int) -> Optional[SensorReading]: ...
    def list_for_tank(self, tank_id: int, limit: int = 100) -> Iterable[SensorReading]: ...
