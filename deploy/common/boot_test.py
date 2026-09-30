#!/usr/bin/env python3
"""Record pre-reboot state and verify persistence after a real machine reboot."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--state-file", required=True)
    prepare.add_argument("--platform", required=True)
    prepare.add_argument("--version", required=True)
    prepare.add_argument("--boot-id", required=True)
    prepare.add_argument("--property-count", type=int, required=True)
    prepare.add_argument("--signature", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--state-file", required=True)
    verify.add_argument("--boot-id", required=True)
    verify.add_argument("--property-count", type=int, required=True)
    verify.add_argument("--signature", required=True)
    args = parser.parse_args()
    path = Path(args.state_file)
    if args.command == "prepare":
        if args.property_count < 1:
            parser.error("boot test requires at least one administrator-configured property")
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "status": "waiting_for_reboot",
            "platform": args.platform,
            "release": args.version,
            "boot_id_before": args.boot_id,
            "property_count": args.property_count,
            "property_signature": args.signature,
            "prepared_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(path)
        print(json.dumps({"status": record["status"], "release": args.version, "property_count": args.property_count}))
        return 0

    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(f"no valid boot-test marker exists: {exc}")
    if record.get("status") != "waiting_for_reboot":
        parser.error("boot test is not waiting for a reboot; run prepare before restarting the machine")
    checks = {
        "machine_rebooted": record.get("boot_id_before") != args.boot_id,
        "property_count_preserved": record.get("property_count") == args.property_count,
        "property_configuration_preserved": record.get("property_signature") == args.signature,
    }
    record["verified_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    record["checks"] = checks
    record["status"] = "passed" if all(checks.values()) else "failed"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    print(json.dumps({"status": record["status"], "checks": checks}, sort_keys=True))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
