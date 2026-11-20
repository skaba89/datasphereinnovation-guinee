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
import crm
import quotes
import direction
import missions
import billing
import accounts
import own_activity
import authentication
from collections import defaultdict
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit, parse_qs

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
    crm.schema(db)
    quotes.schema(db)
    missions.schema(db)
    billing.schema(db)
    accounts.schema(db)
    return db


def validate(payload):
    if not isinstance(payload, dict) or payload.get("website"):
        raise ValueError("Demande invalide.")
    allowed = set(SIZES) | {"website", "consent"}
    if set(payload) - allowed or payload.get("consent") is not True:
        raise ValueError("Veuillez confirmer la notice de confidentialité.")
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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "dist"), **kwargs)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'")
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
        if urlsplit(self.path).path=='/api/auth/me':return authentication.me(self,connect)
        if urlsplit(self.path).path=='/api/admin/my-activity':return own_activity.handle(self,connect,'GET')
        if urlsplit(self.path).path in ('/api/admin/accounts','/api/admin/audit'):return accounts.handle(self,connect,'GET')
        if re.fullmatch(r'/api/admin/billing(?:/milestones)?',urlsplit(self.path).path): return billing.handle(self,connect,'GET')
        if re.fullmatch(r'/api/admin/missions(?:/eligible|/[0-9a-f-]{36}/activity)?',urlsplit(self.path).path):
            return missions.handle(self,connect,'GET')
        if urlsplit(self.path).path == "/api/admin/direction":
            if not self.admin_authorized(): return
            if self.headers.get("Sec-Fetch-Site") == "cross-site" or (self.headers.get("Origin") and self.headers["Origin"] != "http://" + self.headers.get("Host", "")):
                return self.json_response(403, {"error": "Origine non autorisée."})
            with connect() as db:
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
        return accounts.authorize(self,connect,ADMIN_TOKEN)

    def do_PATCH(self):
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
        if (self.headers.get("Origin") and self.headers["Origin"] != "http://" + self.headers.get("Host", "")) or self.headers.get("Sec-Fetch-Site") == "cross-site":
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
        if self.path in ('/api/auth/activate','/api/auth/login','/api/auth/logout','/api/auth/mfa-setup','/api/auth/mfa-confirm','/api/auth/revoke-others'):return authentication.handle(self,connect)
        if self.path=='/api/admin/my-activity':return own_activity.handle(self,connect,'POST')
        if self.path=='/api/admin/accounts':return accounts.handle(self,connect,'POST')
        if re.fullmatch(r'/api/admin/billing/(?:milestones|invoices|payments)',self.path): return billing.handle(self,connect,'POST')
        if re.fullmatch(r'/api/admin/missions(?:/[0-9a-f-]{36}/activity)?',self.path):
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
        if (self.headers.get("Origin") and self.headers["Origin"] != "http://" + self.headers.get("Host", "")) or self.headers.get("Sec-Fetch-Site") == "cross-site":
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
            RATE[ip] = [t for t in RATE[ip] if now - t < 60]
            if len(RATE[ip]) >= 5:
                return self.json_response(429, {"error": "Veuillez patienter une minute."})
            RATE[ip].append(now)
        request_id = str(uuid.uuid4())
        try:
            with connect() as db:
                db.execute("INSERT INTO requests (id,nom,org,email,besoin,solution,message) VALUES (?,?,?,?,?,?,?)",
                           (request_id, *(values[k] for k in SIZES)))
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--backup", metavar="FILE", help="Sauvegarde SQLite privée, fichier inexistant")
    args = parser.parse_args()
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
    bind='0.0.0.0' if os.environ.get('DSIG_CONTAINER')=='1' else '127.0.0.1'
    server = ThreadingHTTPServer((bind, args.port), Handler)
    print(f"DSIG local : http://127.0.0.1:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
