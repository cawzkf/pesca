# aqui ficam os objetos principais  do sistema
# circulam pelo sistema carregando infos


from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from config.settings import WATER_QUALITY_THRESHOLDS

# decorador que clia classe automaticamente
@dataclass(frozen=True)
class SensorReading:
    # leitura dos sensores que medem a qualidade da agua 

    tank_id: int
    temperatura: float 
    ph: float         
    oxigenio: float      
    turbidez: float   
    timestamp: datetime = None

    def __post_init__(self):
        # validações
        if self.timestamp is None:
            object.__setattr__(self, 'timestamp', datetime.now())
        # validar temperatura (0-50°C)
        if not 0 <= self.temperatura <= 50:
            raise ValueError(f"Temperatura inválida: {self.temperatura}°C. Range: 0-50°C")
        
        # validar pH (0-14)
        if not 0 <= self.ph <= 14:
            raise ValueError(f"pH inválido: {self.ph}. Range: 0-14")
        
        # validar oxigênio (0-100%)
        if not 0 <= self.oxigenio <= 100:
            raise ValueError(f"Oxigênio inválido: {self.oxigenio}%. Range: 0-100%")
        
        # validar turbidez (0-200 NTU)
        if not 0 <= self.turbidez <= 200:
            raise ValueError(f"Turbidez inválida: {self.turbidez} NTU. Range: 0-200")
        
        # literal serve para retornar so as 3 strings

    def get_status(self) -> Literal["normal", "alerta", "critico"]:
        # Determina status baseado nos thresholds
        
        # verificar condições críticas
        if (self.ph < 6.0 or self.ph > 9.0 or 
            self.temperatura < 18 or self.temperatura > 35 or
            self.oxigenio < 30):
            return "critico"
        
        # verificar condições de alerta
        thresholds = WATER_QUALITY_THRESHOLDS
        if (self.ph < thresholds['ph_min'] or self.ph > thresholds['ph_max'] or
            self.temperatura < thresholds['temp_min'] or self.temperatura > thresholds['temp_max'] or
            self.oxigenio < thresholds['oxygen_min']):
            return "alerta"
        
        return "normal"
            
    def is_healthy(self) -> bool:
        # verifica a condição da agua
        return self.get_status() == "normal"