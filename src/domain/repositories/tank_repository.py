# src/domain/repositories/tank_repository.py
from __future__ import annotations
from typing import Protocol, Optional
from src.domain.entities.tank import Tank

class ITankRepository(Protocol):
    def get(self, tank_id: int) -> Optional[Tank]: ...
