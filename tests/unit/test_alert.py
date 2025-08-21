from src.domain.entities.alert import Alert
from src.domain.enums import Severity, AlertType

def test_resolve_duration():
    a = Alert.overcrowd(1, 35.0, 25.0, "ovc-1")
    b = a.resolve()
    assert b.type is AlertType.OVERCROWD
    assert b.resolved_at is not None
    assert b.duration is not None
