"""Durable V2 reservation; never starts a container or grants runtime access."""
import hashlib
import json
import os
import sqlite3
import stat
from pathlib import Path
from datetime import datetime, timezone
from contextlib import closing
import prod_authorization as auth
import prod_private_runtime_contract as contract
from prod_private_replay import private_parent

SCHEMA="CREATE TABLE runtime_consumed(nonce TEXT PRIMARY KEY NOT NULL CHECK(length(nonce)=64), payload_sha256 TEXT NOT NULL UNIQUE CHECK(length(payload_sha256)=64), container_id TEXT NOT NULL CHECK(length(container_id)=64), consumed_at TEXT NOT NULL)"

def initialize(path):
    path=Path(path)
    private_parent(path)
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    os.close(fd)
    with closing(sqlite3.connect(path.absolute().as_uri()+'?mode=rw',uri=True)) as db:
        db.execute('PRAGMA synchronous=FULL')
        db.execute('BEGIN IMMEDIATE')
        db.execute(SCHEMA)
        db.execute('PRAGMA user_version=2')
        db.commit()
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def consume(path,envelope,public,*,authority_pin,expected):
    checks=dict.fromkeys(('signature','ledger','single_use'),'FAIL')
    result=dict(status='FAIL',checks=checks,nonce_consumed=False,
                startup_authorized=False,production_authorized=False)
    try:
        envelope=json.loads(auth.canonical(envelope))
        expected=json.loads(auth.canonical(expected))
        def valid():
            return contract.verify(envelope,public,authority_pin=authority_pin,expected=expected)['status']=='PASS'
        if not valid():
            return result
        checks['signature']='PASS'
        path=Path(path)
        private_parent(path)
        info=path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid()
                or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1):
            return result
        with closing(sqlite3.connect(path.absolute().as_uri()+'?mode=rw',uri=True,timeout=10)) as db:
            db.execute('PRAGMA trusted_schema=OFF')
            db.execute('PRAGMA synchronous=FULL')
            with db:
                db.execute('BEGIN IMMEDIATE')
                if db.execute('PRAGMA user_version').fetchone()!=(2,) or db.execute('PRAGMA quick_check').fetchall()!=[('ok',)]:
                    return result
                if db.execute("SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()!=[('table','runtime_consumed',SCHEMA)]:
                    return result
                current=path.lstat()
                if (current.st_dev,current.st_ino)!=(info.st_dev,info.st_ino):
                    return result
                checks['ledger']='PASS'
                if not valid():
                    return result
                p=envelope['payload']
                db.execute('INSERT INTO runtime_consumed VALUES (?,?,?,?)',
                    (p['nonce'],hashlib.sha256(auth.canonical(p)).hexdigest(),
                     p['container_id'],datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')))
            checks['single_use']='PASS'
            result.update(status='PASS',nonce_consumed=True)
    except (OSError,ValueError,TypeError,KeyError,sqlite3.Error,RuntimeError):
        pass
    return result
