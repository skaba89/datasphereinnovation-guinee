"""Offline evidence completeness check; never authorizes production."""
import json
import re
import sys
import subprocess
from pathlib import Path

GATES = {f'G{i:02d}' for i in range(1, 11)}


def inspect(data, expected_commit=None):
    if not isinstance(data, dict):
        return False
    if not isinstance(data.get('commit'), str) or not re.fullmatch(r'[0-9a-f]{40}', data['commit']):
        return False
    if expected_commit is not None and data['commit'] != expected_commit:
        return False
    gates = data.get('gates')
    if not isinstance(gates, dict) or set(gates) != GATES:
        return False
    return all(isinstance(gate, dict) and gate.get('status') == 'PASS'
               and isinstance(gate.get('evidence'), str) and bool(gate['evidence'].strip())
               and isinstance(gate.get('reviewer'), str) and bool(gate['reviewer'].strip())
               for gate in gates.values())


def current_commit():
    try:
        return subprocess.run(['git', '-C', str(Path(__file__).resolve().parent.parent), 'rev-parse', 'HEAD'],
                              check=True, capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ''


if __name__ == '__main__':
    try:
        with open(sys.argv[1], encoding='utf-8') as source:
            complete = inspect(json.load(source), current_commit())
    except (OSError, ValueError, IndexError):
        complete = False
    print(json.dumps({'evidence_complete': complete, 'production_authorized': False}))
    raise SystemExit(0 if complete else 1)
