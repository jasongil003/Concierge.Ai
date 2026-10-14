import json
import zipfile

import pytest

from app.operations import OperationsStore
from app.rwg_knowledge import build_import_plan, load_rwg_package


OFFICIAL = "https://www.rwgenting.com/en/things-to-do/shopping/skyavenue-complex.html"


def _write_package(path, *, image_url="https://www.rwgenting.com/images/photo.jpg"):
    official_map = {
        "id": "skyavenue-directory",
        "title": "SkyAvenue official directory",
        "scope": "SkyAvenue",
        "format": "html",
        "official_url": OFFICIAL,
        "local_file": None,
        "file_bundled": False,
        "version": "currentness not verified",
        "interactive_indoor_routing": False,
        "license_status": "not-cleared",
    }
    primary = {
        "schema_version": "1.0.0",
        "dataset_id": "rwg-test-v2",
        "mode": "reference_content_not_live_integration",
        "verified_as_of": "2026-10-14",
        "brand": {"name": "Resorts World Genting"},
        "content_governance": {},
        "hotels": [
            {"id": "hotel-a", "name": "Hotel A", "description": "A test property.", "time_zone": "Asia/Kuala_Lumpur", "location": "Genting Highlands", "contact": {}, "hero_image_id": "lobby-a", "gallery_image_ids": []},
            {"id": "hotel-b", "name": "Hotel B", "description": "Another test property.", "time_zone": "Asia/Kuala_Lumpur", "location": "Genting Highlands", "contact": {}, "hero_image_id": None, "gallery_image_ids": []},
        ],
        "images": [{"id": "lobby-a", "hotel_id": "hotel-a", "title": "Lobby", "url": image_url, "source_page": OFFICIAL, "rights": "Permission not established", "local_path": None, "status": "reference_only"}],
        "restaurants": [
            {"id": "restaurant-a", "name": "Restaurant A", "hotel_id": "hotel-a", "category": "Dining", "location": "Level G, Hotel A", "hours_display": None, "menu": {"items": [], "prices_verified": False}, "source_url": OFFICIAL, "status": "information_only"},
            {"id": "restaurant-shared", "name": "Shared Restaurant", "hotel_id": None, "category": "Dining", "location": "SkyAvenue", "hours_display": None, "menu": {"items": [], "prices_verified": False}, "source_url": OFFICIAL, "status": "information_only"},
        ],
        "facilities": [{"id": "lobby-a-facility", "name": "Hotel A Lobby", "hotel_id": "hotel-a", "category": "lobby", "level": "G", "navigation": {"verified_route": None}}],
        "attractions": [{"id": "skyworlds", "name": "Genting SkyWorlds", "category": "park", "website": "https://www.gentingskyworlds.com/", "opening_hours": None, "live_ticket_price": None}],
        "maps": [official_map],
        "guest_service_request_templates": [{"id": "late-checkout", "title": "Late checkout enquiry", "guest_can_request": False, "status": "proposed_service_category_not_verified_as_offered"}],
        "faq": [
            {"question": "When is Hotel A check-in?", "answer": "Check-in is at 3:00 PM.", "hotel_id": "hotel-a", "source_url": OFFICIAL},
            {"question": "Can I book online?", "answer": "Use the official booking website.", "hotel_id": None, "source_url": "https://book.rwgenting.com/"},
        ],
        "sources": [OFFICIAL],
        "maps_status": "official references only",
    }
    locations = {"source_checked": "2026-10-14", "facilities": [{
        "id": "facility-001", "name": "ATM", "complex": "SkyAvenue", "level": "1",
        "location_description": "Near currency exchange", "category": "banking", "source_url": OFFICIAL,
        "coordinates": None, "indoor_route": None, "status": "official-directory-listed",
    }]}
    manifest = {
        "version": "2.0", "copyright_note": "Permission required before redistribution.",
        "map_files_in_zip": 0, "image_files_in_zip": 0, "image_references_in_primary_json": 1,
        "maps": [official_map],
        "directions_policy": "No routes without verified floorplans.",
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("rwg_hotel_knowledge.json", json.dumps(primary))
        archive.writestr("maps/facility_locations.json", json.dumps(locations))
        archive.writestr("maps/map_manifest.json", json.dumps(manifest))
    return path


def test_loader_reads_all_three_json_files_and_builds_scoped_non_destructive_plan(tmp_path):
    package = load_rwg_package(_write_package(tmp_path / "rwg.zip"))
    records, report = build_import_plan(package, {"hotel-a": "property-a", "hotel-b": "property-b"})

    assert len(records) == report["planned_records"]
    assert report["facility_locations"] == 1
    assert report["coordinates_present"] == 0
    assert report["indoor_routes_present"] == 0
    assert report["map_files_bundled"] == 0
    assert report["images_with_unconfirmed_rights"] == 1
    image = next(item for item in records if item["record_type"] == "image")
    assert image["payload"]["display_allowed"] is False
    assert image["payload"]["display_image_url"] == ""
    assert any(item["record_type"] == "faq" and item["property_id"] == "property-a" for item in records)
    assert any(item["record_type"] == "facility_location" and item["property_id"] == "property-b" for item in records)
    assert not any(item["record_type"] == "service_request_template" and item["enabled"] for item in records)


def test_import_is_idempotent_property_scoped_and_refuses_conflicting_replacement(tmp_path):
    package = load_rwg_package(_write_package(tmp_path / "rwg.zip"))
    records, _ = build_import_plan(package, {"hotel-a": "property-a", "hotel-b": "property-b"})
    store = OperationsStore(tmp_path / "knowledge.db")

    first = store.import_reference_knowledge_batch(records)
    second = store.import_reference_knowledge_batch(records)
    assert sum(created for _, created in first) == len(records)
    assert not any(created for _, created in second)
    assert {row["property_id"] for row in store.imported_reference_knowledge("property-a")} == {"property-a"}
    assert all(row["property_id"] == "property-b" for row in store.imported_reference_knowledge("property-b"))
    assert store.imported_reference_knowledge("missing-property") == []
    assert not any(row["source_name"].endswith(":service_request_template:late-checkout") for row in store.imported_reference_knowledge("property-a"))

    new_item = {
        "property_id": "property-a", "dataset_id": "rwg-test-v2", "record_type": "hotel",
        "source_record_id": "property-a-extra", "payload": {"id": "property-a-extra", "name": "Extra"},
    }
    conflicting = dict(records[0])
    conflicting["payload"] = {**conflicting["payload"], "name": "Changed in place"}
    before = len(store.list_knowledge("property-a"))
    with pytest.raises(ValueError, match="no data was replaced"):
        store.import_reference_knowledge_batch([new_item, conflicting])
    assert len(store.list_knowledge("property-a")) == before


def test_structured_rwg_records_are_not_guest_faq_answers_but_real_faqs_remain_searchable(tmp_path):
    store = OperationsStore(tmp_path / "rwg-search.db")
    rows = [
        {
            "property_id": "rwg-crockfords", "dataset_id": "rwg-test-v2",
            "record_type": "dataset_metadata", "source_record_id": "package",
            "payload": {"brand": {"name": "Resorts World Genting"}, "maps_status": "official references only"},
        },
        {
            "property_id": "rwg-crockfords", "dataset_id": "rwg-test-v2",
            "record_type": "hotel", "source_record_id": "crockfords",
            "payload": {"id": "crockfords", "name": "Crockfords", "room_types": [{"name": "Superior Room"}]},
        },
        {
            "property_id": "rwg-crockfords", "dataset_id": "rwg-test-v2",
            "record_type": "restaurant", "source_record_id": "eden",
            "payload": {"id": "eden", "name": "Eden by Crockfords", "location": "Level G"},
        },
        {
            "property_id": "rwg-crockfords", "dataset_id": "rwg-test-v2",
            "record_type": "faq", "source_record_id": "check-in",
            "payload": {
                "question": "What time is check-in at Crockfords?",
                "answer": "Check-in is listed at 3:00 PM.",
                "hotel_id": "crockfords",
            },
        },
    ]
    store.import_reference_knowledge_batch(rows)

    about_hotel = store.search_knowledge("rwg-crockfords", "Tell me about the hotel", include_documents=False)
    dining = store.search_knowledge("rwg-crockfords", "What restaurants are in Crockfords?", include_documents=False)
    checkin = store.search_knowledge("rwg-crockfords", "What time is check-in at Crockfords?", include_documents=False)

    assert about_hotel == []
    assert dining == []
    assert len(checkin) == 1
    assert checkin[0]["answer"] == "Check-in is listed at 3:00 PM."
    assert not checkin[0]["answer"].lstrip().startswith("{")


def test_loader_rejects_non_https_or_non_official_image_urls(tmp_path):
    package_path = _write_package(tmp_path / "bad-image.zip", image_url="http://example.test/image.jpg")
    with pytest.raises(ValueError, match="official Resorts World Genting domain"):
        load_rwg_package(package_path)


def test_import_plan_requires_a_distinct_mapping_for_every_package_hotel(tmp_path):
    package = load_rwg_package(_write_package(tmp_path / "rwg.zip"))
    with pytest.raises(ValueError, match="distinct property ID"):
        build_import_plan(package, {"hotel-a": "same", "hotel-b": "same"})
