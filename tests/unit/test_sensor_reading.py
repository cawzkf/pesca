from datetime import datetime, UTC
from src.domain.entities.sensor_reading import SensorReading
from src.domain.enums import Severity

def test_status_normal():
    r = SensorReading(1, 26.0, 7.2, 75.0, 20.0, datetime.now(UTC))
    assert r.status_geral_severity() == Severity.NORMAL
