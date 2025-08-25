"""
Recomendação de ração a partir de uma leitura de sensores.

Este módulo define a entidade imutável `FeedRecommendation`, responsável por
conter a recomendação diária (em gramas por peixe e total do tanque) e um
texto explicativo (“nota”) sobre os ajustes aplicados com base nas condições
da água.

Princípios:
- **Imutabilidade**: o dataclass é `frozen=True`, garantindo rastreabilidade
  e evitando alterações acidentais após a criação.
- **Determinismo**: para uma mesma leitura e parâmetros de tanque, a
  recomendação é reprodutível.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.entities.tank import Tank
from src.domain.entities.sensor_reading import SensorReading
from src.domain.enums import Severity


@dataclass(frozen=True)
class FeedRecommendation:
    """
    Estrutura que representa uma recomendação de ração para um tanque.

    Attributes:
        tank_id: Identificador do tanque.
        gramas_por_peixe: Quantidade sugerida por peixe, em gramas/dia.
        gramas_totais: Quantidade total diária para o tanque, em gramas.
        nota: Texto curto justificando a recomendação (condições ideais ou
              ajustes aplicados).
    """
    tank_id: int
    gramas_por_peixe: float
    gramas_totais: float
    nota: str

    @staticmethod
    def a_partir_de_leitura(tank: Tank, leitura: SensorReading) -> "FeedRecommendation":
        """
        Calcula uma recomendação simples de ração com base na leitura atual.

        Regras aplicadas:
            1) Ponto de partida: 3,0 g/peixe/dia.
            2) Ajuste por oxigênio dissolvido:
               - Se a severidade do oxigênio for WARNING ou CRITICAL,
                 reduz 30% (multiplica por 0,70).
            3) Ajuste por temperatura:
               - Se a temperatura estiver fora da faixa 24,0–28,0 °C,
                 reduz 15% (multiplica por 0,85).
            4) Total do tanque:
               - `gramas_por_peixe` × `quantidade_peixes` do tanque.
            5) Nota:
               - “Condições ideais.” se nenhum ajuste foi aplicado.
               - “Ajustado por condições de água.” se houve redução.

        Args:
            tank: Entidade do tanque contendo ao menos `id` e `quantidade_peixes`.
            leitura: Leitura de sensores usada para avaliar as condições da água.

        Returns:
            Instância de `FeedRecommendation` com valores arredondados a 2 casas.
        """
        # Base inicial em g/peixe/dia (valor de referência operacional).
        base = 3.0
        g = base

        # Redução por condição de oxigênio fora do ideal.
        if leitura.status_oxigenio() in (Severity.WARNING, Severity.CRITICAL):
            g *= 0.70

        # Redução por temperatura fora da faixa operacional 24–28 °C.
        if not (24.0 <= leitura.temperatura <= 28.0):
            g *= 0.85

        # Cálculo do total diário para o tanque.
        total = g * tank.quantidade_peixes

        # Nota explicativa da recomendação.
        nota = "Ajustado por condições de água." if g != base else "Condições ideais."

        return FeedRecommendation(
            tank_id=tank.id,
            gramas_por_peixe=round(g, 2),
            gramas_totais=round(total, 2),
            nota=nota,
        )
