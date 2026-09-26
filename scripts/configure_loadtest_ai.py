"""Point one isolated staging property at the deterministic local AI endpoint."""

from __future__ import annotations

import os
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai_providers import AIProviderStore


def main() -> None:
    if os.getenv("LOADTEST_CONFIRMATION") != "YES":
        raise SystemExit("Set LOADTEST_CONFIRMATION=YES to change the selected property's AI routing.")
    property_id = os.getenv("PROPERTY_ID", "").strip()
    endpoint_url = os.getenv("MOCK_AI_URL", "http://mock-ai:8081").strip().rstrip("/")
    if not property_id:
        raise SystemExit("PROPERTY_ID is required.")
    store = AIProviderStore(Path(os.getenv("DB_PATH", "state/concierge.db")))
    current = store.get_settings(property_id)
    store.save_settings(
        property_id,
        {
            "organization_default_provider": current["organization_default_provider"],
            "default_provider": "local",
            "routing_mode": "fixed",
            "local_only": True,
            "fallback_chain": [],
            "limits": current["limits"],
        },
    )
    store.save_connection(
        property_id,
        "local",
        {
            "enabled": True,
            "auth_method": "none",
            "selected_model": "concierge-loadtest",
            "endpoint_url": endpoint_url,
            "timeout_seconds": 10,
            "max_output_tokens": 48,
        },
    )
    print(f"Configured deterministic AI for property {property_id}.")


if __name__ == "__main__":
    main()
