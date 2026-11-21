#!/usr/bin/env python3
"""Read-only proof of deployed application content; never a production authorization."""
import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone

# The server Dockerfile copies root Python files, requirements.txt and dist/.
REMOTE = """
import hashlib, json, pathlib, os
root = pathlib.Path('/app')
paths = [p for p in root.glob('*.py')] + [root/'requirements.txt']
paths += [p for p in (root/'dist').rglob('*') if p.is_file() or p.is_symlink()]
if any(p.is_symlink() or not p.is_file() for p in paths):
    raise RuntimeError('unexpected file type')
print(json.dumps({'environment': os.environ.get('DSIG_ENV') == 'REC',
                  'files': {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}))
"""

def invoke(args):
    return subprocess.run(args, check=True, capture_output=True, timeout=90).stdout

def included(path):
    return path.startswith('dist/') or path == 'requirements.txt' or ('/' not in path and path.endswith('.py'))

def source_manifest(commit):
    entries = invoke(['git','ls-tree','-r','-z',commit]).split(b'\x00')
    result = {}
    for entry in entries:
        if not entry:
            continue
        meta, raw = entry.split(b'\t',1)
        path = raw.decode('utf-8')
        if not included(path):
            continue
        mode, kind, blob = meta.decode('ascii').split()
        if kind != 'blob' or mode not in ('100644','100755'):
            raise ValueError('unexpected tracked file type')
        result[path] = hashlib.sha256(invoke(['git','cat-file','blob',blob])).hexdigest()
    if 'server.py' not in result or 'requirements.txt' not in result or not any(p.startswith('dist/') for p in result):
        raise ValueError('incomplete source')
    return result

def verify(commit, container):
    checks = {'source_manifest': 'FAIL', 'container_rec': 'FAIL', 'content_matches': 'FAIL',
              'container_healthy': 'FAIL'}
    count = 0
    try:
        expected = source_manifest(commit)
        count = len(expected)
        checks['source_manifest'] = 'PASS'
        deployed = json.loads(invoke(['docker','exec',container,'python','-c',REMOTE]))
        checks['container_rec'] = 'PASS' if deployed.get('environment') is True else 'FAIL'
        checks['content_matches'] = 'PASS' if deployed.get('files') == expected else 'FAIL'
        health = invoke(['docker','inspect','--format','{{.State.Health.Status}}',container]).decode().strip()
        checks['container_healthy'] = 'PASS' if health == 'healthy' else 'FAIL'
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, AttributeError):
        pass
    return {'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'commit': commit,
            'container': container, 'file_count': count, 'checks': checks,
            'status': 'PASS' if all(v == 'PASS' for v in checks.values()) else 'FAIL',
            'production_authorized': False,
            'manual_gates': ['CI exact SHA','TLS and access restriction','MFA and business acceptance',
                             'antivirus','backup and isolated application restore','security and human approval']}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('commit', help='Exact 40-character Git commit SHA')
    parser.add_argument('--container', choices=('dsig-rec-dsig-1','dsig-ci'), default='dsig-rec-dsig-1')
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}',args.commit):
        parser.error('Exact lowercase commit SHA required')
    report = verify(args.commit,args.container)
    print(json.dumps(report, indent=2))
    raise SystemExit(int(report['status'] != 'PASS'))
