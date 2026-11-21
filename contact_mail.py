"""Durable REC-only notifications; optional fictional contact details to the test mailbox."""
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

    db.execute('''CREATE TABLE IF NOT EXISTS contact_mail_detail_mode (request_id TEXT PRIMARY KEY REFERENCES requests(id), enabled INTEGER NOT NULL)''')

    db.execute('''CREATE TABLE IF NOT EXISTS account_invitation (
        request_id TEXT PRIMARY KEY REFERENCES accounts(id), kind TEXT NOT NULL DEFAULT 'invite',
        language TEXT NOT NULL DEFAULT 'fr', created REAL NOT NULL, next_attempt REAL NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT 'PENDING', provider_id TEXT)''')


def enqueue_invitation(db, account_id):
    now = time.time()
    return db.execute('INSERT OR IGNORE INTO account_invitation(request_id,created,next_attempt) VALUES (?,?,?)',(account_id,now,now)).rowcount == 1


def enqueue(db, request_id, language):
    now = time.time()
    db.executemany('INSERT INTO contact_mail(request_id,kind,language,created,next_attempt) VALUES (?,?,?,?,?)',
                   [(request_id, kind, language, now, now) for kind in ('internal','ack')])


def config(raw):
    if not isinstance(raw, dict) or not {'api_key','sender','test_recipient'} <= set(raw) or set(raw)-{'api_key','sender','test_recipient','include_contact_details'}:
        raise ValueError('Invalid mail configuration')
    address = r'[A-Za-z0-9.!+_-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
    if not isinstance(raw.get('include_contact_details',False),bool) or not all(isinstance(raw[k],str) for k in ('api_key','sender','test_recipient')) or not re.fullmatch(r're_[A-Za-z0-9_-]+',raw['api_key']) or not all(re.fullmatch(address,raw[k]) for k in ('sender','test_recipient')) or not raw['sender'].lower().endswith('@dsig-consulting.com'):
        raise ValueError('Invalid mail configuration')
    return raw


def send(cfg, rid, kind, language, *, details=None):
    if kind == 'invite':
        subject, body = '[REC TEST] Invitation espace DSIG', 'Simulation d’invitation au portail DSIG : https://rec.dsig-consulting.com/connexion.html\nLa clé individuelle doit être transmise séparément par un canal sécurisé. Aucun compte réel ni secret dans ce message.'
    elif kind == 'internal':
        subject, body = '[REC] Nouvelle demande DSIG', f'Consultez le CRM REC. Référence : {rid}'
        if details is not None and cfg.get('include_contact_details',False):
            labels = ('Nom','Organisation','E-mail','Besoin','Solution','Message')
            body += '\n\n' + '\n'.join(f'{label} : {value}' for label,value in zip(labels,details))
            body += '\n\nTraiter dans le CRM REC : https://rec.dsig-consulting.com/admin.html'
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


def run(connect, cfg, deliver=send, limit=10, *, invitations=False):
    """Claim with a lease; retry only inside Resend's 24h idempotency window."""
    cfg = config(cfg)
    table = 'account_invitation' if invitations else 'contact_mail'
    counts = {'accepted':0,'retry':0,'failed':0}
    for _ in range(limit):
        now = time.time()
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if invitations:
                db.execute("UPDATE account_invitation SET state='CANCELLED' WHERE state='PENDING' AND (NOT EXISTS(SELECT 1 FROM accounts a WHERE a.id=request_id AND a.enabled=1) OR EXISTS(SELECT 1 FROM credentials c WHERE c.account_id=request_id))")
            db.execute(f"UPDATE {table} SET state='FAILED' WHERE state='PENDING' AND (created<? OR (attempts>=5 AND next_attempt<=?))",(now-20*3600,now))
            row = db.execute(f"SELECT request_id,kind,language,attempts FROM {table} WHERE state='PENDING' AND next_attempt<=? ORDER BY created,kind LIMIT 1",(now,)).fetchone()
            if not row:
                break
            rid,kind,lang,attempts = row
            details = None
            if not invitations and kind=='internal':
                db.execute('INSERT OR IGNORE INTO contact_mail_detail_mode VALUES (?,?)',(rid,int(attempts==0 and cfg.get('include_contact_details',False))))
                mode=db.execute('SELECT enabled FROM contact_mail_detail_mode WHERE request_id=?',(rid,)).fetchone()[0]
                if mode:
                    if not cfg.get('include_contact_details',False):
                        db.execute("UPDATE contact_mail SET state='FAILED' WHERE request_id=? AND kind=?",(rid,kind));counts['failed']+=1;continue
                    details=db.execute('SELECT nom,org,email,besoin,solution,message FROM requests WHERE id=?',(rid,)).fetchone()
            db.execute(f'UPDATE {table} SET attempts=attempts+1,next_attempt=? WHERE request_id=? AND kind=?',(now+120,rid,kind))
        try:
            identifier = deliver(cfg,rid,kind,lang,details=tuple(details)) if details is not None else deliver(cfg,rid,kind,lang)
        except (OSError, ValueError, KeyError):
            state = 'FAILED' if attempts>=4 else 'PENDING'
            with connect() as db:
                db.execute(f'UPDATE {table} SET state=?,next_attempt=? WHERE request_id=? AND kind=? AND attempts=?',(state,now+300*2**attempts,rid,kind,attempts+1))
            counts['failed' if state=='FAILED' else 'retry']+=1
        else:
            with connect() as db:
                db.execute(f"UPDATE {table} SET state='ACCEPTED',provider_id=? WHERE request_id=? AND kind=? AND attempts=?",(identifier,rid,kind,attempts+1))
            counts['accepted']+=1
    return counts
