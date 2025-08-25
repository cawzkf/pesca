from enum import Enum, auto

class TankStatus(Enum):
    """Estado operacional do tanque."""
    ATIVO = auto()        # Operando normalmente
    MANUTENCAO = auto()   # Em manutenção (temporariamente indisponível)
    INATIVO = auto()      # Fora de operação

class Severity(Enum):
    """Nível de severidade para condições/alertas."""
    NORMAL = auto()    # Dentro da faixa esperada
    WARNING = auto()   # Atenção: fora do ideal
    CRITICAL = auto()  # Crítico: ação imediata necessária

class AlertType(Enum):
    """Categoria/origem do alerta."""
    WATER_QUALITY = auto()  # Relacionado à qualidade da água (pH, temp, O2, turbidez)
    OVERCROWD = auto()      # Densidade/superlotação
    DEVICE = auto()         # Dispositivo/sensor/equipamento
