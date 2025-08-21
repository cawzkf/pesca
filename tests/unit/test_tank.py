from src.domain.entities.tank import Tank

def test_densidade_superlotacao():
    t = Tank(id=1, nome="A", capacidade=2000, quantidade_peixes=60, ip_adress="x", ativo=True)
    assert round(t.densidade_peixes_m3, 2) == 30.00
    assert t.is_superlotado(25.0) is True
