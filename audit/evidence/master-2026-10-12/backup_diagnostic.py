import runpy, tempfile
from pathlib import Path
import app.backup as backup
original = backup.subprocess.run
def capture(command, *args, **kwargs):
    result = original(command, *args, **kwargs)
    if command and command[0] == "pg_restore" and result.returncode:
        print("RESTORE DIAGNOSTIC:", (result.stderr or "")[-2500:])
    return result
backup.subprocess.run = capture
with tempfile.TemporaryDirectory(prefix="audit-backup-diagnostic-") as temporary:
    runpy.run_path("tests/test_postgres_backup_integration.py")["test_postgres_backup_restores_expected_records_to_clean_database"](Path(temporary))
