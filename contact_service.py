"""DSIG PROD public contact service (V174) — one public endpoint, nothing else.

Architecture: the public website container (its own Caddy, not the shared proxy) forwards
POST /api/contact to this service on the private `edge` network. No REC code, database,
token or admin API is reachable from here.

Safety gates
- Submissions are refused (503) unless DSIG_CONTACT_ENABLED=1, which the operator sets only
  after the legal validations (V161) and the human approvals.
- Personal data is encrypted at rest (Fernet, DSIG_CONTACT_KEY); only the request type, date,
  language and status are stored in clear for statistics.
- Strict input validation (shared contact_form module), JSON only, 8 KB max, exact Origin,
  honeypot, per-client and global rate limits, duplicate-submission detection.
- The internal notification carries no personal data; it is queued and retried separately,
  so a mail outage never loses a request nor shows an error to the visitor.
- Logs never contain bodies, query strings or IP addresses.

Operator commands (inside the container, no network exposure):
  --list | --show ID | --set-status ID STATUS | --erase ID | --purge [--apply] | --notify (JSON config on stdin)
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import urllib.request
import uuid
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock

from cryptography.fernet import Fernet, InvalidToken

import contact_form

STATUSES = ('NOUVELLE', 'EN_COURS', 'REPONDUE', 'CLOSE')
MAX_BODY = 8192
CLIENT_LIMIT, CLIENT_WINDOW = 5, 600        # 5 requests per client per 10 minutes
GLOBAL_LIMIT, GLOBAL_WINDOW = 60, 3600      # 60 requests per hour for the whole service
DUPLICATE_WINDOW = 600                      # same email + message within 10 minutes -> same reference
ERASED = '[supprimé]'
ACK = {'fr': 'Votre demande a bien été reçue. Référence : ', 'en': 'Your request has been received. Reference: '}


def db_path():
    return os.environ.get('DSIG_CONTACT_DB', '/data/contact.sqlite3')


def connect():
    db = sqlite3.connect(db_path(), timeout=10)
    db.execute('''CREATE TABLE IF NOT EXISTS contact_requests (
        id TEXT PRIMARY KEY, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, besoin TEXT NOT NULL,
        language TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'NOUVELLE', fingerprint TEXT NOT NULL,
        payload BLOB, erased_at TEXT)''')
    db.execute('CREATE INDEX IF NOT EXISTS contact_requests_fingerprint ON contact_requests(fingerprint,created_at)')
    db.execute('''CREATE TABLE IF NOT EXISTS contact_notifications (
        request_id TEXT PRIMARY KEY, state TEXT NOT NULL DEFAULT 'PENDING', attempts INTEGER NOT NULL DEFAULT 0,
        next_attempt REAL NOT NULL DEFAULT 0, provider_id TEXT)''')
    db.execute('''CREATE TABLE IF NOT EXISTS contact_audit (
        id INTEGER PRIMARY KEY, at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, actor TEXT NOT NULL,
        action TEXT NOT NULL, request_id TEXT NOT NULL)''')
    if db.in_transaction:
        db.commit()
    return db


def cipher():
    key = os.environ.get('DSIG_CONTACT_KEY', '')
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError):
        raise SystemExit('DSIG_CONTACT_KEY manquante ou invalide (clé Fernet requise).')


def fingerprint(values):
    return hashlib.sha256((values['email'].casefold() + '\n' + values['message']).encode()).hexdigest()


def audit(db, actor, action, rid):
    db.execute('INSERT INTO contact_audit(actor,action,request_id) VALUES (?,?,?)', (actor, action, rid))


def store(values, language, fernet, now=None):
    """Persist one validated request. Returns (reference, created)."""
    now = now or time.time()
    fp = fingerprint(values)
    since = datetime.fromtimestamp(now - DUPLICATE_WINDOW, timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        existing = db.execute('SELECT id FROM contact_requests WHERE fingerprint=? AND created_at>=? AND erased_at IS NULL',
                              (fp, since)).fetchone()
        if existing:
            return existing[0], False
        rid = str(uuid.uuid4())
        personal = {k: values[k] for k in ('nom', 'org', 'email', 'telephone', 'solution', 'message')}
        db.execute('INSERT INTO contact_requests(id,besoin,language,fingerprint,payload) VALUES (?,?,?,?,?)',
                   (rid, values['besoin'], language, fp, fernet.encrypt(json.dumps(personal).encode())))
        db.execute('INSERT INTO contact_notifications(request_id,next_attempt) VALUES (?,?)', (rid, now))
        audit(db, 'public', 'DEMANDE_RECUE', rid)
    return rid, True


class RateLimiter:
    def __init__(self):
        self.lock, self.clients, self.all = Lock(), defaultdict(deque), deque()

    def allow(self, client, now=None):
        now = now or time.time()
        with self.lock:
            for bucket, window in ((self.clients[client], CLIENT_WINDOW), (self.all, GLOBAL_WINDOW)):
                while bucket and now - bucket[0] > window:
                    bucket.popleft()
            if len(self.clients[client]) >= CLIENT_LIMIT or len(self.all) >= GLOBAL_LIMIT:
                return False
            self.clients[client].append(now)
            self.all.append(now)
            if len(self.clients) > 10000:  # bound memory
                for key in [k for k, v in self.clients.items() if not v]:
                    del self.clients[key]
            return True


LIMITER = RateLimiter()


def client_address(handler):
    """Visitor IP from X-Forwarded-For, counting only the trusted proxy hops (shared proxy + website)."""
    hops = int(os.environ.get('DSIG_TRUSTED_HOPS', '2'))
    chain = [x.strip() for x in handler.headers.get('X-Forwarded-For', '').split(',') if x.strip()]
    return chain[-hops] if len(chain) >= hops else handler.client_address[0]


class Handler(BaseHTTPRequestHandler):
    server_version = 'dsig-contact'
    sys_version = ''
    timeout = 10

    def log_message(self, fmt, *args):  # no bodies, query strings or IP addresses
        sys.stderr.write('%s %s\n' % (self.command, args[1] if len(args) > 1 else '-'))

    def reply(self, status, body):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == '/healthz':
            return self.reply(200, {'status': 'ok', 'accepting': os.environ.get('DSIG_CONTACT_ENABLED') == '1'})
        return self.reply(404, {'error': 'Introuvable.'})

    def do_POST(self):
        if self.path != '/api/contact':
            return self.reply(404, {'error': 'Introuvable.'})
        if os.environ.get('DSIG_CONTACT_ENABLED') != '1':
            return self.reply(503, {'error': 'Le formulaire n’est pas encore ouvert. Écrivez-nous par e-mail.'})
        origin = os.environ.get('DSIG_CONTACT_ORIGIN', 'https://dsig-consulting.com')
        if self.headers.get('Origin') != origin or self.headers.get('Sec-Fetch-Site') == 'cross-site':
            return self.reply(403, {'error': 'Origine non autorisée.'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            length = -1
        if not 0 < length <= MAX_BODY or self.headers.get_content_type() != 'application/json':
            return self.reply(400, {'error': 'Demande invalide.'})
        raw = self.rfile.read(length)
        if not LIMITER.allow(client_address(self)):
            return self.reply(429, {'error': 'Trop de demandes. Réessayez dans quelques minutes.'})
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict) and payload.get('website'):
                # Honeypot: answer like a success, store nothing.
                return self.reply(201, {'id': str(uuid.uuid4()), 'message': ACK['fr']})
            values = contact_form.validate(payload, needs=contact_form.PUBLIC_NEEDS, demo_requires_solution=False)
        except (ValueError, TypeError, UnicodeDecodeError) as error:
            message = str(error) if isinstance(error, ValueError) and not isinstance(error, json.JSONDecodeError) else 'Demande invalide.'
            return self.reply(400, {'error': message})
        language = payload.get('language', 'fr')
        try:
            rid, created = store(values, language, cipher())
        except sqlite3.Error:
            return self.reply(503, {'error': 'Service momentanément indisponible. Écrivez-nous par e-mail.'})
        return self.reply(201 if created else 200, {'id': rid, 'message': ACK[language] + rid})


# ----- notifications (no personal data) -----

def notify(config, deliver=None, limit=20, now=None):
    """Send pending internal notifications. Config: api_key, sender, recipients (list)."""
    recipients = config.get('recipients')
    if not isinstance(recipients, list) or not 0 < len(recipients) <= 5 or not all(
            isinstance(x, str) and re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', x) for x in recipients):
        raise ValueError('recipients invalides')
    deliver = deliver or resend
    now = now or time.time()
    counts = {'sent': 0, 'retry': 0, 'failed': 0}
    with connect() as db:
        rows = db.execute('''SELECT n.request_id,n.attempts,r.besoin,r.created_at FROM contact_notifications n
            JOIN contact_requests r ON r.id=n.request_id WHERE n.state='PENDING' AND n.next_attempt<=? ORDER BY n.next_attempt LIMIT ?''',
                          (now, limit)).fetchall()
    for rid, attempts, besoin, created in rows:
        subject = f'[DSIG] Nouvelle demande de contact — {besoin}'
        text = f'Nouvelle demande reçue le {created} UTC.\nType : {besoin}\nRéférence : {rid}\n\nConsultation sur le serveur (commande --show). Aucune donnée personnelle dans cet e-mail.'
        try:
            provider = deliver(config, rid, subject, text)
        except (OSError, ValueError, KeyError):
            state = 'FAILED' if attempts >= 7 else 'PENDING'
            with connect() as db:
                db.execute('UPDATE contact_notifications SET attempts=attempts+1,state=?,next_attempt=? WHERE request_id=?',
                           (state, now + 300 * 2 ** attempts, rid))
            counts['failed' if state == 'FAILED' else 'retry'] += 1
            continue
        with connect() as db:
            db.execute("UPDATE contact_notifications SET state='SENT',attempts=attempts+1,provider_id=? WHERE request_id=?", (provider, rid))
        counts['sent'] += 1
    return counts


def resend(config, rid, subject, text):
    message = {'from': config['sender'], 'to': config['recipients'], 'subject': subject, 'text': text}
    req = urllib.request.Request('https://api.resend.com/emails', data=json.dumps(message).encode(), method='POST',
                                 headers={'Authorization': 'Bearer ' + config['api_key'], 'Content-Type': 'application/json',
                                          'User-Agent': 'DSIG-CONTACT/1.0', 'Idempotency-Key': 'dsig-contact/' + rid})
    with urllib.request.urlopen(req, timeout=15) as response:
        identifier = json.loads(response.read(4096))['id']
    if not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9-]{1,100}', identifier):
        raise ValueError('Invalid provider response')
    return identifier


# ----- operator commands -----

def show(rid, fernet, actor='operateur'):
    with connect() as db:
        row = db.execute('SELECT id,created_at,besoin,language,status,payload,erased_at FROM contact_requests WHERE id=?', (rid,)).fetchone()
        if not row:
            raise LookupError(rid)
        audit(db, actor, 'DEMANDE_CONSULTEE', rid)
    data = {'id': row[0], 'created_at': row[1], 'besoin': row[2], 'language': row[3], 'status': row[4], 'erased_at': row[6]}
    if row[5] is not None:
        try:
            data.update(json.loads(fernet.decrypt(row[5])))
        except InvalidToken:
            raise SystemExit('Clé de déchiffrement incorrecte.')
    return data


def set_status(rid, status, actor='operateur'):
    if status not in STATUSES:
        raise ValueError(status)
    with connect() as db:
        if db.execute('UPDATE contact_requests SET status=? WHERE id=?', (status, rid)).rowcount != 1:
            raise LookupError(rid)
        audit(db, actor, 'STATUT_' + status, rid)


def erase(rid, actor='operateur', reason='EFFACEMENT'):
    with connect() as db:
        if not db.execute('SELECT 1 FROM contact_requests WHERE id=?', (rid,)).fetchone():
            raise LookupError(rid)
        done = db.execute("UPDATE contact_requests SET payload=NULL,fingerprint=?,erased_at=CURRENT_TIMESTAMP WHERE id=? AND erased_at IS NULL",
                          (ERASED, rid)).rowcount == 1
        if done:
            audit(db, actor, reason, rid)
    return done


def purge(apply=False, today=None, days=None):
    days = days or int(os.environ.get('DSIG_CONTACT_RETENTION_DAYS', '1095'))
    if not 30 <= days <= 3650:
        raise ValueError('DSIG_CONTACT_RETENTION_DAYS hors bornes (30–3650)')
    limit = ((today or date.today()) - timedelta(days=days)).isoformat()
    with connect() as db:
        ids = [r[0] for r in db.execute("SELECT id FROM contact_requests WHERE erased_at IS NULL AND date(created_at)<?", (limit,))]
    erased = sum(erase(rid, 'SYSTEME:conservation', 'ANONYMISEE_CONSERVATION') for rid in ids) if apply else 0
    return {'retention_days': days, 'eligible': len(ids), 'erased': erased, 'applied': apply}


def main(argv=None):
    parser = argparse.ArgumentParser(description='DSIG PROD contact service')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--list', action='store_true')
    group.add_argument('--show')
    group.add_argument('--set-status', nargs=2, metavar=('ID', 'STATUS'))
    group.add_argument('--erase')
    group.add_argument('--purge', action='store_true')
    group.add_argument('--notify', action='store_true')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--port', type=int, default=8090)
    args = parser.parse_args(argv)
    if args.apply and not args.purge:
        parser.error('--apply exige --purge')
    if args.list:
        with connect() as db:
            for row in db.execute('SELECT id,created_at,besoin,language,status,erased_at IS NOT NULL FROM contact_requests ORDER BY created_at DESC LIMIT 200'):
                print(json.dumps(dict(zip(('id', 'created_at', 'besoin', 'language', 'status', 'erased'), row)), ensure_ascii=False))
        return
    try:
        if args.show:
            print(json.dumps(show(args.show, cipher()), ensure_ascii=False, indent=1))
        elif args.set_status:
            set_status(*args.set_status)
            print('OK')
        elif args.erase:
            print('EFFACEE' if erase(args.erase) else 'DEJA_EFFACEE')
        elif args.purge:
            print(json.dumps(purge(apply=args.apply)))
        elif args.notify:
            print(json.dumps(notify(json.loads(sys.stdin.read(4096)))))
        else:
            cipher()  # refuse to start without a valid key
            connect().close()
            server = ThreadingHTTPServer(('0.0.0.0' if os.environ.get('DSIG_CONTAINER') == '1' else '127.0.0.1', args.port), Handler)
            server.serve_forever()
    except LookupError:
        raise SystemExit('Demande introuvable.')
    except ValueError as error:
        raise SystemExit(f'Paramètre invalide : {error}')


if __name__ == '__main__':
    main()
