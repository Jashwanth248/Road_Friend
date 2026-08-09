from app.ml.recommender import rank_places
from app.models import Location


def test_location_validation():
    loc = Location(latitude=44.56, longitude=-123.26)
    assert loc.latitude == 44.56


def test_recommender_orders_high_rating_first():
    data = [
        {"name": "A", "rating": 4.0, "reviews": 10},
        {"name": "B", "rating": 4.9, "reviews": 500},
    ]
    assert rank_places(data)[0]["name"] == "B"
