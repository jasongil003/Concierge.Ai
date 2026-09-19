from pathlib import Path

from app.hotel import HotelKnowledge


def test_fast_path_breakfast():
    knowledge = HotelKnowledge(Path("data/hotel.json"))
    answer = knowledge.exact_fast_answer("What time is breakfast?")
    assert answer is not None
    assert "6:30 AM" in answer


def test_retrieval_wifi():
    knowledge = HotelKnowledge(Path("data/hotel.json"))
    results = knowledge.retrieve("My Wi-Fi connection is not working")
    assert results
    assert results[0]["title"] == "Guest Wi-Fi"
