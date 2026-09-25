from __future__ import annotations

import csv
from pathlib import Path
import sys


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python loadtest/assert_smoke.py <locust-stats-csv>")
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
    print(f"Load smoke passed: {requests} requests; {failures} failures.")


if __name__ == "__main__":
    main()
