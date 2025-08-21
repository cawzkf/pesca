from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from src.domain.enums import TankStatus
try:
    from src.domain.value_objects import IPAddress
    IPType = IPAddress
    IP_GET = lambda ip: ip.value
except Exception:
    IPType = str
    IP_GET = lambda ip: ip

DEFAULT_MAX_POR_M3 = 20.0 

@dataclass(frozen=True)
class Tank:
    id: int
    nome: str
    capacidade: float            
    quantidade_peixes: int
    ip_adress: IPType          
    ativo: bool = True

    def __post_init__(self):
        if not self.nome.strip():
            raise ValueError("Nome do tanque não pode estar vazio.")
        if self.capacidade <= 0:
            raise ValueError("Capacidade deve ser > 0 (litros).")
        if self.quantidade_peixes < 0:
            raise ValueError("Quantidade de peixes não pode ser negativa.")

    @property
    def volume_m3(self) -> float:
        return self.capacidade / 1000.0

    @property
    def densidade_peixes_m3(self) -> float:
        # cálculo em memória (não persiste no banco)
        return float("inf") if self.volume_m3 == 0 else self.quantidade_peixes / self.volume_m3

    def is_superlotado(self, max_por_m3: float = DEFAULT_MAX_POR_M3) -> bool:
        return self.densidade_peixes_m3 > max_por_m3

    @property
    def status(self) -> TankStatus:
        # mapeia o booleano existente para status do requisito
        return TankStatus.ATIVO if self.ativo else TankStatus.INATIVO

    def to_dict(self) -> dict:
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
