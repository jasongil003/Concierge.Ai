"""Synthetic security/installer regressions; no Git mutations or real credentials."""

import errno
import json
from pathlib import Path
import subprocess
import traceback

import pytest

from app import backup
from deploy import source_install, source_service
from deploy.common import diagnostics, port_probe, preflight, runtime_environment
from scripts import history_preservation as history


def test_diagnostic_selected_config_wins_over_unrelated_shell(tmp_path, monkeypatch):
    config = tmp_path / 'deployment.env'
    config.write_text('DATABASE_URL=postgresql://db.example.test/concierge\n')
    monkeypatch.setenv('DATABASE_URL', '')
    assert diagnostics.read_config(config)['DATABASE_URL'].startswith('postgresql:')
    config.write_text('DATABASE_URL=\n')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://unrelated.example.test/db')
    assert diagnostics.read_config(config)['DATABASE_URL'] == ''


@pytest.mark.parametrize('outcome', [errno.ECONNREFUSED, errno.ETIMEDOUT, TimeoutError()])
@pytest.mark.parametrize('busy', [False, True])
def test_bounded_probe_confirms_bind_after_refusal_or_timeout(monkeypatch, outcome, busy):
    opened, closed, timeouts, bound = [], [], [], []

    class Probe:
        def __init__(self, family, _kind):
            self.family = family
            opened.append(self)
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            closed.append(self)
        def settimeout(self, value):
            timeouts.append(value)
        def connect_ex(self, _address):
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        def bind(self, address):
            bound.append(address)
            if busy:
                raise OSError(errno.EADDRINUSE, 'occupied')

    monkeypatch.setattr(port_probe.socket, 'socket', Probe)
    assert source_service.port_in_use() is busy
    assert bound
    assert all(value == 1.0 for value in timeouts)
    assert opened == closed
    if not busy:
        assert [address[0] for address in bound] == ['127.0.0.1', '::1']


def test_unknown_probe_blocks_both_installers(monkeypatch):
    def unavailable(*_args):
        raise OSError(errno.EACCES, 'restricted')
    monkeypatch.setattr(port_probe.socket, 'socket', unavailable)
    with pytest.raises(source_service.ServiceError, match='indeterminate'):
        source_service.port_in_use()
    assert preflight._listener(8080) is True


def test_ipv6_only_listener_is_detected_and_sockets_closed(monkeypatch):
    closed = []
    class Probe:
        def __init__(self, family, _kind):
            self.family = family
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            closed.append(self.family)
        def settimeout(self, _value):
            pass
        def connect_ex(self, _address):
            return 0 if self.family == port_probe.socket.AF_INET6 else errno.ECONNREFUSED
        def bind(self, _address):
            pass
    monkeypatch.setattr(port_probe.socket, 'socket', Probe)
    assert source_service.port_in_use()
    assert len(closed) == 3


def test_unsupported_ipv6_does_not_block_verified_ipv4(monkeypatch):
    class Probe:
        def __init__(self, family, _kind):
            if family == port_probe.socket.AF_INET6:
                raise OSError(errno.EAFNOSUPPORT, 'IPv6 unavailable')
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            pass
        def settimeout(self, _value):
            pass
        def connect_ex(self, _address):
            return errno.ECONNREFUSED
        def bind(self, _address):
            pass
    monkeypatch.setattr(port_probe.socket, 'socket', Probe)
    assert source_service.port_in_use() is False


def test_application_children_accept_config_without_unrelated_host_credentials(monkeypatch):
    monkeypatch.setenv('DO_NOT_PROPAGATE_SENTINEL', 'synthetic-parent-value')
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-configured-provider')
    monkeypatch.setenv('PYTHONPATH', '/untrusted/python')
    environment = runtime_environment.application_environment({'DATABASE_URL': 'postgresql://db.example.test/db'})
    assert 'DO_NOT_PROPAGATE_SENTINEL' not in environment
    assert 'PYTHONPATH' not in environment
    assert environment['OPENAI_API_KEY'] == 'synthetic-configured-provider'
    assert environment['DATABASE_URL'] == 'postgresql://db.example.test/db'
    assert environment['PATH']


def test_validate_source_configuration_isolates_actual_child(tmp_path, monkeypatch):
    (tmp_path / '.env').write_text('CREDENTIAL_ENCRYPTION_SECRET=' + 'a' * 48 + '\nADMIN_BOOTSTRAP_USERNAME=admin\nADMIN_BOOTSTRAP_PASSWORD=TestOnly-123!\n')
    monkeypatch.setenv('DO_NOT_PROPAGATE_SENTINEL', 'synthetic-parent-value')
    captured = []
    source_install.validate_configuration(tmp_path, Path('/synthetic/python'), runner=lambda _cmd, **kw: captured.append(kw['env']))
    assert len(captured) == 1
    assert 'DO_NOT_PROPAGATE_SENTINEL' not in captured[0]


def test_postgres_explicit_authentication_and_url_precedence(monkeypatch):
    monkeypatch.setenv('DO_NOT_PROPAGATE_SENTINEL', 'synthetic-parent-value')
    monkeypatch.setenv('PGPASSFILE', '/private/authorized.pgpass')
    monkeypatch.setenv('PGSSLROOTCERT', '/private/root.crt')
    monkeypatch.setenv('PGHOST', 'unrelated-host')
    switches, environment = backup._postgres_environment('postgresql://db.example.test/db?sslmode=verify-full')
    assert switches == ['--no-password']
    assert environment['PGPASSFILE'] == '/private/authorized.pgpass'
    assert environment['PGSSLMODE'] == 'verify-full'
    assert environment['PGSSLROOTCERT'] == '/private/root.crt'
    assert environment['PGHOST'] == 'db.example.test'
    assert 'DO_NOT_PROPAGATE_SENTINEL' not in environment
    _, override = backup._postgres_environment('postgresql://db.example.test/db?passfile=/other/authorized.pgpass')
    assert override['PGPASSFILE'] == '/other/authorized.pgpass'


@pytest.mark.parametrize('mode', ['timeout', 'exit', 'missing'])
def test_postgres_failures_suppress_subprocess_diagnostics(monkeypatch, tmp_path, capsys, mode):
    sentinel = 'DO_NOT_PROPAGATE_SENTINEL'
    def run(argv, **kwargs):
        assert sentinel not in kwargs['env']
        if mode == 'timeout':
            raise subprocess.TimeoutExpired(argv, 1, output=sentinel, stderr=sentinel)
        if mode == 'missing':
            raise FileNotFoundError(sentinel)
        return subprocess.CompletedProcess(argv, 1, sentinel, sentinel)
    monkeypatch.setattr(backup.subprocess, 'run', run)
    monkeypatch.setenv(sentinel, sentinel)
    with pytest.raises(RuntimeError) as caught:
        backup._pg_dump('postgresql://db.example.test/db', tmp_path / 'backup.dump')
    output = capsys.readouterr()
    assert sentinel not in output.out + output.err + ''.join(traceback.format_exception(caught.value))


@pytest.mark.parametrize('local,remote,expected', [
    ('a', 'a', False), ('a', 'b', True), ('a', None, False), (None, 'b', False),
])
def test_reference_collision_preflight(local, remote, expected):
    rows = []
    if local:
        rows.append(('refs/heads/main', local * 40))
    if remote:
        rows.append(('refs/remotes/origin/main', remote * 40))
    assert bool(history.divergent_refs(rows)) is expected


def test_known_five_commit_loss_collision_fails_before_filtering(monkeypatch, tmp_path):
    local = '7185e18df2ae3b8f100804b7c3618a3909a831b6'
    remote = 'f4287c20febb4023179a1040540c244db4b223ec'
    rows = f'refs/heads/codex/ecc-closeout-20261019 {local}\nrefs/remotes/origin/codex/ecc-closeout-20261019 {remote}'
    monkeypatch.setattr(history, 'git_read', lambda *_args: rows)
    with pytest.raises(SystemExit, match='divergent branch tips'):
        history.preflight(tmp_path)


def preservation_fixture(tmp_path, monkeypatch, lost=False, wrong_set=False, wrong_parent=False):
    old = [f'{index:040x}' for index in range(1, 7)]
    new = [f'{index:040x}' for index in range(11, 17)]
    metadata = tmp_path / 'filter-repo'
    metadata.mkdir()
    (metadata / 'commit-map').write_text('old new\n' + ''.join(f'{a} {b if not lost or i == 0 else "0" * 40}\n' for i, (a, b) in enumerate(zip(old, new))))
    (metadata / 'ref-map').write_text(f'old new ref\n{old[0]} {new[0]} refs/heads/main\n')
    refs = tmp_path / 'refs.tsv'
    refs.write_text(f'refs/heads/main\tcommit\t{old[0]}\t{old[0]}\t6\n')
    commits = tmp_path / 'commits.tsv'
    commits.write_text(''.join(f'refs/heads/main\t{sha}\n' for sha in old))
    (tmp_path / 'source-inventory.json').write_text(json.dumps([{'ref': 'refs/heads/main', 'type': 'commit', 'commits': [f'{old[i]} {old[i+1]}' if i < 5 else old[i] for i in range(6)]}]))
    def git(command, **_kwargs):
        args = command[3:]
        if args[0] == 'rev-parse':
            stdout = new[0]
        elif args[0] == 'cat-file':
            stdout = 'commit'
        elif args[0] == 'rev-list':
            stdout = '\n'.join(new[:-1] + ['f' * 40] if wrong_set else new)
        elif args[0] == 'show':
            index = new.index(args[-1])
            stdout = '' if wrong_parent or index == 5 else new[index+1]
        elif args[0] == 'for-each-ref':
            stdout = 'refs/heads/main'
        else:
            raise AssertionError('unexpected read-only git operation')
        return subprocess.CompletedProcess(command, 0, stdout, '')
    monkeypatch.setattr(history.subprocess, 'run', git)
    return refs, commits


@pytest.mark.parametrize('failure', [None, 'lost', 'wrong_set', 'wrong_parent'])
def test_preservation_gate_validates_counts_sets_and_topology(tmp_path, monkeypatch, failure):
    refs, commits = preservation_fixture(tmp_path, monkeypatch, **({failure: True} if failure else {}))
    if failure:
        with pytest.raises(SystemExit, match='FAILED'):
            history.verify(tmp_path, refs, commits)
    else:
        history.verify(tmp_path, refs, commits)


def test_fallback_service_child_does_not_inherit_unrelated_credentials(tmp_path, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setenv('DO_NOT_PROPAGATE_SENTINEL', 'synthetic-parent-value')
    monkeypatch.setattr(source_service, '_fallback_running', lambda _root: None)
    captured = []
    def popen(_cmd, **kwargs):
        captured.append(kwargs['env'])
        return SimpleNamespace(pid=123)
    monkeypatch.setattr(source_service.subprocess, 'Popen', popen)
    source_service._fallback_start(tmp_path)
    assert 'DO_NOT_PROPAGATE_SENTINEL' not in captured[0]
    assert captured[0]['CONCIERGE_DEPLOYMENT_MODE'] == 'source'


def test_remote_tracking_namespace_has_documented_destination():
    assert history.destination_ref('refs/remotes/origin/topic') == 'refs/heads/topic'
    assert history.destination_ref('refs/tags/release') == 'refs/tags/release'


def test_preservation_gate_rejects_missing_source_reference(tmp_path, monkeypatch):
    refs, commits = preservation_fixture(tmp_path, monkeypatch)
    refs.write_text('')
    with pytest.raises(SystemExit, match='omitted or duplicated'):
        history.verify(tmp_path, refs, commits)
