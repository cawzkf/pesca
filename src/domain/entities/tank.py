from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from src.domain.enums import TankStatus
try:
    from src.domain.value_objects import IPAddress
    IPType = IPAddress
    IP_GET = lambda ip: ip.value
except Exception:
    # Fallback: caso o VO IPAddress não exista, usa string crua
    IPType = str
    IP_GET = lambda ip: ip

# Densidade de referência (peixes por m³) para avaliar superlotação
DEFAULT_MAX_POR_M3 = 20.0 

@dataclass(frozen=True)
class Tank:
    """
    Representa um tanque de piscicultura.
    - Imutável (dataclass frozen)
    - Valida campos essenciais no __post_init__
    - Expõe propriedades derivadas (volume e densidade)
    - Mapeia 'ativo' para TankStatus
    - Serializa para dicionário com valores prontos para API/log
    """
    id: int
    nome: str
    capacidade: float            # litros
    quantidade_peixes: int
    ip_adress: IPType            # VO IPAddress (se disponível) ou str
    ativo: bool = True

    def __post_init__(self):
        """
        Regras de consistência de dados:
        - nome não pode ser vazio
        - capacidade > 0 (litros)
        - quantidade_peixes >= 0
        """
        if not self.nome.strip():
            raise ValueError("Nome do tanque não pode estar vazio.")
        if self.capacidade <= 0:
            raise ValueError("Capacidade deve ser > 0 (litros).")
        if self.quantidade_peixes < 0:
            raise ValueError("Quantidade de peixes não pode ser negativa.")

    @property
    def volume_m3(self) -> float:
        """Volume em metros cúbicos (1.000 litros = 1 m³)."""
        return self.capacidade / 1000.0

    @property
    def densidade_peixes_m3(self) -> float:
        """
        Densidade de peixes por m³.
        Retorna infinito se volume for 0 para evitar divisão por zero.
        """
        # cálculo em memória (não persiste no banco)
        return float("inf") if self.volume_m3 == 0 else self.quantidade_peixes / self.volume_m3

    def is_superlotado(self, max_por_m3: float = DEFAULT_MAX_POR_M3) -> bool:
        """
        Indica superlotação se a densidade atual exceder o limite fornecido.
        """
        return self.densidade_peixes_m3 > max_por_m3

    @property
    def status(self) -> TankStatus:
        """
        Mapeia o booleano 'ativo' para o enum TankStatus requerido.
        """
        # mapeia o booleano existente para status do requisito
        return TankStatus.ATIVO if self.ativo else TankStatus.INATIVO

    def to_dict(self) -> dict:
        """
        Serialização amigável para APIs/logs.
        - 'ip_adress' normalizado via IP_GET (VO ou str)
        - 'status' exportado como nome do enum
        - 'densidade_peixes_m3' arredondada em 3 casas decimais
        """
        return {
            "id": self.id,
            "nome": self.nome,
            "capacidade": self.capacidade,
            "quantidade_peixes": self.quantidade_peixes,
            "ip_adress": IP_GET(self.ip_adress),
            "ativo": self.ativo,
            "status": self.status.name,
            "densidade_peixes_m3": round(self.densidade_peixes_m3, 3),
        }
