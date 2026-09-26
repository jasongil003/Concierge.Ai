from pathlib import Path

from app.hotel import HotelKnowledge


def test_empty_property_profile_has_no_seeded_knowledge():
    knowledge = HotelKnowledge(Path("data/hotel.json"))
    assert knowledge.public_profile["name"] == ""
    assert knowledge.exact_fast_answer("What time is breakfast?") is None
    assert knowledge.retrieve("My Wi-Fi connection is not working") == []
