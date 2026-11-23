"""Durable REC-only notifications; optional fictional contact details to the test mailbox."""
import json
import contact_ack
import quote_followups
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

    db.execute('''CREATE TABLE IF NOT EXISTS contact_mail_recipient (request_id TEXT NOT NULL,kind TEXT NOT NULL,recipient TEXT NOT NULL, PRIMARY KEY(request_id,kind))''')
    db.execute('''CREATE TABLE IF NOT EXISTS contact_ack_template (request_id TEXT PRIMARY KEY REFERENCES requests(id), category TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS contact_mail_detail_mode (request_id TEXT PRIMARY KEY REFERENCES requests(id), enabled INTEGER NOT NULL)''')

    db.execute('''CREATE TABLE IF NOT EXISTS account_invitation (
        request_id TEXT PRIMARY KEY REFERENCES accounts(id), kind TEXT NOT NULL DEFAULT 'invite',
        language TEXT NOT NULL DEFAULT 'fr', created REAL NOT NULL, next_attempt REAL NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT 'PENDING', provider_id TEXT)''')


def enqueue_invitation(db, account_id):
    now = time.time()
    return db.execute('INSERT OR IGNORE INTO account_invitation(request_id,created,next_attempt) VALUES (?,?,?)',(account_id,now,now)).rowcount == 1


def enqueue(db, request_id, language, category=None):
    if category in contact_ack.TYPES:
        db.execute('INSERT INTO contact_ack_template VALUES (?,?)',(request_id,category))
    now = time.time()
    db.executemany('INSERT INTO contact_mail(request_id,kind,language,created,next_attempt) VALUES (?,?,?,?,?)',
                   [(request_id, kind, language, now, now) for kind in ('internal','ack')])


def enqueue_status(db, request_id, event_id, status):
    row=db.execute("SELECT language FROM contact_mail WHERE request_id=? AND kind='ack'",(request_id,)).fetchone()
    if row:
        now=time.time()
        db.execute('INSERT INTO contact_mail(request_id,kind,language,created,next_attempt) VALUES (?,?,?,?,?)',(request_id,f'status-{event_id}-{status}',row[0],now,now))


def config(raw):
    if not isinstance(raw, dict) or not {'api_key','sender','test_recipient'} <= set(raw) or set(raw)-{'api_key','sender','test_recipient','include_contact_details','rec_customer_recipients'}:
        raise ValueError('Invalid mail configuration')
    address = r'[A-Za-z0-9.!+_-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
    if not isinstance(raw.get('include_contact_details',False),bool) or not all(isinstance(raw[k],str) for k in ('api_key','sender','test_recipient')) or not re.fullmatch(r're_[A-Za-z0-9_-]+',raw['api_key']) or not all(re.fullmatch(address,raw[k]) for k in ('sender','test_recipient')) or not raw['sender'].lower().endswith('@dsig-consulting.com'):
        raise ValueError('Invalid mail configuration')
    recipients=raw.get('rec_customer_recipients',[])
    if not isinstance(recipients,list) or len(recipients)>20 or not all(isinstance(x,str) and re.fullmatch(address,x) for x in recipients):raise ValueError('Invalid REC recipient allowlist')
    return raw


def send(cfg, rid, kind, language, *, details=None, category=None, recipient=None):
    html = None
    if kind == 'invite':
        subject, body = '[REC TEST] Invitation espace DSIG', 'Simulation d’invitation au portail DSIG : https://rec.dsig-consulting.com/connexion.html\nLa clé individuelle doit être transmise séparément par un canal sécurisé. Aucun compte réel ni secret dans ce message.'
    elif kind == 'internal':
        subject, body = '[REC] Nouvelle demande DSIG', f'Consultez le CRM REC. Référence : {rid}'
        if details is not None and cfg.get('include_contact_details',False):
            labels = ('Nom','Organisation','E-mail','Besoin','Solution','Message')
            body += '\n\n' + '\n'.join(f'{label} : {value}' for label,value in zip(labels,details))
            body += '\n\nTraiter dans le CRM REC : https://rec.dsig-consulting.com/admin.html'
    elif kind.startswith('status-'):
        subject,body,html=contact_ack.render_status(rid,kind.rsplit('-',1)[-1],language)
    elif kind.startswith('followup-'):
        subject,body,html=quote_followups.render(rid,language)
    elif kind == 'ack' and category in contact_ack.TYPES:
        subject, body, html = contact_ack.render(rid, category, language)
    elif language == 'en':
        subject, body = '[REC TEST] DSIG request received', f'Thank you for your request. Reference: {rid}. Our team will review it.'
    else:
        subject, body = '[REC TEST] DSIG demande reçue', f'Merci pour votre demande. Référence : {rid}. Notre équipe va l’étudier.'
    destination=cfg['test_recipient']
    if recipient is not None and (kind=='ack' or kind.startswith(('status-','followup-'))):
        if recipient.casefold() not in {x.casefold() for x in cfg.get('rec_customer_recipients',[])} and recipient!=destination:raise ValueError('Recipient not authorised')
        destination=recipient
    message = {'from':cfg['sender'],'to':[destination],'subject':subject,'text':body}
    if html is not None:message['html']=html
    payload = json.dumps(message).encode()
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
            category = None
            recipient = None
            if not invitations and (kind=='ack' or kind.startswith(('status-','followup-'))):
                allowed=cfg.get('rec_customer_recipients',[])
                saved=db.execute('SELECT recipient FROM contact_mail_recipient WHERE request_id=? AND kind=?',(rid,kind)).fetchone()
                if saved:recipient=saved[0]
                elif allowed and attempts==0:
                    row_email=db.execute('SELECT email FROM requests WHERE id=?',(rid,)).fetchone()
                    recipient=next((x for x in allowed if row_email and x.casefold()==row_email[0].casefold()),cfg['test_recipient'])
                    db.execute('INSERT INTO contact_mail_recipient VALUES (?,?,?)',(rid,kind,recipient))
                if recipient is not None and recipient!=cfg['test_recipient'] and recipient.casefold() not in {x.casefold() for x in allowed}:
                    db.execute("UPDATE contact_mail SET state='FAILED' WHERE request_id=? AND kind=?",(rid,kind));counts['failed']+=1;continue
            if not invitations and kind=='ack':
                template=db.execute('SELECT category FROM contact_ack_template WHERE request_id=?',(rid,)).fetchone()
                if template:category=template[0]
            if not invitations and kind=='internal':
                db.execute('INSERT OR IGNORE INTO contact_mail_detail_mode VALUES (?,?)',(rid,int(attempts==0 and cfg.get('include_contact_details',False))))
                mode=db.execute('SELECT enabled FROM contact_mail_detail_mode WHERE request_id=?',(rid,)).fetchone()[0]
                if mode:
                    if not cfg.get('include_contact_details',False):
                        db.execute("UPDATE contact_mail SET state='FAILED' WHERE request_id=? AND kind=?",(rid,kind));counts['failed']+=1;continue
                    details=db.execute('SELECT nom,org,email,besoin,solution,message FROM requests WHERE id=?',(rid,)).fetchone()
            db.execute(f'UPDATE {table} SET attempts=attempts+1,next_attempt=? WHERE request_id=? AND kind=?',(now+120,rid,kind))
        try:
            kwargs={}
            if details is not None:kwargs['details']=tuple(details)
            if category is not None:kwargs['category']=category
            if recipient is not None:kwargs['recipient']=recipient
            identifier = deliver(cfg,rid,kind,lang,**kwargs)
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
