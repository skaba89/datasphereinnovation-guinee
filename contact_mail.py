"""Durable REC-only contact notifications. No prospect data leaves REC."""
import json
import re
import time
import urllib.request
import urllib.error


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, 'Redirect refused', headers, fp)


def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS contact_mail (
        request_id TEXT NOT NULL REFERENCES requests(id), kind TEXT NOT NULL,
        language TEXT NOT NULL, created REAL NOT NULL, next_attempt REAL NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT 'PENDING',
        provider_id TEXT, PRIMARY KEY(request_id,kind))''')


def enqueue(db, request_id, language):
    now = time.time()
    db.executemany('INSERT INTO contact_mail(request_id,kind,language,created,next_attempt) VALUES (?,?,?,?,?)',
                   [(request_id, kind, language, now, now) for kind in ('internal','ack')])


def config(raw):
    if not isinstance(raw, dict) or set(raw) != {'api_key','sender','test_recipient'}:
        raise ValueError('Invalid mail configuration')
    address = r'[A-Za-z0-9.!+_-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
    if not all(isinstance(v,str) for v in raw.values()) or not re.fullmatch(r're_[A-Za-z0-9_-]+',raw['api_key']) or not all(re.fullmatch(address,raw[k]) for k in ('sender','test_recipient')) or not raw['sender'].lower().endswith('@dsig-consulting.com'):
        raise ValueError('Invalid mail configuration')
    return raw


def send(cfg, rid, kind, language):
    if kind == 'internal':
        subject, body = '[REC] Nouvelle demande DSIG', f'Consultez le CRM REC. Référence : {rid}'
    elif language == 'en':
        subject, body = '[REC TEST] DSIG request received', f'Thank you for your request. Reference: {rid}. Our team will review it.'
    else:
        subject, body = '[REC TEST] DSIG demande reçue', f'Merci pour votre demande. Référence : {rid}. Notre équipe va l’étudier.'
    payload = json.dumps({'from':cfg['sender'],'to':[cfg['test_recipient']],'subject':subject,'text':body}).encode()
    req = urllib.request.Request('https://api.resend.com/emails', data=payload, headers={'Authorization':'Bearer '+cfg['api_key'],'Content-Type':'application/json','User-Agent':'DSIG-REC/1.0','Idempotency-Key':f'dsig-rec/{rid}/{kind}'}, method='POST')
    with urllib.request.build_opener(NoRedirect).open(req, timeout=15) as response:
        identifier = json.loads(response.read(4096))['id']
    if not isinstance(identifier,str) or not re.fullmatch(r'[A-Za-z0-9-]{1,100}',identifier):
        raise ValueError('Invalid provider response')
    return identifier


def run(connect, cfg, deliver=send, limit=10):
    """Claim with a lease; retry only inside Resend's 24h idempotency window."""
    cfg = config(cfg)
    counts = {'accepted':0,'retry':0,'failed':0}
    for _ in range(limit):
        now = time.time()
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE contact_mail SET state='FAILED' WHERE state='PENDING' AND (created<? OR (attempts>=5 AND next_attempt<=?))",(now-20*3600,now))
            row = db.execute("SELECT request_id,kind,language,attempts FROM contact_mail WHERE state='PENDING' AND next_attempt<=? ORDER BY created,kind LIMIT 1",(now,)).fetchone()
            if not row:
                break
            rid,kind,lang,attempts = row
            db.execute('UPDATE contact_mail SET attempts=attempts+1,next_attempt=? WHERE request_id=? AND kind=?',(now+120,rid,kind))
        try:
            identifier = deliver(cfg,rid,kind,lang)
        except (OSError, ValueError, KeyError):
            state = 'FAILED' if attempts>=4 else 'PENDING'
            with connect() as db:
                db.execute('UPDATE contact_mail SET state=?,next_attempt=? WHERE request_id=? AND kind=? AND attempts=?',(state,now+300*2**attempts,rid,kind,attempts+1))
            counts['failed' if state=='FAILED' else 'retry']+=1
        else:
            with connect() as db:
                db.execute("UPDATE contact_mail SET state='ACCEPTED',provider_id=? WHERE request_id=? AND kind=? AND attempts=?",(identifier,rid,kind,attempts+1))
            counts['accepted']+=1
    return counts
