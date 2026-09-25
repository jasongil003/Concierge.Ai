from pathlib import Path

from app.hospitality import HospitalityStore
from app.lunara_seed import PROPERTY_ID, seed_lunara_demo
from app.operations import OperationsStore
from app.properties import PropertyStore
from app.zones import ZoneStore


def test_lunara_seed_maps_property_and_is_idempotent(tmp_path: Path):
    db_path = tmp_path / "lunara.db"
    config_path = Path(__file__).parents[1] / "data" / "lunara.json"
    asset_path = Path(__file__).parents[1] / "app" / "static" / "assets" / "lunara-property-map.png"
    properties = PropertyStore(db_path)
    properties.seed_from_hotel_json(PROPERTY_ID, config_path)
    zones = ZoneStore(db_path)
    hospitality = HospitalityStore(db_path)
    operations = OperationsStore(db_path)

    result = seed_lunara_demo(properties, zones, hospitality, operations, asset_path)
    assert result == {"zones": 15, "facilities": 7, "services": 6, "faqs": 15}
    assert properties.get(PROPERTY_ID).hotel_name == "Lunara Grand Hotel & Residences"
    assert len(zones.overview(PROPERTY_ID)["zones"]) == 15
    assert len(zones.overview(PROPERTY_ID)["maps"]) == 1
    assert len(hospitality.catalog(PROPERTY_ID)["services"]) == 6
    assert len(operations.list_knowledge(PROPERTY_ID)) == 16

    assert seed_lunara_demo(properties, zones, hospitality, operations, asset_path) == {"zones": 0, "facilities": 0, "services": 0, "faqs": 0}
    assert len(zones.overview(PROPERTY_ID)["zones"]) == 15
