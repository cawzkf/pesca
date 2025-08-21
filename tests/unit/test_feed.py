from src.domain.entities.feed_recommendation import FeedRecommendation
from src.domain.entities.tank import Tank
from src.domain.entities.sensor_reading import SensorReading
from datetime import datetime, UTC

def test_feed_calc():
    t = Tank(1, "A", 2000, 50, "x", True)
    r = SensorReading(1, 26.0, 7.2, 80.0, 10.0, datetime.now(UTC))
    rec = FeedRecommendation.a_partir_de_leitura(t, r)
    assert rec.gramas_totais > 0
