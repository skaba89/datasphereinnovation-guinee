"""Durable private-release nonce reservation, separate from review ledger.

Operator-owned state, no automatic initialization or reset. Consumption does
not start the server. Local rollback/deletion by a privileged operator is
outside this ledger's trust boundary.
"""
import hashlib
import os
import sqlite3
import stat
from pathlib import Path
from datetime import datetime, timezone
import prod_authorization as auth
import prod_private_release as release

SCHEMA = "CREATE TABLE private_consumed(nonce TEXT PRIMARY KEY NOT NULL CHECK(length(nonce)=64), payload_sha256 TEXT NOT NULL UNIQUE CHECK(length(payload_sha256)=64), consumed_at TEXT NOT NULL)"

def private_parent(path):
    info = path.parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError('unsafe private ledger directory')

def initialize(path):
    path = Path(path)
    private_parent(path)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    os.close(fd)
    with sqlite3.connect(path.absolute().as_uri()+'?mode=rw', uri=True) as db:
        db.execute('PRAGMA synchronous=FULL')
        db.execute(SCHEMA)
        db.execute('PRAGMA user_version=1')
    db.close()
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def consume(path, envelope, public, *, authority_pin, **expected):
    checks = dict.fromkeys(('signature','ledger','single_use'), 'FAIL')
    if 'now' in expected:
        raise ValueError('caller clock forbidden')
    db = None
    try:
        # Freeze caller-owned payload before verification and reservation.
        import json
        envelope = json.loads(auth.canonical(envelope))
        def verify():
            return release.verify(envelope, public, authority_pin=authority_pin, **expected)['status']=='PASS'
        if not verify():
            raise ValueError('invalid private release')
        checks['signature']='PASS'
        path=Path(path)
        private_parent(path)
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1:
            raise ValueError('unsafe private ledger')
        db=sqlite3.connect(path.absolute().as_uri()+'?mode=rw',uri=True,timeout=10)
        db.execute('PRAGMA trusted_schema=OFF')
        db.execute('PRAGMA synchronous=FULL')
        db.execute('BEGIN IMMEDIATE')
        if db.execute('PRAGMA user_version').fetchone()!=(1,) or db.execute('PRAGMA quick_check').fetchall()!=[('ok',)]:
            raise ValueError('invalid ledger')
        if db.execute("SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()!=[('table','private_consumed',SCHEMA)]:
            raise ValueError('unexpected ledger schema')
        checks['ledger']='PASS'
        if not verify():
            raise ValueError('permit expired while waiting')
        p=envelope['payload']
        db.execute('INSERT INTO private_consumed VALUES (?,?,?)',(p['nonce'],hashlib.sha256(auth.canonical(p)).hexdigest(),datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')))
        db.commit()
        checks['single_use']='PASS'
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error, RuntimeError):
        if db is not None:
            db.rollback()
    finally:
        if db is not None:
            db.close()
    return dict(status='PASS' if all(v=='PASS' for v in checks.values()) else 'FAIL',checks=checks, startup_authorized=False,production_authorized=False)
