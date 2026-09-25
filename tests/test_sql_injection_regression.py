from pathlib import Path

import pytest

from app.hospitality import HospitalityStore
from app.zones import ZoneStore


def test_hospitality_ownership_lookup_binds_untrusted_values(tmp_path: Path):
    store = HospitalityStore(tmp_path / "hospitality-sql-injection.db")

    # A value that would change query meaning if concatenated must stay an ordinary lookup value.
    with pytest.raises(KeyError, match="not found"):
        store._require_owned("restaurants", "restaurant_id", "' OR 1=1 --", "hotel-a")


def test_hospitality_ownership_lookup_rejects_untrusted_identifiers(tmp_path: Path):
    store = HospitalityStore(tmp_path / "hospitality-sql-identifiers.db")

    with pytest.raises(ValueError, match="Unsupported ownership lookup"):
        store._require_owned("restaurants", "restaurant_id OR 1=1 --", "r1", "hotel-a")
    with pytest.raises(ValueError, match="Unsupported ownership lookup"):
        store._require_owned("restaurants WHERE 1=1 --", "restaurant_id", "r1", "hotel-a")


def test_zone_ownership_lookup_rejects_untrusted_identifiers(tmp_path: Path):
    store = ZoneStore(tmp_path / "zones-sql-identifiers.db")

    with pytest.raises(ValueError, match="Unsupported ownership lookup"):
        store._require_owned("zones", "zone_id OR 1=1 --", "z1", "hotel-a")
    with pytest.raises(ValueError, match="Unsupported ownership lookup"):
        store._require_owned("zones; DROP TABLE zones", "zone_id", "z1", "hotel-a")
