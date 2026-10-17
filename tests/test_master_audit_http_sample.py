"""The HTTP sample's disposable children must not inherit host credentials."""

import os
import subprocess
from types import SimpleNamespace

from scripts import master_audit_http_sample as http_sample


def test_http_sample_children_do_not_receive_host_credentials(monkeypatch):
    child_environments = []

    class FakeServer:
        def __init__(self):
            self.returncode = None

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode = 0

        def wait(self, timeout=None):
            self.returncode = 0
            return self.returncode

    def fake_run(command, **kwargs):
        child_environments.append(dict(kwargs["env"]))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    def fake_popen(command, **kwargs):
        child_environments.append(dict(kwargs["env"]))
        return FakeServer()

    class FakeProcess:
        def cpu_times(self):
            return (0.1, 0.1)

        def memory_info(self):
            return SimpleNamespace(rss=1024)

    monkeypatch.setattr(http_sample.subprocess, "run", fake_run)
    monkeypatch.setattr(http_sample.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(http_sample.psutil, "Process", lambda pid: FakeProcess())
    monkeypatch.setattr(http_sample, "request", lambda *args: (1.0, 200))
    monkeypatch.setattr(http_sample.time, "sleep", lambda *args: None)
    monkeypatch.setenv(
        "CONCIERGE_SYNTHETIC_HOST_SECRET_SENTINEL",
        "synthetic-host-secret-for-isolation-test",
    )

    host_sensitive_names = {
        name for name in os.environ
        if any(marker in name.upper() for marker in ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL"))
    } - {"ADMIN_BOOTSTRAP_PASSWORD", "CREDENTIAL_ENCRYPTION_SECRET"}

    http_sample.main()

    assert len(child_environments) == 3
    assert all(
        host_sensitive_names.isdisjoint(environment)
        for environment in child_environments
    )
    assert all(
        "CONCIERGE_SYNTHETIC_HOST_SECRET_SENTINEL" not in environment
        for environment in child_environments
    )
