from enum import Enum, auto

class TankStatus(Enum):
    ATIVO = auto()
    MANUTENCAO = auto()
    INATIVO = auto()

class Severity(Enum):
    NORMAL = auto()
    WARNING = auto()
    CRITICAL = auto()

class AlertType(Enum):
    WATER_QUALITY = auto()
    OVERCROWD = auto()
    DEVICE = auto()
