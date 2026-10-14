#!/usr/bin/env python3
"""Create and read per-checkout passwords for the isolated local demo."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile


ACCOUNTS = {
    "admin": "demo-admin",
    "housekeeping": "demo-housekeeping",
    "restaurant_manager": "demo-sora-manager",
}


def _credential_path() -> Path:
    root = Path(__file__).resolve().parents[1]
    demo = root / ".local-demo"
    if demo.is_symlink() or demo.resolve().parent != root.resolve():
        raise RuntimeError("Refusing to store local demo credentials outside this checkout.")
    demo.mkdir(parents=True, exist_ok=True)
    path = demo / "credentials.json"
    if path.is_symlink():
        raise RuntimeError("Refusing to read a symlinked local demo credential file.")
    return path


def _new_password() -> str:
    return "D3mo-" + secrets.token_urlsafe(36) + "!"


def ensure_credentials() -> dict[str, object]:
    path = _credential_path()
    if path.exists():
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("schema_version") != 1:
            raise RuntimeError("Unsupported local demo credential file version.")
        accounts = value.get("accounts")
        if not isinstance(accounts, dict):
            raise RuntimeError("Invalid local demo credential file.")
        for key, username in ACCOUNTS.items():
            account = accounts.get(key)
            if not isinstance(account, dict) or account.get("username") != username or not isinstance(account.get("password"), str) or len(account["password"]) < 12:
                raise RuntimeError("Invalid local demo credential account entry.")
        os.chmod(path, 0o600)
        return value

    value = {
        "schema_version": 1,
        "accounts": {
            key: {"username": username, "password": _new_password()}
            for key, username in ACCOUNTS.items()
        },
    }
    descriptor, temporary = tempfile.mkstemp(prefix="credentials-", suffix=".tmp", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        Path(temporary).unlink(missing_ok=True)
        raise
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ensure", action="store_true", help="create the ignored credentials file if needed")
    parser.add_argument("--field", choices=[f"{key}_password" for key in ACCOUNTS])
    args = parser.parse_args()
    try:
        value = ensure_credentials() if args.ensure or args.field else json.loads(_credential_path().read_text(encoding="utf-8"))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"local demo credentials: {exc}", file=sys.stderr)
        return 2
    if args.field:
        account_key = args.field.removesuffix("_password")
        print(value["accounts"][account_key]["password"])
    elif args.ensure:
        print("Local demo credentials are stored in .local-demo/credentials.json (mode 0600).")
    else:
        print(json.dumps({key: account["username"] for key, account in value["accounts"].items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
