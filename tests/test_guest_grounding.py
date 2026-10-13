from app.guest_grounding import parse_source_id, requires_verified_guest_answer, source_id


def test_source_ids_are_property_scoped_and_shape_parser_does_not_resolve_records():
    first = source_id("property-a", "restaurant", "restaurant-1", "opening_hours")
    other_property = source_id("property-b", "restaurant", "restaurant-1", "opening_hours")
    other_field = source_id("property-a", "restaurant", "restaurant-1", "description")

    assert first.startswith("guest:property-a:")
    assert first != other_property
    assert first != other_field
    assert parse_source_id(first) == ("property-a", "restaurant", "restaurant-1", "opening_hours")
    # Parsing proves bounded syntax only. Record existence and guest visibility
    # are checked against current property stores at the response boundary.
    assert parse_source_id("guest:property-a:restaurant:does-not-exist") == (
        "property-a", "restaurant", "does-not-exist", "",
    )
    assert parse_source_id("guest:property-a:restaurant:bad/id") is None
    assert parse_source_id("guest:property-a:restaurant:item:opening_hours:extra") is None


def test_property_fact_routing_covers_indirect_and_multilingual_questions():
    for message in (
        "Could you tell me when the rooftop pool closes?",
        "¿La piscina está abierta ahora?",
        "Magkano ang extra unan?",
        "Tell me the hotel's pet policy",
        "Could housekeeping bring another towel",
    ):
        assert requires_verified_guest_answer(message), message


def test_general_conversation_can_still_use_the_natural_chat_path():
    for message in (
        "Thanks, that helped.",
        "I had a lovely walk by the river today.",
        "Help me write a birthday message for my sister.",
    ):
        assert not requires_verified_guest_answer(message), message
