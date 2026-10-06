#!/usr/bin/env python3
"""Classify whether the prior application release is safe to resume."""

from __future__ import annotations

import argparse


def rollback_decision(*, pointer_restored: bool, service_started: bool, health_passed: bool) -> str:
    if not pointer_restored:
        return "pointer_restore_failed"
    if not service_started:
        return "previous_release_start_failed"
    if not health_passed:
        return "previous_release_unhealthy"
    return "rollback_success"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pointer-restored", choices=("yes", "no"), required=True)
    parser.add_argument("--service-started", choices=("yes", "no"), required=True)
    parser.add_argument("--health-passed", choices=("yes", "no"), required=True)
    args = parser.parse_args()
    print(rollback_decision(
        pointer_restored=args.pointer_restored == "yes",
        service_started=args.service_started == "yes",
        health_passed=args.health_passed == "yes",
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
