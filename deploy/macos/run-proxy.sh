#!/bin/bash
set -euo pipefail

PYTHON=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14
APP_ROOT=/opt/concierge/current
"$PYTHON" "$APP_ROOT/deploy/common/preflight.py" appliance --port 8080
exec "$PYTHON" "$APP_ROOT/deploy/common/loopback_proxy.py"
