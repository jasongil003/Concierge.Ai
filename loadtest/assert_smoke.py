from __future__ import annotations

import csv
from pathlib import Path
import sys


def main() -> None:
    if len(sys.argv) not in {2, 3} or (len(sys.argv) == 3 and sys.argv[2] != "--require-staff-conversation"):
        raise SystemExit(
            "Usage: python loadtest/assert_smoke.py <locust-stats-csv> [--require-staff-conversation]"
        )
    path = Path(sys.argv[1])
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    aggregate = next((row for row in rows if row.get("Name") == "Aggregated"), None)
    if aggregate is None:
        raise SystemExit("Locust aggregate row is missing.")
    requests = int(aggregate.get("Request Count", "0"))
    failures = int(aggregate.get("Failure Count", "0"))
    if requests < 1 or failures:
        raise SystemExit(f"Load smoke did not meet its minimum: requests={requests}, failures={failures}.")
    if len(sys.argv) == 3:
        required_flows = {
            "GET /api/guest/conversations/{session_id}/staff-messages [no staff conversation]",
            "POST /api/guest/conversations/{session_id}/escalate [guest escalation]",
            "GET /api/guest/conversations/{session_id}/staff-messages [active staff conversation]",
        }
        by_name = {row.get("Name", ""): row for row in rows}
        missing = []
        for name in sorted(required_flows):
            row = by_name.get(name)
            if row is None or int(row.get("Request Count", "0")) < 1 or int(row.get("Failure Count", "0")):
                missing.append(name)
        if missing:
            raise SystemExit("Staff-conversation load flow is incomplete or failing: " + "; ".join(missing))
    print(f"Load smoke passed: {requests} requests; {failures} failures.")


if __name__ == "__main__":
    main()
