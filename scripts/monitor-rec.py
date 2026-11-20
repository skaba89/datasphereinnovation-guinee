#!/usr/bin/env python3
"""Local REC monitoring. No secret values or subprocess output in reports."""
import json
import os
import shutil
import stat
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen

CONTAINER = 'dsig-rec-dsig-1'
MAX_BACKUP_AGE = 26 * 3600


def command(args):
    try:
        return subprocess.run(args, capture_output=True, text=True, check=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def endpoint(path, expected):
    try:
        with urlopen('http://127.0.0.1:8300/api/' + path, timeout=5) as response:
            return response.status == 200 and json.loads(response.read(4096)).get('status') == expected
    except (OSError, ValueError, AttributeError):
        return False


def backup_recent(directory, now):
    try:
        if directory.is_symlink() or stat.S_IMODE(directory.stat().st_mode) != 0o700:
            return False
        for path in directory.glob('dsig-rec-*.dsigbak'):
            info = path.lstat()
            if (stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
                    and info.st_size > 0 and 0 <= now - info.st_mtime <= MAX_BACKUP_AGE):
                return True
    except OSError:
        pass
    return False


def inspect():
    directory = Path(os.environ.get('DSIG_BACKUP_DIR', str(Path.home() / 'dsig-backups')))
    checks = {
        'container_healthy': command(['docker', 'inspect', '--format', '{{.State.Health.Status}}', CONTAINER]) == 'healthy',
        'api_health': endpoint('health', 'ok'),
        'api_ready': endpoint('ready', 'ready'),
        'antivirus_clean_scan': command(['docker', 'exec', CONTAINER, 'python', '-c',
                                         "import antivirus; antivirus.scan(b'DSIG monitoring')"]) is not None,
        'backup_recent': backup_recent(directory, time.time()),
    }
    disk = shutil.disk_usage('/')
    checks['disk_available'] = disk.free / disk.total >= 0.15
    return {'status': 'PASS' if all(checks.values()) else 'FAIL',
            'checks': {name: 'PASS' if value else 'FAIL' for name, value in checks.items()}}


if __name__ == '__main__':
    report = inspect()
    print(json.dumps(report))
    raise SystemExit(int(report['status'] != 'PASS'))
