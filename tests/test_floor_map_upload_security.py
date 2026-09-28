import base64
from io import BytesIO

import pytest
from PIL import Image

import app.main as main_module
import app.zones as zones_module
from app.properties import PropertyRecord, PropertyStore
from app.zones import ZoneStore


def _zone_store(tmp_path, monkeypatch):
    database = tmp_path / "concierge.db"
    monkeypatch.setattr(zones_module, "UPLOAD_ROOT", tmp_path / "uploads")
    properties = PropertyStore(database)
    properties.upsert(PropertyRecord(property_id="hotel-a", hotel_name="Hotel A"))
    zones = ZoneStore(database)
    building = zones.create_building("hotel-a", {"name": "Main"})
    floor = zones.create_floor("hotel-a", {"building_id": building["building_id"], "name": "Ground"})
    return zones, floor["floor_id"]


def _upload(zones, floor_id, filename, content_type, raw):
    return zones.save_floor_map(
        "hotel-a",
        floor_id,
        {
            "filename": filename,
            "content_type": content_type,
            "content_base64": base64.b64encode(raw).decode("ascii"),
        },
    )


@pytest.mark.parametrize(
    ("content_type", "raw"),
    [
        ("image/png", b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"),
        ("image/jpeg", b"not a jpeg"),
        ("application/pdf", b"<html>not a pdf</html>"),
        ("image/svg+xml", b"<html>not an svg</html>"),
    ],
)
def test_floor_map_upload_rejects_fake_mime_signatures(tmp_path, monkeypatch, content_type, raw):
    zones, floor_id = _zone_store(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        _upload(zones, floor_id, "fake.upload", content_type, raw)


@pytest.mark.parametrize(
    "svg",
    [
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>',
        b'<svg xmlns="http://www.w3.org/2000/svg"><foreignObject><div>active</div></foreignObject></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg"><image href="https://attacker.example/pixel"/></svg>',
        b'<!DOCTYPE svg [<!ENTITY x "expanded">]><svg xmlns="http://www.w3.org/2000/svg">&x;</svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg"><style>@import url(https://attacker.example/a.css)</style></svg>',
    ],
)
def test_floor_map_upload_rejects_active_or_external_svg_content(tmp_path, monkeypatch, svg):
    zones, floor_id = _zone_store(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        _upload(zones, floor_id, "map.svg", "image/svg+xml", svg)


def test_floor_map_upload_rejects_oversized_pixel_dimensions(tmp_path, monkeypatch):
    zones, floor_id = _zone_store(tmp_path, monkeypatch)
    buffer = BytesIO()
    Image.new("1", (5500, 5500)).save(buffer, format="PNG")
    huge_png = buffer.getvalue()
    with pytest.raises(ValueError, match="30 million pixels"):
        _upload(zones, floor_id, "huge.png", "image/png", huge_png)


def test_floor_map_responses_use_sandbox_and_pdf_download(tmp_path):
    svg_response = main_module._floor_map_file_response(tmp_path / "map.svg")
    pdf_response = main_module._floor_map_file_response(tmp_path / "map.pdf")

    assert "sandbox" in svg_response.headers["content-security-policy"]
    assert "default-src 'none'" in svg_response.headers["content-security-policy"]
    assert svg_response.headers["x-content-type-options"] == "nosniff"
    assert pdf_response.headers["content-disposition"] == "attachment"
