"""Transactional named-account bootstrap primitive for isolated qualification only."""
import re
import secrets
import sqlite3
import uuid

import accounts

EMPTY_TABLES = ('accounts', 'credentials', 'sessions', 'mfa', 'recovery_codes',
                'archived_accounts', 'access_events')


def initialize_review(db, usernames):
    """Caller supplies an isolated, initialized database; never opens a DB or sends keys."""
    if (not isinstance(usernames, list) or not 2 <= len(usernames) <= 5
            or any(not isinstance(u, str) or not re.fullmatch(
                r'[A-Za-z][A-Za-z0-9_-]{1,30}\.[A-Za-z][A-Za-z0-9_-]{1,30}', u)
                   for u in usernames)
            or len({u.lower() for u in usernames}) != len(usernames)):
        raise ValueError('named administrator list required')
    if db.in_transaction:
        raise ValueError('exclusive transaction required')
    db.execute('BEGIN IMMEDIATE')
    try:
        for table in EMPTY_TABLES:
            if db.execute('SELECT 1 FROM '+table+' LIMIT 1').fetchone():
                raise ValueError('account state not empty')
        db.execute('CREATE TABLE IF NOT EXISTS named_bootstrap_review '
                   '(id INTEGER PRIMARY KEY CHECK(id=1), completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
        db.execute('INSERT INTO named_bootstrap_review(id) VALUES(1)')
        result=[]
        for username in usernames:
            oid=str(uuid.uuid4())
            key='dsig_'+secrets.token_urlsafe(32)
            db.execute('INSERT INTO accounts(id,username,role,key_hash) VALUES(?,?,?,?)',
                       (oid,username,'ADMIN',accounts.digest(key)))
            accounts.event(db,'named-bootstrap-review','COMPTE_CREE',username)
            result.append({'id':oid,'username':username,'activation_key':key})
        db.commit()
        # Raw activation keys are returned once to the trusted caller only.
        return result
    except BaseException:
        db.rollback()
        raise


def readiness(db):
    """Counts only; no authorization to start or access PROD."""
    checks=dict.fromkeys(('bootstrap_record','named_admins','passwords','mfa','recovery'), 'FAIL')
    try:
        if db.execute('SELECT id FROM named_bootstrap_review').fetchall() != [(1,)]:
            return report(checks)
        checks['bootstrap_record']='PASS'
        rows=db.execute("SELECT id,username FROM accounts WHERE role='ADMIN' AND enabled=1").fetchall()
        if len(rows)<2 or any(not re.fullmatch(
                r'[A-Za-z][A-Za-z0-9_-]{1,30}\.[A-Za-z][A-Za-z0-9_-]{1,30}',u)
                               for _,u in rows):
            return report(checks)
        checks['named_admins']='PASS'
        if all(db.execute('SELECT 1 FROM credentials WHERE account_id=?',(oid,)).fetchone() for oid,_ in rows):
            checks['passwords']='PASS'
        if all(db.execute("SELECT 1 FROM mfa WHERE account_id=? AND enabled=1 AND secret LIKE 'fernet:%'",(oid,)).fetchone() for oid,_ in rows):
            checks['mfa']='PASS'
        if all(db.execute('SELECT 1 FROM recovery_codes WHERE account_id=?',(oid,)).fetchone() for oid,_ in rows):
            checks['recovery']='PASS'
    except (sqlite3.Error,ValueError,TypeError):
        pass
    return report(checks)


def report(checks):
    return {'status':'PASS' if all(v=='PASS' for v in checks.values()) else 'FAIL',
            'checks':checks,'production_authorized':False}
