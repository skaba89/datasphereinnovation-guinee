"""Real Compose resolution with ephemeral fictitious secrets; no container startup."""
import copy
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import prod_compose
import prod_config

IMAGE = 'dsig.invalid/app@sha256:' + 'a' * 64
PORT = 8320


def secret_env(mode, origin):
    return dict(DSIG_ENV=mode, DSIG_HTTPS_ORIGIN=origin,
                **({'DSIG_ADMIN_TOKEN':secrets.token_urlsafe(48)} if mode != 'PROD' else {}),
                **{k: Fernet.generate_key().decode() for k in prod_config.KEYS})


def resolve():
    prod = secret_env('PROD', prod_config.ORIGIN)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('DSIG_', 'COMPOSE_'))}
    for name in prod_config.KEYS:
        env[name.replace('DSIG_', 'DSIG_PROD_', 1)] = prod[name]
    env.update(DSIG_PROD_IMAGE=IMAGE, DSIG_PROD_PORT=str(PORT), DSIG_PROD_CLAMD_GID='109')
    with tempfile.TemporaryDirectory() as tmp:
        empty = Path(tmp) / 'empty.env'
        empty.touch(mode=0o600)
        result = subprocess.run(
            ['docker', 'compose', '--env-file', str(empty), '-f',
             str(ROOT / 'compose.prod.yaml'), '--profile', 'prod-review',
             'config', '--format', 'json'], cwd=ROOT, env=env,
            capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError('Compose resolution failed')
        return json.loads(result.stdout)


def check(condition, label):
    if not condition:
        raise RuntimeError(label)
    print('PASS:', label)


def main():
    c = resolve()
    report = prod_compose.validate(c, IMAGE, PORT)
    print(json.dumps(report))
    if report['status'] != 'PASS':
        # Diagnostic limited to allowlisted structural metadata, never env values.
        app = c.get('services', {}).get('app', {})
        print(json.dumps({
            'top_level_fields': sorted(c),
            'service_fields': sorted(app),
            'network_names': sorted(c.get('networks', {})),
            'network_fields': {k: sorted(v or {}) for k, v in c.get('networks', {}).items()},
            'service_network_shape': app.get('networks'),
            'command_is_null': app.get('command') is None,
            'command_is_empty_list': app.get('command') == [],
            'ipam_is_default': c.get('networks', {}).get('prod-private', {}).get('ipam') in (None, {}, {'driver':'default'}, {'config':[]}, {'driver':'default','config':[]}),
            'expected_network': {k: v for k, v in c.get('networks', {}).get('prod-private', {}).items()
                                 if k in ('name', 'internal', 'driver', 'external', 'attachable', 'enable_ipv6')}
        }))
    check(report['status'] == 'PASS' and not report['production_authorized'],
          'actual resolved topology')
    env = c['services']['app']['environment']
    rec = secret_env('REC', 'https://rec.dsig-consulting.com')
    candidate = secret_env('REC', 'https://candidate.invalid')
    report = prod_config.inspect(env, rec, candidate)
    print(json.dumps(report))
    check(report['status'] == 'PASS' and not report['production_authorized'],
          'combined configuration and distinct fictitious secrets')
    for field, value in [('privileged', True), ('entrypoint', ['python','server.py']),
                         ('network_mode', 'host')]:
        bad = copy.deepcopy(c)
        bad['services']['app'][field] = value
        check(prod_compose.validate(bad, IMAGE, PORT)['status'] == 'FAIL',
              'reject ' + field)
    bad = dict(env, DSIG_MFA_KEY=rec['DSIG_MFA_KEY'])
    check(prod_config.inspect(bad, rec, candidate)['status'] == 'FAIL',
          'reject REC key reuse')
    bad = dict(env, DSIG_ADMIN_TOKEN='synthetic')
    check(prod_config.inspect(bad, rec, candidate)['status'] == 'FAIL', 'reject generic PROD token')
    c['services']['app']['environment'] = bad
    check(prod_compose.validate(c, IMAGE, PORT)['status'] == 'FAIL', 'reject token in resolved topology')
    print('PASS: integration review only; production_authorized=false')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Never emit Compose output or exception details containing environment values.
        print('FAIL: PROD Compose integration', file=sys.stderr)
        raise SystemExit(1)
