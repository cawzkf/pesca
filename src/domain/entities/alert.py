"""
Módulo de definição de alertas do domínio.

Este módulo concentra o tipo imutável `Alert`, responsável por representar
eventos relevantes detectados no monitoramento (qualidade da água, densidade,
etc.). O objetivo é fornecer uma unidade de informação autocontida e
consistente, adequada para persistência, exibição e auditoria.

Princípios e invariantes adotados
---------------------------------
- **Imutabilidade**: `Alert` é um `dataclass(frozen=True)`. Qualquer mudança
  (p.ex., marcar como resolvido) gera **uma nova instância**.
- **Temporalidade em UTC**: `created_at` e `resolved_at` são normalizados para
  timezone UTC. Se valores "naive" (sem tzinfo) forem fornecidos, são
  ajustados para UTC no `__post_init__`.
- **Identificação**: `id` deve ser único no repositório de alertas.
- **Semântica de resolução**: um alerta resolvido mantém o histórico de
  criação e armazena `resolved_at`. A duração é calculada como
  `resolved_at - created_at`.

Campos livres
-------------
- `metadata` carrega informações específicas do tipo de alerta para
  rastreabilidade (ex.: nome da métrica, valor medido, limites aplicados).
  A estrutura é opcional e dependente do `AlertType`.

Dependências
------------
- `AlertType` e `Severity` são enums do domínio.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from src.domain.enums import AlertType, Severity


@dataclass(frozen=True)
class Alert:
    """
    Entidade imutável que representa um alerta gerado pelo sistema.

    Attributes:
        id: Identificador único do alerta no escopo do repositório.
        tank_id: Identificador do tanque ao qual o alerta pertence.
        type: Tipo do alerta (ex.: `AlertType.WATER_QUALITY`).
        severity: Nível de severidade (NORMAL, WARNING, CRITICAL).
        message: Texto curto e objetivo descrevendo o motivo do alerta.
        created_at: Instante de criação do alerta (normalizado para UTC).
        metadata: Dados auxiliares para auditoria e contexto (opcional).
        resolved_at: Instante de resolução (UTC), se já resolvido.

    Observações:
        - Imutável por design. Métodos que “alteram” retornam uma NOVA instância.
        - `created_at` e `resolved_at` são garantidos como timezone-aware (UTC).
    """

    id: str
    tank_id: int
    type: AlertType
    severity: Severity
    message: str
    created_at: datetime
    metadata: Optional[Dict[str, Any]] = None
    resolved_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        """
        Normaliza `created_at` e (se existir) `resolved_at` para timezone-aware UTC.

        Regras:
            - Se `created_at.tzinfo` for `None` (naive), assume UTC.
            - Se `resolved_at` existir e for naive, assume UTC.

        Justificativa:
            Manter dados temporais em UTC evita ambiguidades de fuso horário
            em persistência, ordenação e auditoria.
        """
        tz = timezone.utc

        # `dataclass(frozen=True)` impede atribuição direta; usa-se `object.__setattr__`.
        if self.created_at.tzinfo is None:
            object.__setattr__(self, "created_at", self.created_at.replace(tzinfo=tz))

        if self.resolved_at and self.resolved_at.tzinfo is None:
            object.__setattr__(self, "resolved_at", self.resolved_at.replace(tzinfo=tz))

    def resolve(self, when: Optional[datetime] = None) -> "Alert":
        """
        Marca o alerta como resolvido, retornando uma NOVA instância.

        Args:
            when: Instante da resolução. Se omitido, usa o horário atual em UTC.

        Returns:
            Uma nova instância de `Alert` com `resolved_at` definido.

        Exemplo:
            >>> a = Alert(..., created_at=datetime.now(timezone.utc))
            >>> b = a.resolve()  # `a` permanece intacto; `b` é a versão resolvida.
        """
        resolved_time = when or datetime.now(timezone.utc)
        return replace(self, resolved_at=resolved_time)

    @property
    def duration(self) -> Optional[timedelta]:
        """
        Duração entre a criação e a resolução do alerta.

        Returns:
            `timedelta` com o intervalo (`resolved_at - created_at`) se já
            resolvido; caso contrário, `None`.

        Observação:
            Para duração "em aberto" (agora - created_at) adote cálculo externo,
            mantendo este método coerente com a semântica de “alerta resolvido”.
        """
        return None if not self.resolved_at else (self.resolved_at - self.created_at)

    # -------------------------------------------------------------------------
    # Fábricas especializadas
    # -------------------------------------------------------------------------

    @staticmethod
    def water_quality(
        tank_id: int,
        metric: str,
        value: float,
        severity: Severity,
        limits: dict,
        alert_id: str,
    ) -> "Alert":
        """
        Cria um alerta de qualidade da água padronizado.

        Args:
            tank_id: Tanque associado.
            metric: Nome da grandeza (ex.: "oxigenio", "temperatura", "ph", "turbidez").
            value: Valor medido que motivou o alerta.
            severity: Severidade atribuída ao evento.
            limits: Dicionário de limites/limiares aplicados no momento.
                Chaves recomendadas: 'warn_low', 'warn_high' (podem não existir).
            alert_id: Identificador único do alerta.

        Returns:
            Instância de `Alert` com `type=AlertType.WATER_QUALITY` e `metadata`
            contendo `metric`, `value` e `limits`.

        Mensagem gerada:
            "{metric}={value} fora da faixa ótima (warn_low–warn_high)"

        Observações:
            - O texto exibe '-' caso algum limite não esteja presente em `limits`.
            - `created_at` é definido no instante da criação (UTC).
        """
        msg = (
            f"{metric}={value} fora da faixa ótima "
            f"({limits.get('warn_low','-')}–{limits.get('warn_high','-')})"
        )
        return Alert(
            alert_id,
            tank_id,
            AlertType.WATER_QUALITY,
            severity,
            msg,
            datetime.now(timezone.utc),
            metadata={"metric": metric, "value": value, "limits": limits},
        )

    @staticmethod
    def overcrowd(tank_id: int, density_m3: float, max_per_m3: float, alert_id: str) -> "Alert":
        """
        Cria um alerta de superlotação (densidade acima do limite).

        Args:
            tank_id: Tanque associado.
            density_m3: Densidade atual (peixes por metro cúbico).
            max_per_m3: Limite máximo permitido (peixes por metro cúbico).
            alert_id: Identificador único do alerta.

        Returns:
            Instância de `Alert` com `type=AlertType.OVERCROWD`,
            severidade CRITICAL e metadados de densidade.

        Mensagem gerada:
            "Densidade {density_m3:.2f}/m³ > limite {max_per_m3:.2f}/m³"
        """
        msg = f"Densidade {density_m3:.2f}/m³ > limite {max_per_m3:.2f}/m³"
        return Alert(
            alert_id,
            tank_id,
            AlertType.OVERCROWD,
            Severity.CRITICAL,
            msg,
            datetime.now(timezone.utc),
            metadata={"density_m3": density_m3, "max_per_m3": max_per_m3},
        )
