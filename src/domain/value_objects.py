import ipaddress
from dataclasses import dataclass

@dataclass(frozen=True)
class IPAddress:
    """
    Value Object para endereço IP.

    - Imutável (frozen).
    - Valida IPv4 no __post_init__ via ipaddress.ip_address.
    - Em caso de IP inválido, levanta ValueError com mensagem padronizada.
    """
    value: str

    def __post_init__(self):
        """
        Valida o valor informado como IPv4.
        Usa ipaddress.ip_address que lança ValueError se inválido.
        """
        try:
            ipaddress.ip_address(self.value)  # valida e descarta o retorno
        except ValueError as e:
            raise ValueError(f"IP inválido: {self.value}") from e
