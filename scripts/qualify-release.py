#!/usr/bin/env python3
"""Read-only consolidation of REC evidence; never authorizes production."""
import argparse
import importlib.util
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from release_evidence import evaluate

spec = importlib.util.spec_from_file_location('release_gates', ROOT/'scripts/release-gates.py')
gates = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gates)


def qualify(sha, preflight, register, gate_data, now=None):
    now = now or datetime.now(timezone.utc)
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Exact lowercase SHA required')
    technical = False
    if isinstance(preflight, dict):
        try:
            stamp = datetime.fromisoformat(preflight['timestamp_utc'].replace('Z', '+00:00'))
            technical = (now-timedelta(hours=24) <= stamp <= now
                         and preflight.get('commit') == sha
                         and preflight.get('production_authorized') is False
                         and preflight.get('technical_status') == 'PASS'
                         and preflight.get('checks') == dict.fromkeys(('release','preflight','monitor','antivirus'),'PASS'))
        except (KeyError, AttributeError, TypeError, ValueError):
            pass
    declared = evaluate(register, sha, now)
    gate_status = {}
    supplied = gate_data.get('gates') if isinstance(gate_data, dict) and gate_data.get('commit') == sha else None
    for name in sorted(gates.GATES):
        item = supplied.get(name) if isinstance(supplied, dict) else None
        if not isinstance(item, dict):
            gate_status[name] = 'INVALID'
        elif item.get('status') in ('FAIL','NOT_RUN'):
            gate_status[name] = item['status']
        elif item.get('status') == 'PASS' and all(isinstance(item.get(k),str) and item[k].strip() for k in ('evidence','reviewer')):
            gate_status[name] = 'DECLARED_PASS'
        else:
            gate_status[name] = 'INVALID'
    complete = technical and declared['status'] == 'REVIEW_REQUIRED' and gates.inspect(gate_data,sha)
    blockers = (['technical_preflight'] if not technical else []) + [f'register:{name}' for name,status in declared['checks'].items() if status!='DECLARED_PASS'] + [f'gate:{name}' for name,status in gate_status.items() if status!='DECLARED_PASS']
    if not blockers and not complete:blockers.append('evidence_structure')
    return {'commit':sha,'environment':'REC','technical_preflight':'PASS' if technical else 'FAIL',
            'register':declared['checks'],'gates':gate_status,
            'blocking_checks':blockers,'declared_pass_count':declared['declared_pass_count'],
            'register_total':declared['total'], 'status':'REVIEW_REQUIRED' if complete else 'NO_GO', 'production_authorized':False}


def read(path):
    try:
        with open(path, encoding='utf-8') as source:
            return json.load(source)
    except (OSError, ValueError):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sha')
    parser.add_argument('--preflight', required=True)
    parser.add_argument('--register', required=True)
    parser.add_argument('--gates', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}', args.sha):
        parser.error('Exact lowercase SHA required')
    report = qualify(args.sha, read(args.preflight), read(args.register), read(args.gates))
    print(json.dumps(report, indent=2))
    return int(report['status'] == 'NO_GO')


if __name__ == '__main__':
    raise SystemExit(main())
