# define como salvar/buscar os dados  mas nao onde devera ser salvo/buscado
# os outros modulos somente usam 
# src/domain/repositories/sensor_repository.py
from __future__ import annotations
from typing import Protocol, Iterable, Optional
from src.domain.entities.sensor_reading import SensorReading

class ISensorRepository(Protocol):
    """Persistência de leituras de sensores.

    Este protocolo define **como** as leituras devem ser manipuladas
    (métodos/assinaturas), sem impor a tecnologia de armazenamento.
    Implementações concretas (SQL, NoSQL, arquivo, memória, etc.) ficam a cargo da infra.
    """

    def add(self, reading: SensorReading) -> None:
        """Persiste uma leitura de sensor.

        Args:
            reading: Instância de SensorReading já validada pelo domínio.
        """
        ...

    def last_for_tank(self, tank_id: int) -> Optional[SensorReading]:
        """Retorna a leitura mais recente de um tanque (se existir).

        Args:
            tank_id: Identificador do tanque.

        Returns:
            A última leitura (ou None, caso não haja registros).
        """
        ...

    def list_for_tank(self, tank_id: int, limit: int = 100) -> Iterable[SensorReading]:
        """Lista leituras de um tanque (histórico).

        Args:
            tank_id: Identificador do tanque.
            limit: Quantidade máxima de leituras a retornar.

        Returns:
            Um iterável de SensorReading. A ordenação (ASC/DESC) deve ser
            definida pela implementação e documentada para consumo consistente.
        """
        ...
