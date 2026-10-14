import hashlib
from dataclasses import replace
from pathlib import Path
import sqlite3
import sys

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from scripts import seed_local_demo


def test_local_demo_unsets_external_provider_credentials():
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts" / "local-demo.sh").read_text(encoding="utf-8")

    assert "unset GEMINI_API_KEY OPENAI_API_KEY COMPATIBLE_API_BASE_URL COMPATIBLE_API_KEY GOOGLE_PLACES_API_KEY" in script
    assert not any("GEMINI_API_KEY=" in line for line in script.splitlines())


@pytest.mark.parametrize("value", [
    "http://127.0.0.1:8082",
    "http://127.0.0.1:8082/",
])
def test_local_demo_seed_accepts_only_the_expected_loopback_origin(value: str):
    assert seed_local_demo._is_loopback_demo_url(value)


@pytest.mark.parametrize("value", [
    "http://127.0.0.1:8082@attacker.example",
    "http://127.0.0.1.evil.example:8082",
    "http://demo@127.0.0.1:8082",
    "https://127.0.0.1:8082",
    "http://127.0.0.1:8082/admin",
    "http://127.0.0.1:8082/?next=https://attacker.example",
    "http://127.0.0.1:99999",
])
def test_local_demo_seed_rejects_non_loopback_or_ambiguous_origins(value: str):
    assert not seed_local_demo._is_loopback_demo_url(value)


def test_seed_main_rejects_userinfo_redirect_to_remote_host_before_login(monkeypatch, capsys):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("CONCIERGE_LOCAL_DEMO", "1")
    monkeypatch.setenv("APP_ENVIRONMENT", "development")
    monkeypatch.setenv("CONCIERGE_DEPLOYMENT_MODE", "source")
    monkeypatch.setenv("DB_PATH", str(root / ".local-demo" / "state" / "concierge.db"))
    monkeypatch.setenv("DATABASE_URL", "")

    class UnexpectedDemoAPI:
        def __init__(self, _base_url):
            pytest.fail("The seed script must reject the URL before attempting login.")

    monkeypatch.setattr(seed_local_demo, "DemoAPI", UnexpectedDemoAPI)
    monkeypatch.setattr(sys, "argv", [
        "seed_local_demo.py", "--base-url", "http://127.0.0.1:8082@attacker.example",
    ])
    result = seed_local_demo.main()

    assert result == 2
    assert "Refusing to send demo data outside" in capsys.readouterr().err


def test_package_importer_rejects_remote_host_before_opening_database(tmp_path, monkeypatch):
    root = tmp_path / "checkout"
    demo_dir = root / ".local-demo"
    database = demo_dir / "state" / "concierge.db"
    uploads = demo_dir / "uploads"
    database.parent.mkdir(parents=True)
    uploads.mkdir(parents=True)
    (demo_dir / "DEMO_STATE").write_text(
        f"Concierge.AI local demo state v1\nrepo={root}\n", encoding="utf-8",
    )
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE properties (property_id TEXT PRIMARY KEY)")
        db.execute("CREATE TABLE admin_users (user_id TEXT PRIMARY KEY)")
        db.execute("INSERT INTO properties (property_id) VALUES (?)", ("hotel-de-luna-demo",))

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    import import_hotel_de_luna_v2 as importer

    monkeypatch.setattr(importer, "ROOT", root)
    monkeypatch.setattr(importer, "DEMO_DIR", demo_dir)
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("CONCIERGE_LOCAL_DEMO", "1")
    monkeypatch.setenv("APP_ENVIRONMENT", "development")
    monkeypatch.setenv("CONCIERGE_DEPLOYMENT_MODE", "source")
    monkeypatch.setenv("DB_PATH", str(database))
    monkeypatch.setenv("UPLOAD_ROOT", str(uploads))
    monkeypatch.setenv("DATABASE_URL", "")

    with pytest.raises(RuntimeError, match="base URL must be an HTTP loopback address"):
        importer.require_local_demo("http://127.0.0.1:8082@attacker.example")


def test_guest_hotel_asset_route_rejects_property_directory_symlink_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    upload_root = tmp_path / "uploads"
    other_property_media = upload_root / "other-property" / "hotel_media"
    other_property_media.mkdir(parents=True)
    content = b"synthetic image bytes"
    asset_id = hashlib.sha256(content).hexdigest()
    (other_property_media / f"{asset_id}.jpg").write_bytes(content)
    (upload_root / "test-property").symlink_to(
        upload_root / "other-property", target_is_directory=True,
    )
    monkeypatch.setattr(main_module, "settings", replace(main_module.settings, upload_root=upload_root))

    with TestClient(main_module.app) as client:
        response = client.get(
            f"/api/guest/hotel-assets/{asset_id}?property_id=test-property",
        )

    assert response.status_code == 404


def test_guest_hotel_asset_route_serves_a_hash_named_asset_from_its_property_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    upload_root = tmp_path / "uploads"
    media_root = upload_root / "test-property" / "hotel_media"
    media_root.mkdir(parents=True)
    content = b"synthetic image bytes"
    asset_id = hashlib.sha256(content).hexdigest()
    (media_root / f"{asset_id}.jpg").write_bytes(content)
    monkeypatch.setattr(main_module, "settings", replace(main_module.settings, upload_root=upload_root))

    with TestClient(main_module.app) as client:
        response = client.get(
            f"/api/guest/hotel-assets/{asset_id}?property_id=test-property",
        )
        malformed = client.get(
            f"/api/guest/hotel-assets/../{asset_id}?property_id=test-property",
        )

    assert response.status_code == 200
    assert response.content == content
    assert response.headers["content-type"] == "image/jpeg"
    assert malformed.status_code == 404
