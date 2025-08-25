# src/domain/use_cases/optimize_feed_use_case.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional
import logging

from src.domain.repositories.tank_repository import ITankRepository
from src.domain.repositories.sensor_repository import ISensorRepository
from src.domain.repositories.feed_repository import IFeedRecommendationRepository
from src.domain.entities.sensor_reading import SensorReading
from src.domain.enums import Severity

log = logging.getLogger("pesca.usecases.feed")

# assinatura do preditor de peso (injeção de dependência)
WeightPredictor = Callable[[dict], float]

@dataclass(frozen=True)
class OptimizeFeedResult:
    """
    DTO imutável com o resultado da recomendação de ração.
    """
    grams_per_fish: float
    total_grams: float
    notes: str

class OptimizeFeedUseCase:
    """
    Calcula recomendação de ração:
    - usa preditor de peso (RF) se fornecido, senão aplica baseline
    - aplica redutores conforme severidade das condições da água
    - persiste recomendação
    """

    def __init__(
        self,
        tank_repo: ITankRepository,
        sensor_repo: ISensorRepository,
        feed_repo: IFeedRecommendationRepository,
        weight_predictor: Optional[WeightPredictor] = None,
    ) -> None:
        """
        Injeta repositórios do domínio e, opcionalmente, um preditor de peso.

        Args:
            tank_repo: Acesso à entidade Tank.
            sensor_repo: Acesso à última leitura de sensores do tanque.
            feed_repo: Persistência da recomendação de ração.
            weight_predictor: Função opcional que recebe features e retorna peso (kg).
        """
        self.tank_repo = tank_repo
        self.sensor_repo = sensor_repo
        self.feed_repo = feed_repo
        self.weight_predictor = weight_predictor  # pode ser injetado nos testes

    def execute(self, tank_id: int, dias_cultivo: float = 120.0) -> OptimizeFeedResult:
        """
        Gera e persiste uma recomendação de ração para o tanque informado.

        Fluxo resumido:
            - Busca Tank e última leitura; usa leitura neutra se ausente.
            - Estima peso (kg) por peixe via preditor ou baseline (0.10 kg).
            - Calcula 2% do peso em gramas por peixe, com piso de 0.1 g.
            - Reduz 10% ou 30% conforme severidade (WARNING/CRITICAL).
            - Calcula total (g) para o tanque e persiste no repositório.

        Args:
            tank_id: Identificador do tanque.
            dias_cultivo: Idade do cultivo usada como feature no preditor.

        Returns:
            OptimizeFeedResult: valores arredondados e nota de condição.
        """
        tank = self.tank_repo.get(tank_id)
        if not tank:
            raise ValueError(f"Tank {tank_id} não encontrado")

        reading = self.sensor_repo.last_for_tank(tank_id)
        if not reading:
            # se não houver leitura, usamos valores neutros
            reading = SensorReading(tank_id, 26.0, 7.2, 80.0, 20.0)

        # densidade peixes/m³
        m3 = max(0.001, float(tank.capacidade) / 1000.0)
        densidade = float(tank.quantidade_peixes) / m3

        # peso previsto (kg) — se não tiver preditor, supõe 100g
        if self.weight_predictor:
            peso_kg = self.weight_predictor({
                "temperatura": reading.temperatura,
                "ph": reading.ph,
                "oxigenio": reading.oxigenio,
                "turbidez": reading.turbidez,
                "dias_cultivo": dias_cultivo,
                "densidade": densidade,
            })
        else:
            peso_kg = 0.10

        # 2% do peso/dia por peixe (ajuste fácil de entender)
        grams_per_fish = max(0.1, peso_kg * 1000.0 * 0.02)

        # Redutores conforme severidade geral
        sev = reading.status_geral_severity()
        note = "condições normais"
        if sev == Severity.WARNING:
            grams_per_fish *= 0.90
            note = "redução 10% por alerta"
        elif sev == Severity.CRITICAL:
            grams_per_fish *= 0.70
            note = "redução 30% por crítico"

        total_grams = grams_per_fish * float(tank.quantidade_peixes)

        self.feed_repo.save(
            tank_id=tank_id,
            grams_per_fish=float(round(grams_per_fish, 2)),
            total_grams=float(round(total_grams, 1)),
            algorithm="RF|baseline",
            recommended_time=datetime.now(timezone.utc),
            notes=note,
        )
        log.info("feed_saved tank=%s g_per_fish=%.2f total=%.1f sev=%s",
                 tank_id, grams_per_fish, total_grams, sev.name)

        return OptimizeFeedResult(
            grams_per_fish=float(round(grams_per_fish, 2)),
            total_grams=float(round(total_grams, 1)),
            notes=note,
        )
