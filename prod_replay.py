"""Local durable single-use review ledger. Never authorizes production."""
import hashlib
import os
import sqlite3
import stat
from pathlib import Path

import prod_authorization
import prod_trust


def consume(path, envelope, registry_bytes, pinned_sha256, *, now=None, **expected):
    checks = {'trust': 'FAIL', 'ledger': 'FAIL', 'single_use': 'FAIL'}
    db = None
    try:
        report = prod_trust.verify(envelope, registry_bytes, pinned_sha256, now=now, **expected)
        if report['status'] != 'PASS':
            raise ValueError('untrusted review')
        checks['trust'] = 'PASS'
        path = Path(path)
        # Require a pre-provisioned, private ledger and directory. Never auto-reset.
        parent = path.parent.lstat()
        info = path.lstat()
        if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid()
                or stat.S_IMODE(parent.st_mode) != 0o700
                or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise ValueError('unsafe ledger')
        db = sqlite3.connect(path.resolve().as_uri() + '?mode=rw', uri=True, timeout=10)
        db.execute('PRAGMA synchronous=FULL')
        db.execute('BEGIN IMMEDIATE')
        if db.execute('PRAGMA user_version').fetchone()[0] != 1:
            raise ValueError('invalid ledger version')
        if db.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
            raise ValueError('invalid ledger integrity')
        checks['ledger'] = 'PASS'
        # Same signed payload is single-use even if signed by another trusted key.
        fingerprint = hashlib.sha256(prod_authorization.canonical(envelope['payload'])).hexdigest()
        db.execute('INSERT INTO consumed(payload_sha256) VALUES (?)', (fingerprint,))
        db.commit()
        checks['single_use'] = 'PASS'
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error, RuntimeError):
        if db is not None:
            try:
                db.rollback()
            except sqlite3.Error:
                pass
    finally:
        if db is not None:
            db.close()
    return {'status': 'PASS' if all(v == 'PASS' for v in checks.values()) else 'FAIL',
            'checks': checks, 'production_authorized': False}


def initialize(path):
    """Explicit one-time provisioning; refuses existing files. No reset command."""
    path = Path(path)
    parent = path.parent.lstat()
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid()
            or stat.S_IMODE(parent.st_mode) != 0o700):
        raise ValueError('unsafe ledger directory')
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    os.close(fd)
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=rw', uri=True)
    try:
        db.execute('PRAGMA synchronous=FULL')
        db.execute('CREATE TABLE consumed(payload_sha256 TEXT PRIMARY KEY NOT NULL CHECK(length(payload_sha256)=64))')
        db.execute('PRAGMA user_version=1')
        db.commit()
    finally:
        db.close()
