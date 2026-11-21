#!/usr/bin/env python3
"""Aggregate REC diagnostics without deploying or exposing subprocess output."""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTAINER = 'dsig-rec-dsig-1'


def command(args):
    try:
        result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=180)
        data = json.loads(result.stdout)
        return result.returncode == 0, data
    except (OSError, subprocess.SubprocessError, ValueError):
        return False, None


def inspect(commit, run=command):
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Exact lowercase commit SHA required')
    probes = {
        'release': ([sys.executable, str(ROOT/'scripts/verify-rec-release.py'), commit],
                    lambda d: d.get('status') == 'PASS' and d.get('commit') == commit and d.get('production_authorized') is False),
        'preflight': (['docker','exec',CONTAINER,'python','preflight.py'],
                      lambda d: d.get('status') == 'PASS' and d.get('production_authorized') is False),
        'monitor': ([sys.executable, str(ROOT/'scripts/monitor-rec.py')],
                    lambda d: d.get('status') == 'PASS'),
        'antivirus': (['docker','exec',CONTAINER,'python','check_antivirus.py'],
                      lambda d: d == {'clean':'PASS','eicar_rejected':'PASS'}),
    }
    checks = {}
    for name, (args, validate) in probes.items():
        ok, data = run(args)
        checks[name] = 'PASS' if ok and isinstance(data, dict) and validate(data) else 'FAIL'
    return {
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'commit': commit,
        'checks': checks,
        'technical_status': 'PASS' if all(v == 'PASS' for v in checks.values()) else 'FAIL',
        'production_authorized': False,
        'remaining': ['CI exact SHA', 'TLS and access control', 'business acceptance and MFA',
                      'offsite backup and isolated restore', 'external alert delivery',
                      'security review and human approval'],
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('commit')
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}', args.commit):
        parser.error('Exact lowercase commit SHA required')
    report = inspect(args.commit)
    print(json.dumps(report, indent=2))
    sys.exit(int(report['technical_status'] != 'PASS'))
