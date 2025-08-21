import ipaddress
from dataclasses import dataclass

@dataclass(frozen=True)
class IPAddress:
    value: str
    def __post_init__(self):
        try:
            ipaddress.ip_address(self.value)
        except ValueError as e:
            raise ValueError(f"IP inválido: {self.value}") from e
