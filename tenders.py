"""Internal tender register. No external submissions or integrations."""
from datetime import date
import json
import sqlite3
import uuid
from urllib.parse import parse_qs, urlsplit

STAGES = ("VEILLE", "QUALIFICATION", "GO", "NO_GO", "PREPARATION", "DEPOSE", "GAGNE", "PERDU")
FIELDS = {"title": 180, "client": 180, "reference": 120, "deadline": 10,
          "owner": 120, "notes": 4000, "currency": 3, "budget": 30}


def schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS tenders (
        id TEXT PRIMARY KEY, title TEXT NOT NULL, client TEXT NOT NULL,
        reference TEXT NOT NULL, deadline TEXT NOT NULL, owner TEXT NOT NULL,
        notes TEXT NOT NULL, currency TEXT NOT NULL, budget TEXT NOT NULL,
        stage TEXT NOT NULL DEFAULT 'VEILLE', version INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    db.execute("""CREATE TABLE IF NOT EXISTS tender_events (
        id INTEGER PRIMARY KEY, tender_id TEXT NOT NULL,
        stage TEXT NOT NULL, version INTEGER NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")


def validate(data):
    import re
    if not isinstance(data, dict) or set(data) != set(FIELDS) | {"stage"}:
        raise ValueError()
    result = {}
    for key, limit in FIELDS.items():
        v = data[key]
        if not isinstance(v, str) or len(v) > limit or "\x00" in v:
            raise ValueError()
        result[key] = v.strip()
    if not result["title"] or not result["client"] or not result["deadline"]:
        raise ValueError()
    if date.fromisoformat(result["deadline"]).isoformat() != result["deadline"]:
        raise ValueError()
    if result["currency"] not in ("GNF", "EUR", "USD", "XOF"):
        raise ValueError()
    if result["budget"] and not re.fullmatch(r"\d{1,15}(\.\d{1,2})?", result["budget"]):
        raise ValueError()
    if data["stage"] not in STAGES:
        raise ValueError()
    result["stage"] = data["stage"]
    return result


def handle(handler, connect, method):
    if not handler.admin_authorized():
        return
    if (handler.headers.get("Origin") and handler.headers["Origin"] != "http://" + handler.headers.get("Host", "")) or handler.headers.get("Sec-Fetch-Site") == "cross-site":
        return handler.json_response(403, {"error": "Origine non autorisée."})
    path = urlsplit(handler.path).path
    if method == "GET":
        if path != "/api/admin/tenders":
            return handler.json_response(404, {"error": "Route inconnue."})
        query = parse_qs(urlsplit(handler.path).query)
        stage = query.get("stage", [""])[0]
        q = query.get("q", [""])[0][:120]
        if stage and stage not in STAGES:
            return handler.json_response(400, {"error": "Statut invalide."})
        try:
            page = max(1, min(10000, int(query.get("page", ["1"])[0])))
        except ValueError:
            return handler.json_response(400, {"error": "Page invalide."})
        where = "WHERE (?='' OR stage=?) AND (instr(lower(title),lower(?))>0 OR instr(lower(client),lower(?))>0 OR instr(lower(reference),lower(?))>0)"
        args = (stage, stage, q, q, q)
        with connect() as db:
            db.row_factory = sqlite3.Row
            total = db.execute("SELECT count(*) FROM tenders "+where,args).fetchone()[0]
            rows = [dict(r) for r in db.execute("SELECT * FROM tenders "+where+" ORDER BY deadline,id LIMIT 25 OFFSET ?",(*args,(page-1)*25))]
            counts = dict(db.execute("SELECT stage,count(*) FROM tenders GROUP BY stage").fetchall())
        return handler.json_response(200, {"items": rows, "total": total, "counts": counts})
    try:
        size = int(handler.headers.get("Content-Length", "0"))
        if not 0 < size <= 32000 or handler.headers.get_content_type() != "application/json":
            raise ValueError()
        data = json.loads(handler.rfile.read(size))
        version = data.pop("version", None) if isinstance(data, dict) else None
        values = validate(data)
        if method == "PATCH" and (type(version) is not int or version < 1):
            raise ValueError()
        if method == "POST" and version is not None:
            raise ValueError()
    except (ValueError, TypeError, UnicodeError):
        return handler.json_response(400, {"error": "Champs invalides."})
    columns = list(values)
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if method == "POST" and path == "/api/admin/tenders":
            tid = str(uuid.uuid4())
            db.execute("INSERT INTO tenders(id,"+",".join(columns)+") VALUES("+",".join("?" for _ in range(len(columns)+1))+")",(tid,*values.values()))
            version = 1
        elif method == "PATCH":
            tid = path.removeprefix("/api/admin/tenders/")
            row = db.execute("SELECT version FROM tenders WHERE id=?",(tid,)).fetchone()
            if not row:
                return handler.json_response(404, {"error": "Appel d’offres introuvable."})
            if row[0] != version:
                return handler.json_response(409, {"error": "Dossier modifié. Actualisez."})
            version += 1
            db.execute("UPDATE tenders SET "+",".join(k+"=?" for k in columns)+",version=? WHERE id=?",(*values.values(),version,tid))
        else:
            return handler.json_response(404, {"error": "Route inconnue."})
        db.execute("INSERT INTO tender_events(tender_id,stage,version) VALUES(?,?,?)",(tid,values["stage"],version))
    return handler.json_response(201 if method=="POST" else 200, {"id":tid,"version":version})
