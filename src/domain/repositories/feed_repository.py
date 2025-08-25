# src/domain/repositories/feed_repository.py
from __future__ import annotations
from typing import Protocol
from datetime import datetime

class IFeedRecommendationRepository(Protocol):
    """
    Contrato de repositório para recomendações de alimentação.
    Implementações concretas devem persistir registros com
    dosagem por peixe, total, algoritmo/estratégia e horário recomendado.
    """

    def save(
        self,
        *,
        tank_id: int,
        grams_per_fish: float,
        total_grams: float,
        algorithm: str,
        recommended_time: datetime,
        notes: str = "",
    ) -> None:
        """
        Persiste uma recomendação de ração para um tanque.

        Args:
            tank_id: Identificador do tanque.
            grams_per_fish: Quantidade (g) por peixe.
            total_grams: Quantidade total (g) recomendada.
            algorithm: Rótulo da estratégia/algoritmo utilizado.
            recommended_time: Instante recomendado para a alimentação (preferir UTC).
            notes: Observações adicionais (opcional).

        Returns:
            None. Efeito colateral: gravação da recomendação.
        """
        ...
