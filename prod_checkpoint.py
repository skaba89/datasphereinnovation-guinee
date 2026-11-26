"""Compare a local review state with an independently supplied signed checkpoint.

Read-only detection, not an external anchor service or runtime authorization.
"""
import base64
import hashlib
import json
import os
import re
import sqlite3
import stat
from datetime import datetime, timezone, timedelta
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
import prod_authorization as auth
import prod_trust

FIELDS = {'schema', 'purpose', 'sequence', 'registry_sha256', 'ledger_sha256',
          'issued_at', 'expires_at'}
PURPOSE = 'DSIG-PROD-REVIEW-CHECKPOINT'


def ledger_digest(path):
    path = Path(path)
    parent, info = path.parent.lstat(), path.lstat()
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid()
            or stat.S_IMODE(parent.st_mode) != 0o700
            or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
        raise ValueError('unsafe ledger')
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=10)
    try:
        db.execute('BEGIN')
        if db.execute('PRAGMA user_version').fetchone() != (1,):
            raise ValueError('invalid version')
        if db.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
            raise ValueError('invalid ledger')
        digest = hashlib.sha256(b'DSIG-REVIEW-LEDGER-V1\x00')
        for (value,) in db.execute('SELECT payload_sha256 FROM consumed ORDER BY payload_sha256'):
            if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value):
                raise ValueError('invalid entry')
            digest.update(bytes.fromhex(value))
        return digest.hexdigest()
    finally:
        db.close()


def verify(checkpoint, *, anchor_public_key, expected_sequence, registry_bytes,
           ledger_path, now=None):
    checks = dict.fromkeys(('format', 'anchor_signature', 'sequence', 'freshness',
                            'registry_binding', 'ledger_binding'), 'FAIL')
    try:
        if (not isinstance(checkpoint, dict) or set(checkpoint) != {'payload','signature'}
                or not isinstance(anchor_public_key, bytes) or len(anchor_public_key) != 32
                or type(expected_sequence) is not int or expected_sequence < 1):
            raise ValueError('invalid checkpoint')
        p = checkpoint['payload']
        if (not isinstance(p, dict) or set(p) != FIELDS or type(p['schema']) is not int
                or p['schema'] != 1 or p['purpose'] != PURPOSE
                or type(p['sequence']) is not int or p['sequence'] < 1):
            raise ValueError('invalid payload')
        for field in ('registry_sha256','ledger_sha256'):
            if not isinstance(p[field], str) or not re.fullmatch(r'[0-9a-f]{64}', p[field]):
                raise ValueError('invalid digest')
        issued, expires = auth.timestamp(p['issued_at']), auth.timestamp(p['expires_at'])
        sig = base64.b64decode(checkpoint['signature'], validate=True)
        if len(sig) != 64:
            raise ValueError('invalid signature')
        checks['format'] = 'PASS'
        Ed25519PublicKey.from_public_bytes(anchor_public_key).verify(sig, auth.canonical(p))
        checks['anchor_signature'] = 'PASS'
        checks['sequence'] = 'PASS' if p['sequence'] == expected_sequence else 'FAIL'
        current = datetime.now(timezone.utc) if now is None else now
        if issued <= current < expires and timedelta(0) < expires-issued <= timedelta(hours=24):
            checks['freshness'] = 'PASS'
        if (isinstance(registry_bytes, bytes) and 0 < len(registry_bytes) <= prod_trust.MAX_REGISTRY_BYTES
                and hashlib.sha256(registry_bytes).hexdigest() == p['registry_sha256']):
            checks['registry_binding'] = 'PASS'
        if ledger_digest(ledger_path) == p['ledger_sha256']:
            checks['ledger_binding'] = 'PASS'
    except (ValueError, TypeError, KeyError, OSError, sqlite3.Error, InvalidSignature, OverflowError):
        pass
    return {'status':'PASS' if all(v=='PASS' for v in checks.values()) else 'FAIL',
            'checks':checks,'production_authorized':False}
