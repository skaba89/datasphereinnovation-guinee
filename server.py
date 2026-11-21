"""Local-only DSIG request intake; no mail or external integrations."""
import argparse
import csv
import hmac
import json
import os
import re
import sqlite3
import sys
import time
import uuid
import tenders
import consultants
import recruitment
import appointments
import crm
import organizations
import quotes
import direction
import missions
import contracts
import billing
import treasury
import reporting
import documents
import alerts
import notifications
import contact_mail
import accounts
import own_activity
import authentication
import operations
from collections import defaultdict
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, BoundedSemaphore
from urllib.parse import urlsplit, parse_qs, unquote

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get("DSIG_DB", ROOT / "data" / "requests.sqlite3"))
NEEDS = {"Demande de démonstration", "Mission en régie", "Projet au forfait",
         "Plateforme Analytics / BI", "Transformation numérique", "Data & IA", "Partenariat",
         "Conseil & expertise", "Contrôle de gestion & finance", "Audit & contrôle interne",
         "Avant-vente & appels d’offres", "Candidature spontanée", "Cybersécurité & résilience"}
SIZES = {"nom": 120, "org": 180, "email": 254, "besoin": 80, "solution": 160, "message": 4000}
RATE = defaultdict(list)
RATE_LOCK = Lock()
STATUSES = ("NOUVELLE", "QUALIFIEE", "EN_COURS", "GAGNEE", "PERDUE")
ADMIN_TOKEN = os.environ.get("DSIG_ADMIN_TOKEN", "")


def configured_origin():
    """An explicit HTTPS origin, never derived from forwarded headers."""
    origin = os.environ.get('DSIG_HTTPS_ORIGIN', '')
    if origin and not re.fullmatch(r'https://(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', origin):
        raise ValueError('DSIG_HTTPS_ORIGIN must be an exact HTTPS hostname')
    return origin


def connect():
    DB.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    db = sqlite3.connect(DB, timeout=10)
    os.chmod(DB, 0o600)
    db.execute("""CREATE TABLE IF NOT EXISTS requests (
        id TEXT PRIMARY KEY, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        nom TEXT NOT NULL, org TEXT NOT NULL, email TEXT NOT NULL,
        besoin TEXT NOT NULL, solution TEXT NOT NULL, message TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'NOUVELLE')""")
    db.execute("""CREATE TABLE IF NOT EXISTS request_events (
        id INTEGER PRIMARY KEY, request_id TEXT NOT NULL REFERENCES requests(id),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        previous_status TEXT NOT NULL, new_status TEXT NOT NULL)""")
    tenders.schema(db)
    consultants.schema(db)
    recruitment.schema(db)
    appointments.schema(db)
    crm.schema(db)
    organizations.schema(db)
    quotes.schema(db)
    missions.schema(db)
    contracts.schema(db)
    billing.schema(db)
    treasury.schema(db)
    accounts.schema(db)
    documents.schema(db)
    notifications.schema(db)
    contact_mail.schema(db)
    return db


def validate(payload):
    if not isinstance(payload, dict) or payload.get("website"):
        raise ValueError("Demande invalide.")
    allowed = set(SIZES) | {"website", "consent", "language"}
    if set(payload) - allowed or payload.get("consent") is not True:
        raise ValueError("Veuillez confirmer la notice de confidentialité.")
    if payload.get('language','fr') not in ('fr','en'):
        raise ValueError('Langue invalide.')
    values = {}
    for key, maximum in SIZES.items():
        value = payload.get(key, "")
        if not isinstance(value, str) or len(value) > maximum or "\x00" in value:
            raise ValueError("Champ invalide : " + key)
        values[key] = value.strip()
        if key != "solution" and not values[key]:
            raise ValueError("Champ obligatoire : " + key)
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", values["email"]):
        raise ValueError("Adresse e-mail invalide.")
    if values["besoin"] not in NEEDS:
        raise ValueError("Type de demande invalide.")
    if values["besoin"] == "Demande de démonstration" and not values["solution"]:
        raise ValueError("Sélectionnez une solution.")
    if values["besoin"] != "Demande de démonstration":
        values["solution"] = ""
    return values


class Handler(SimpleHTTPRequestHandler):
    timeout = 10

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "dist"), **kwargs)

    def expected_origin(self):
        return configured_origin() or 'http://' + self.headers.get('Host', '')

    def secure_cookie(self):
        return bool(configured_origin())

    def parse_request(self):
        if not super().parse_request():return False
        lengths=self.headers.get_all('Content-Length',[])
        if self.headers.get('Transfer-Encoding') is not None or len(lengths)>1 or (lengths and not re.fullmatch(r'[0-9]{1,10}',lengths[0])):
            self.send_error(400,'Invalid request framing');return False
        if not self.path.startswith('/') or self.path.startswith('//'):
            self.send_error(400,'Invalid request target');return False
        if len(self.headers.get_all('Host', [])) > 1 or len(self.headers.get_all('Origin', [])) > 1:
            self.send_error(400,'Ambiguous origin or host');return False
        origin = configured_origin()
        if origin and not (self.command == 'GET' and self.path in ('/api/health', '/api/ready')):
            if self.headers.get('Host', '') != origin.removeprefix('https://'):
                self.send_error(403,'Invalid host');return False
        return True

    def log_request(self, code='-', size='-'):
        # Never log query strings or submitted credentials.
        self.log_message('%s %s %s',self.command,str(code),str(size))

    def send_head(self):
        # The site is a flat bundle; refuse unpublished files and symlink escape.
        path=unquote(urlsplit(self.path).path)
        name='index.html' if path=='/' else path[1:]
        # Only the four bundled fonts and their license may use a nested path.
        font_asset=name in {
            'fonts/open-sans-Regular.woff',
            'fonts/open-sans-Semibold.woff',
            'fonts/open-sans-Bold.woff',
            'fonts/open-sans-ExtraBold.woff',
            'fonts/LICENSE.txt',
        }
        if not font_asset and not re.fullmatch(r'[A-Za-z0-9_-]+\.(?:html|css|js|svg|webp|txt)',name):
            self.send_error(404);return None
        target=ROOT/'dist'/name
        if (font_asset and target.parent.is_symlink()) or target.is_symlink() or not target.is_file():
            self.send_error(404);return None
        return super().send_head()

    def guess_type(self, path):
        if path.endswith('.woff'):
            return 'font/woff'
        return super().guess_type(path)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'")
        super().end_headers()

    def list_directory(self, path):
        self.send_error(403)

    def json_response(self, status, body):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        if getattr(self,'session_cookie_header',None):self.send_header('Set-Cookie',self.session_cookie_header)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if urlsplit(self.path).path=='/api/admin/crm/appointments':return appointments.handle(self,connect,'GET')
        if urlsplit(self.path).path=='/api/admin/recruitment':return recruitment.handle(self,connect,'GET')
        if urlsplit(self.path).path=='/api/admin/notifications':return notifications.handle(self,connect,'GET')
        if urlsplit(self.path).path=='/api/admin/alerts':return alerts.handle(self,connect)
        if re.fullmatch(r'/api/admin/documents(?:/[0-9a-f-]{36})?',urlsplit(self.path).path):return documents.handle(self,connect,'GET')
        if urlsplit(self.path).path=='/api/admin/direction/reporting':return reporting.handle(self,connect)
        if urlsplit(self.path).path=='/api/admin/billing/expenses':return treasury.handle(self,connect,'GET')
        if re.fullmatch(r'/api/admin/missions/[0-9a-f-]{36}/renewals',urlsplit(self.path).path):return contracts.handle(self,connect,'GET')
        if urlsplit(self.path).path == '/api/admin/crm/organizations':
            return organizations.handle(self,connect,'GET')
        if self.path=='/api/ready':
            ready=operations.ready(DB)
            return self.json_response(200 if ready else 503,{'status':'ready' if ready else 'unavailable'})
        if urlsplit(self.path).path=='/api/auth/me':return authentication.me(self,connect)
        if urlsplit(self.path).path=='/api/admin/my-activity':return own_activity.handle(self,connect,'GET')
        if urlsplit(self.path).path in ('/api/admin/accounts','/api/admin/audit'):return accounts.handle(self,connect,'GET')
        if re.fullmatch(r'/api/admin/billing(?:/milestones)?',urlsplit(self.path).path): return billing.handle(self,connect,'GET')
        if re.fullmatch(r'/api/admin/missions(?:/eligible|/[0-9a-f-]{36}/activity)?',urlsplit(self.path).path):
            return missions.handle(self,connect,'GET')
        if urlsplit(self.path).path == "/api/admin/direction":
            if not self.admin_authorized(): return
            if self.headers.get("Sec-Fetch-Site") == "cross-site" or (self.headers.get("Origin") and self.headers["Origin"] != self.expected_origin()):
                return self.json_response(403, {"error": "Origine non autorisée."})
            with connect() as db:
                db.execute('BEGIN')
                return self.json_response(200, direction.snapshot(db))
        if urlsplit(self.path).path == "/api/admin/quotes":
            return quotes.handle(self, connect, "GET")
        if urlsplit(self.path).path == "/api/admin/crm":
            return crm.handle(self, connect, "GET")
        if urlsplit(self.path).path == "/api/admin/consultants":
            return consultants.handle(self, connect, "GET")
        if urlsplit(self.path).path == "/api/admin/tenders":
            return tenders.handle(self, connect, "GET")
        if self.path == "/api/health":
            self.json_response(200, {"status": "ok", "mode": "local"})
        elif urlsplit(self.path).path == "/api/admin/requests":
            if not self.admin_authorized():
                return
            query = parse_qs(urlsplit(self.path).query)
            status = query.get("status", [""])[0]
            search = query.get("q", [""])[0][:120]
            try:
                page = max(1, min(10000, int(query.get("page", ["1"])[0])))
            except ValueError:
                return self.json_response(400, {"error": "Page invalide."})
            if status and status not in STATUSES:
                return self.json_response(400, {"error": "Statut invalide."})
            need = query.get("besoin", [""])[0]
            if need and need not in NEEDS:
                return self.json_response(400, {"error": "Type de demande invalide."})
            where = "WHERE (? = '' OR status = ?) AND (? = '' OR besoin = ?) AND (instr(lower(nom), lower(?)) > 0 OR instr(lower(org), lower(?)) > 0 OR instr(lower(email), lower(?)) > 0 OR instr(lower(solution), lower(?)) > 0 OR instr(lower(besoin), lower(?)) > 0)"
            args = (status, status, need, need, search, search, search, search, search)
            with connect() as db:
                db.row_factory = sqlite3.Row
                counts = dict((x["status"], x["n"]) for x in db.execute("SELECT status,count(*) n FROM requests GROUP BY status"))
                total = db.execute("SELECT count(*) FROM requests " + where, args).fetchone()[0]
                rows = [dict(x) for x in db.execute("SELECT * FROM requests " + where + " ORDER BY created_at DESC,id DESC LIMIT 25 OFFSET ?", (*args, (page-1)*25))]
            self.json_response(200, {"items": rows, "total": total, "page": page, "counts": counts})
        else:
            super().do_GET()

    def admin_authorized(self):
        if self.headers.get('Sec-Fetch-Site')=='cross-site' or (self.headers.get('Origin') and self.headers['Origin']!=self.expected_origin()):
            self.json_response(403,{'error':'Origine non autorisée.'});return False
        return accounts.authorize(self,connect,ADMIN_TOKEN)

    def do_PATCH(self):
        if re.fullmatch(r'/api/admin/crm/appointments/[0-9a-f-]{36}',self.path):return appointments.handle(self,connect,'PATCH')
        if re.fullmatch(r'/api/admin/missions/[0-9a-f-]{36}/renewals/[0-9a-f-]{36}',self.path):return contracts.handle(self,connect,'PATCH')
        if re.fullmatch(r'/api/admin/crm/organizations/[0-9a-f-]{36}',self.path):
            return organizations.handle(self,connect,'PATCH')
        if re.fullmatch(r'/api/admin/accounts/[0-9a-f-]{36}',self.path):return accounts.handle(self,connect,'PATCH')
        if re.fullmatch(r'/api/admin/billing/milestones/[0-9a-f-]{36}',self.path): return billing.handle(self,connect,'PATCH')
        if re.fullmatch(r'/api/admin/missions/(?:[0-9a-f-]{36}|activity/[0-9a-f-]{36})',self.path):
            return missions.handle(self,connect,'PATCH')
        if re.fullmatch(r"/api/admin/quotes/[0-9a-f-]{36}", self.path):
            return quotes.handle(self, connect, "PATCH")
        if re.fullmatch(r"/api/admin/crm/[0-9a-f-]{36}", self.path):
            return crm.handle(self, connect, "PATCH")
        if re.fullmatch(r"/api/admin/consultants/[0-9a-f-]{36}", self.path):
            return consultants.handle(self, connect, "PATCH")
        if re.fullmatch(r"/api/admin/tenders/[0-9a-f-]{36}", self.path):
            return tenders.handle(self, connect, "PATCH")
        match = re.fullmatch(r"/api/admin/requests/([0-9a-f-]{36})", self.path)
        if not match:
            return self.json_response(404, {"error": "Route inconnue."})
        if not self.admin_authorized():
            return
        if (self.headers.get("Origin") and self.headers["Origin"] != self.expected_origin()) or self.headers.get("Sec-Fetch-Site") == "cross-site":
            return self.json_response(403, {"error": "Origine non autorisée."})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 1024 or self.headers.get_content_type() != "application/json":
                raise ValueError()
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict) or set(payload) != {"status", "previous"} or any(payload[k] not in STATUSES for k in payload):
                raise ValueError()
        except (ValueError, UnicodeError):
            return self.json_response(400, {"error": "Statut invalide."})
        request_id = match.group(1)
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM requests WHERE id=?", (request_id,)).fetchone()
            if not row:
                return self.json_response(404, {"error": "Demande introuvable."})
            if row[0] != payload["previous"]:
                return self.json_response(409, {"error": "La demande a changé. Actualisez la liste."})
            if row[0] != payload["status"]:
                db.execute("UPDATE requests SET status=? WHERE id=?", (payload["status"], request_id))
                db.execute("INSERT INTO request_events(request_id,previous_status,new_status) VALUES (?,?,?)", (request_id,row[0],payload["status"]))
        self.json_response(200, {"status": payload["status"]})

    def do_POST(self):
        if self.path=='/api/admin/crm/appointments':return appointments.handle(self,connect,'POST')
        if self.path=='/api/admin/recruitment':return recruitment.handle(self,connect,'POST')
        if self.path=='/api/admin/notifications':return notifications.handle(self,connect,'POST')
        if self.path=='/api/admin/documents':return documents.handle(self,connect,'POST')
        if self.path=='/api/admin/billing/expenses':return treasury.handle(self,connect,'POST')
        if re.fullmatch(r'/api/admin/missions/[0-9a-f-]{36}/renewals',self.path):return contracts.handle(self,connect,'POST')
        if self.path == '/api/admin/crm/organizations':
            return organizations.handle(self,connect,'POST')
        if self.path in ('/api/auth/activate','/api/auth/login','/api/auth/logout','/api/auth/mfa-setup','/api/auth/mfa-confirm','/api/auth/revoke-others'):return authentication.handle(self,connect)
        if self.path=='/api/admin/my-activity':return own_activity.handle(self,connect,'POST')
        if self.path=='/api/admin/accounts':return accounts.handle(self,connect,'POST')
        if re.fullmatch(r'/api/admin/billing/(?:milestones|invoices|payments)',self.path): return billing.handle(self,connect,'POST')
        if re.fullmatch(r'/api/admin/missions(?:/[0-9a-f-]{36}/(?:activity|team))?',self.path):
            return missions.handle(self,connect,'POST')
        if self.path == "/api/admin/quotes":
            return quotes.handle(self, connect, "POST")
        if self.path == "/api/admin/crm":
            return crm.handle(self, connect, "POST")
        if self.path == "/api/admin/consultants":
            return consultants.handle(self, connect, "POST")
        if self.path == "/api/admin/tenders":
            return tenders.handle(self, connect, "POST")
        if self.path != "/api/requests":
            return self.json_response(404, {"error": "Route inconnue."})
        if (self.headers.get("Origin") and self.headers["Origin"] != self.expected_origin()) or self.headers.get("Sec-Fetch-Site") == "cross-site":
            return self.json_response(403, {"error": "Origine non autorisée."})
        if self.headers.get_content_type() != "application/json":
            return self.json_response(415, {"error": "Format non pris en charge."})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 16000:
                return self.json_response(413, {"error": "Demande trop volumineuse."})
            payload = json.loads(self.rfile.read(size))
            values = validate(payload)
        except (ValueError, UnicodeError):
            return self.json_response(400, {"error": "Veuillez vérifier les champs obligatoires."})
        now = time.monotonic()
        ip = self.client_address[0]
        with RATE_LOCK:
            for stale in [k for k,v in RATE.items() if not v or now-v[-1]>=60]:del RATE[stale]
            if ip not in RATE and len(RATE)>=2048:return self.json_response(429,{'error':'Veuillez patienter une minute.'})
            RATE[ip] = [t for t in RATE[ip] if now - t < 60]
            if len(RATE[ip]) >= 5:
                return self.json_response(429, {"error": "Veuillez patienter une minute."})
            RATE[ip].append(now)
        request_id = str(uuid.uuid4())
        try:
            with connect() as db:
                db.execute("INSERT INTO requests (id,nom,org,email,besoin,solution,message) VALUES (?,?,?,?,?,?,?)",
                           (request_id, *(values[k] for k in SIZES)))
                if os.environ.get('DSIG_ENV','REC') == 'REC':
                    contact_mail.enqueue(db, request_id, payload.get('language','fr'))
        except sqlite3.Error:
            return self.json_response(503, {"error": "Enregistrement indisponible."})
        self.json_response(201, {"id": request_id, "status": "NOUVELLE"})


def export_requests():
    with connect() as db:
        cursor = db.execute("SELECT * FROM requests ORDER BY created_at DESC")
        writer = csv.writer(sys.stdout)
        writer.writerow([x[0] for x in cursor.description])
        for row in cursor:
            writer.writerow([("'" + v) if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")) else v for v in row])


def backup_database(destination):
    path=Path(destination).resolve()
    if path.is_relative_to(ROOT / 'dist') or not DB.is_file():
        raise ValueError('Sauvegarde interdite dans dist ou base inexistante.')
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    os.close(fd)
    try:
        with sqlite3.connect(DB) as source, sqlite3.connect(path) as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                raise ValueError('Contrôle intégrité échoué.')
    except Exception:
        path.unlink()
        raise


class BoundedHTTPServer(ThreadingHTTPServer):
    """Cap simultaneous handlers; the reverse proxy must provide additional limits."""
    slots=BoundedSemaphore(32)
    def process_request(self,request,client_address):
        if not self.slots.acquire(blocking=False):self.shutdown_request(request);return
        try:super().process_request(request,client_address)
        except BaseException:self.slots.release();raise
    def process_request_thread(self,request,client_address):
        try:super().process_request_thread(request,client_address)
        finally:self.slots.release()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--backup", metavar="FILE", help="Sauvegarde SQLite privée, fichier inexistant")
    parser.add_argument("--backup-encrypted", metavar="FILE", help="Sauvegarde chiffrée, fichier inexistant")
    parser.add_argument("--restore-isolated", nargs=2, metavar=("BACKUP","DESTINATION"), help="Restauration chiffrée vers une nouvelle base isolée")
    parser.add_argument("--check-db", action="store_true", help="Vérification de l'intégrité SQLite, lecture seule")
    parser.add_argument("--rotate-documents", metavar="COPY", help="Rotation des documents sur une copie isolée, serveur arrêté")
    parser.add_argument("--refresh-notifications", action="store_true", help="Calcul des rappels internes (DEV/REC)")
    parser.add_argument('--send-contact-notifications', action='store_true', help='REC: traiter la file de mails avec configuration JSON sur stdin')
    parser.add_argument('--send-account-invitations', action='store_true', help='REC: traiter invitations de test')
    parser.add_argument('--contact-mail-status', action='store_true', help='Compteurs de la file de mails')
    args = parser.parse_args()
    if sum(bool(x) for x in (args.export,args.backup,args.backup_encrypted,args.restore_isolated,args.check_db,args.rotate_documents,args.refresh_notifications,args.send_contact_notifications,args.send_account_invitations,args.contact_mail_status))>1:
        parser.error('Une seule opération à la fois.')
    if args.send_contact_notifications or args.send_account_invitations or args.contact_mail_status:
        if os.environ.get('DSIG_ENV','REC') != 'REC':raise SystemExit('REC uniquement.')
        if args.contact_mail_status:
            with connect() as db:print(json.dumps(dict(db.execute('SELECT state,count(*) FROM contact_mail GROUP BY state').fetchall())))
        else:
            try:print(json.dumps(contact_mail.run(connect,json.loads(sys.stdin.read(8192)),invitations=args.send_account_invitations)))
            except (ValueError, OSError, sqlite3.Error):raise SystemExit('Configuration ou traitement indisponible.')
        return
    if args.refresh_notifications:
        if os.environ.get('DSIG_ENV','REC') not in ('DEV','REC'):raise SystemExit('Production bloquée.')
        from datetime import date
        with connect() as db:count=notifications.run(db,date.today())
        print(f'{count} nouvelle(s) notification(s).');return
    if args.rotate_documents:
        path=operations.safe_target(args.rotate_documents,DB,ROOT/'dist');operations.verify(path)
        if DB.exists() and path.samefile(DB):raise ValueError('Copie isolée obligatoire.')
        with sqlite3.connect(path) as db:count=documents.rotate(db)
        print(f'{count} document(s) rechiffré(s) sur la copie isolée.');return
    if args.backup_encrypted:
        operations.encrypted_backup(DB,args.backup_encrypted,ROOT/'dist');print('Sauvegarde chiffrée vérifiée.');return
    if args.restore_isolated:
        operations.restore_isolated(*args.restore_isolated,DB,ROOT/'dist');print('Restauration isolée vérifiée.');return
    if args.check_db:
        operations.verify(DB);print('Intégrité SQLite vérifiée.');return
    if args.export:
        return export_requests()
    if args.backup:
        backup_database(args.backup)
        print('Sauvegarde vérifiée :',args.backup)
        return
    with connect():
        pass
    mode=os.environ.get('DSIG_ENV','REC')
    if mode not in ('DEV','REC'):
        raise SystemExit('Production bloquée : validation de sécurité requise.')
    configured_origin()
    bind='0.0.0.0' if os.environ.get('DSIG_CONTAINER')=='1' else '127.0.0.1'
    server = BoundedHTTPServer((bind, args.port), Handler)
    print(f"DSIG local : http://127.0.0.1:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

