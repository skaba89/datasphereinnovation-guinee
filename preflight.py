"""Read-only REC controls; no credentials or exception details in output."""
import base64
import json
import os
import stat
from pathlib import Path

from cryptography.fernet import Fernet
import accounts
import operations
import server

KEYS = ('DSIG_MFA_KEY', 'DSIG_BACKUP_KEY', 'DSIG_DOCUMENT_KEY')
ROLES = ('ADMIN', 'DIRECTION', 'CONTROLE', 'COMPTABLE', 'AUDITEUR')


def inspect():
    checks = {}
    def check(name, ok, severity='FAIL'):
        checks[name] = 'PASS' if ok else severity

    check('environment_rec', os.environ.get('DSIG_ENV') == 'REC')
    try:
        origin = bool(server.configured_origin())
    except ValueError:
        origin = False
    check('https_origin_configured', origin)
    check('admin_token_length', len(os.environ.get('DSIG_ADMIN_TOKEN', '')) >= 32)
    decoded = []
    for name in KEYS:
        try:
            key = os.environ.get(name, '').encode('ascii')
            Fernet(key)
            decoded.append(base64.urlsafe_b64decode(key))
            check(name, True)
        except (ValueError, TypeError):
            check(name, False)
    check('independent_keys', len(decoded) == len(KEYS) and len(set(decoded)) == len(KEYS))
    check('privileged_mfa_policy', all(accounts.mfa_required(role) for role in ROLES))
    try:
        operations.verify(server.DB)
        check('database_integrity', True)
    except Exception:
        check('database_integrity', False)
    try:
        check('database_permissions', stat.S_IMODE(server.DB.stat().st_mode) == 0o600)
        with operations.readonly(server.DB) as db:
            size = db.execute('PRAGMA page_count').fetchone()[0] * db.execute('PRAGMA page_size').fetchone()[0]
        check('backup_size_limit', size <= operations.MAX_DB_BYTES)
    except Exception:
        check('database_permissions', False)
        check('backup_size_limit', False)
    socket = os.environ.get('DSIG_CLAMD_SOCKET', '')
    try:
        available = bool(socket) and stat.S_ISSOCK(Path(socket).stat().st_mode)
    except OSError:
        available = False
    check('antivirus_socket_present', available, 'WARN')
    status = 'FAIL' if 'FAIL' in checks.values() else 'WARN' if 'WARN' in checks.values() else 'PASS'
    return {'status': status, 'checks': checks, 'production_authorized': False,
            'manual_gates': ['external_https_and_access_control', 'actual_mfa_login',
                             'antivirus_scan', 'isolated_backup_restore', 'business_acceptance']}


if __name__ == '__main__':
    report = inspect()
    print(json.dumps(report, indent=2))
    raise SystemExit(1 if report['status'] == 'FAIL' else 0)
