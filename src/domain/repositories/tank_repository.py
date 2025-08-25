# src/domain/repositories/tank_repository.py
from __future__ import annotations
from typing import Protocol, Optional
from src.domain.entities.tank import Tank

class ITankRepository(Protocol):
    """
    Contrato de repositório para a entidade Tank.

    Implementações concretas devem fornecer a busca por ID sem impor
    a tecnologia de armazenamento (SQL, NoSQL, cache, memória, etc.).
    """

    def get(self, tank_id: int) -> Optional[Tank]:
        """
        Recupera um Tank pelo identificador.

        Args:
            tank_id: Identificador único do tanque.

        Returns:
            Optional[Tank]: Instância de Tank se encontrado; None caso contrário.
        """
        ...
