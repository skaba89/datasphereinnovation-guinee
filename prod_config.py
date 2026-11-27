"""Offline production configuration checks. Never grants runtime authorization."""
import base64
import json
import re
import sys
from cryptography.fernet import Fernet

KEYS = ('DSIG_MFA_KEY', 'DSIG_BACKUP_KEY', 'DSIG_DOCUMENT_KEY')
ROLES = {'ADMIN', 'CLIENT', 'DIRECTION', 'CONTROLE', 'COMPTABLE', 'AUDITEUR'}
SECRET_NAMES = ('DSIG_ADMIN_TOKEN', *KEYS)
ORIGIN = 'https://app.dsig-consulting.com'


def secret_values(env):
    if not isinstance(env, dict):
        raise ValueError('invalid environment')
    if env.get('DSIG_ENV') == 'PROD':
        if 'DSIG_ADMIN_TOKEN' in env:
            raise ValueError('bootstrap forbidden')
        return encryption_values(env)
    token = env.get('DSIG_ADMIN_TOKEN', '')
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43,128}', token):
        raise ValueError('invalid token')
    raw = [token.encode('ascii'), *encryption_values(env)]
    # Compare token text and its decoded representation to encryption keys.
    try:
        decoded_token = base64.urlsafe_b64decode(token + '=' * (-len(token) % 4))
    except ValueError:
        decoded_token = b''
    if len(set(raw)) != len(raw) or decoded_token in raw[1:]:
        raise ValueError('reused key')
    return set(raw) | ({decoded_token} if decoded_token else set())


def encryption_values(env):
    raw = []
    for name in KEYS:
        value = env.get(name, '')
        if not isinstance(value, str):
            raise ValueError('invalid key')
        encoded = value.encode('ascii')
        Fernet(encoded)
        decoded = base64.urlsafe_b64decode(encoded)
        if base64.urlsafe_b64encode(decoded) != encoded:
            raise ValueError('noncanonical key')
        raw.append(decoded)
    if len(set(raw)) != len(raw):
        raise ValueError('reused key')
    return set(raw)


def local_checks(prod):
    """Validate only production-local configuration; not environment separation."""
    checks = dict.fromkeys(('mode', 'origin', 'database_path', 'mfa_policy',
                            'scanner_path', 'prod_secrets'), False)
    if isinstance(prod, dict):
        checks['mode'] = prod.get('DSIG_ENV') == 'PROD'
        checks['origin'] = prod.get('DSIG_HTTPS_ORIGIN') == ORIGIN
        checks['database_path'] = prod.get('DSIG_DB') == '/app/data/requests.sqlite3'
        roles = prod.get('DSIG_MFA_REQUIRED_ROLES', '')
        checks['mfa_policy'] = isinstance(roles, str) and ROLES <= set(roles.split(','))
        checks['scanner_path'] = prod.get('DSIG_CLAMD_SOCKET') == '/run/dsig-clamav/clamd.ctl'
        try:
            secret_values(prod)
            checks['prod_secrets'] = True
        except (ValueError, TypeError):
            pass
    return checks


def inspect_local(prod):
    checks = local_checks(prod)
    return {'status': 'PASS' if all(checks.values()) else 'FAIL',
            'checks': {k: 'PASS' if v else 'FAIL' for k, v in checks.items()},
            'reference_secrets_checked': False, 'production_authorized': False}


def inspect(prod, rec, candidate):
    checks = local_checks(prod) if all(isinstance(x, dict) for x in (prod, rec, candidate)) else local_checks(None)
    checks.update(reference_secrets=False, secret_separation=False)
    if all(isinstance(x, dict) for x in (prod, rec, candidate)):
        try:
            p = secret_values(prod)
        except (ValueError, TypeError):
            p = None
        try:
            if rec.get('DSIG_ENV') != 'REC' or candidate.get('DSIG_ENV') != 'REC':
                raise ValueError('invalid reference mode')
            if rec.get('DSIG_HTTPS_ORIGIN') != 'https://rec.dsig-consulting.com' or candidate.get('DSIG_HTTPS_ORIGIN') != 'https://candidate.invalid':
                raise ValueError('invalid reference origin')
            a, b = secret_values(rec), secret_values(candidate)
            checks['reference_secrets'] = not bool(a & b)
            checks['secret_separation'] = p is not None and not bool(p & (a | b))
        except (ValueError, TypeError):
            pass
    return {'status': 'PASS' if all(checks.values()) else 'FAIL',
            'checks': {k: 'PASS' if v else 'FAIL' for k, v in checks.items()},
            'production_authorized': False}


def main():
    try:
        data = json.load(sys.stdin)
        report = inspect(data['prod'], data['rec'], data['candidate'])
    except (ValueError, TypeError, KeyError, OSError):
        report = {'status': 'FAIL', 'checks': {'input': 'FAIL'}, 'production_authorized': False}
    print(json.dumps(report))
    return int(report['status'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
