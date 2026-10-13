from app.guest_grounding import source_id, unsupported_hotel_claim


def test_source_ids_are_property_scoped_and_field_specific():
    first = source_id("property-a", "restaurant", "restaurant-1", "opening_hours")
    other_property = source_id("property-b", "restaurant", "restaurant-1", "opening_hours")
    other_field = source_id("property-a", "restaurant", "restaurant-1", "description")

    assert first.startswith("guest:property-a:")
    assert first != other_property
    assert first != other_field


def test_free_form_model_cannot_assert_hotel_features_even_if_a_record_mentions_them():
    evidence = '[{"name":"Rooftop Pool","opening_hours":"6:00 AM-10:00 PM"}]'
    assert unsupported_hotel_claim("The rooftop pool is open until 10 PM.", evidence)


def test_unverified_price_and_operating_hours_are_rejected():
    evidence = '[{"name":"Spa","opening_hours":"10:00 AM-8:00 PM","price":"PHP 1,500"}]'

    assert unsupported_hotel_claim("The spa closes at 9 PM.", evidence)
    assert unsupported_hotel_claim("The spa treatment costs PHP 2,000.", evidence)


def test_unsupported_service_and_cross_property_entity_claims_are_rejected():
    evidence = '[{"property_id":"property-a","guest_services":[{"name":"Extra towels"}]}]'

    assert unsupported_hotel_claim("Housekeeping can bring an extra pillow.", evidence)
    assert unsupported_hotel_claim("The rooftop pool is open.", evidence)
    assert unsupported_hotel_claim("There's a rooftop sauna.", evidence)
    assert unsupported_hotel_claim("The hotel offers an airport shuttle.", evidence)
    assert unsupported_hotel_claim("Try Lantern House for dinner.", evidence)


def test_natural_non_property_chat_can_still_pass_without_hotel_claims():
    assert not unsupported_hotel_claim(
        "Of course. I can help you plan a relaxed afternoon.",
        "No matching verified hotel facts.",
    )
