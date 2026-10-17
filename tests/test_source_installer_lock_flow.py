"""Exercise real installer lock re-execution without package/service mutations."""

import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_source_installer_reexecutes_once_and_proceeds_beyond_port_check(tmp_path):
    root = tmp_path / 'source'
    (root / 'deploy' / 'common').mkdir(parents=True)
    shutil.copy2(ROOT / 'deploy/source-install.sh', root / 'deploy/source-install.sh')
    shutil.copy2(ROOT / 'deploy/common/operation_lock.py', root / 'deploy/common/operation_lock.py')
    # Stop immediately at venv creation. No dependency, application or service
    # stages can run; only a disposable lock and trace file are created.
    fake_bin = tmp_path / 'bin'
    fake_bin.mkdir()
    trace = tmp_path / 'stages.txt'
    python_shim = fake_bin / 'python3.14'
    python_impl = fake_bin / 'python_shim.py'
    python_impl.write_text('''
import os, pathlib, sys
args = sys.argv[1:]
trace = pathlib.Path(os.environ['INSTALL_TEST_TRACE'])
if args == ['--version']:
    print('Python 3.14.0')
elif args[:2] == ['-m', 'venv']:
    pass
elif args[0].endswith('operation_lock.py'):
    with trace.open('a') as out:
        out.write('lock-entry\\n')
    os.execv(sys.executable, [sys.executable, *args])
elif args[0].endswith('source_service.py'):
    assert args[-1] == 'port-check'
    assert os.environ['CONCIERGE_OPERATION_LOCK_HELD'] == '1'
    with trace.open('a') as out:
        out.write('port-check\\n')
elif args[0].endswith('source_venv.py'):
    if args[1] == 'check':
        print('3.14')
    else:
        with trace.open('a') as out:
            out.write('virtual-environment\\n')
        sys.exit(73)
else:
    raise SystemExit('unexpected installer operation')
''')
    python_shim.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' ' + shlex.quote(str(python_impl)) + ' "$@"\n')
    python_shim.chmod(0o755)
    for name, content in {
        'git': '#!/bin/sh\nexit 0\n',
        'id': '#!/bin/sh\necho 1000\n',
        'uname': '#!/bin/sh\necho Linux\n',
    }.items():
        path = fake_bin / name
        path.write_text(content)
        path.chmod(0o755)
    environment = {
        'PATH': str(fake_bin) + os.pathsep + os.defpath,
        'HOME': str(tmp_path), 'TMPDIR': str(tmp_path),
        'INSTALL_TEST_TRACE': str(trace),
    }
    result = subprocess.run(
        ['bash', str(root / 'deploy/source-install.sh'), '--no-start', '--unattended'],
        env=environment, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 73, result.stderr
    assert trace.read_text().splitlines() == ['lock-entry', 'port-check', 'virtual-environment']
    assert 'Installation failed during virtual-environment' in result.stderr
    assert not (root / '.venv').exists()
    assert not (root / '.env').exists()
