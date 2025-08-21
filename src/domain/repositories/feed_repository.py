# src/domain/repositories/feed_repository.py
from __future__ import annotations
from typing import Protocol
from datetime import datetime

class IFeedRecommendationRepository(Protocol):
    def save(
        self,
        *,
        tank_id: int,
        grams_per_fish: float,
        total_grams: float,
        algorithm: str,
        recommended_time: datetime,
        notes: str = "",
    ) -> None: ...
