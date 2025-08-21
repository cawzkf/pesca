from __future__ import annotations
from dataclasses import dataclass
from src.domain.entities.tank import Tank
from src.domain.entities.sensor_reading import SensorReading
from src.domain.enums import Severity

@dataclass(frozen=True)
class FeedRecommendation:
    tank_id: int
    gramas_por_peixe: float
    gramas_totais: float
    nota: str

    @staticmethod
    def a_partir_de_leitura(tank: Tank, leitura: SensorReading) -> "FeedRecommendation":
        base = 3.0  
        g = base
        if leitura.status_oxigenio() in (Severity.WARNING, Severity.CRITICAL):
            g *= 0.7
        if not (24.0 <= leitura.temperatura <= 28.0):  
            g *= 0.85
        total = g * tank.quantidade_peixes
        nota = "Ajustado por condições de água." if g != base else "Condições ideais."
        return FeedRecommendation(tank.id, round(g, 2), round(total, 2), nota)
