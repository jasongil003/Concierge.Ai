"""Bounded TCP probes with a bind check before declaring a local port free."""

import errno
import socket


PORT_PROBE_TIMEOUT = 1.0
_UNSUPPORTED = {errno.EAFNOSUPPORT, errno.EPROTONOSUPPORT, errno.EADDRNOTAVAIL}


class PortProbeError(RuntimeError):
    pass


def port_in_use(host: str = "127.0.0.1", port: int = 8080) -> bool:
    candidates = [(socket.AF_INET, host)]
    if host == "127.0.0.1":
        candidates.append((socket.AF_INET6, "::1"))
    checked = False
    for family, address in candidates:
        try:
            with socket.socket(family, socket.SOCK_STREAM) as probe:
                probe.settimeout(PORT_PROBE_TIMEOUT)
                try:
                    if probe.connect_ex((address, port)) == 0:
                        return True
                except TimeoutError:
                    pass
            # WSL mirrored networking can silently drop loopback connects.
            # A timeout/refusal alone cannot establish availability. Do not set
            # SO_REUSEADDR: an existing bound socket must make this check fail.
            with socket.socket(family, socket.SOCK_STREAM) as probe:
                probe.bind((address, port))
            checked = True
        except OSError as exc:
            if exc.errno == errno.EADDRINUSE:
                return True
            if family == socket.AF_INET6 and exc.errno in _UNSUPPORTED:
                continue
            raise PortProbeError(f"Port {port} availability is indeterminate; resolve the local socket error before installing.") from None
    if not checked:
        raise PortProbeError(f"Port {port} availability could not be established.")
    return False
