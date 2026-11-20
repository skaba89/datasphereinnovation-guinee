"""Private consultant register for local acceptance testing."""
import json
import re
import sqlite3
import uuid
from urllib.parse import parse_qs, urlsplit

STATUSES = ("A_QUALIFIER", "DISPONIBLE", "EN_MISSION", "INDISPONIBLE", "ARCHIVE")
FIELDS = {"name":120,"email":254,"role":120,"skills":1000,"location":120,
          "experience":2,"availability":120,"notes":2000,"status":30}

def schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS consultants (
      id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL, role TEXT NOT NULL,
      skills TEXT NOT NULL, location TEXT NOT NULL, experience TEXT NOT NULL,
      availability TEXT NOT NULL, notes TEXT NOT NULL, status TEXT NOT NULL,
      version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    db.execute("""CREATE TABLE IF NOT EXISTS consultant_events (
      id INTEGER PRIMARY KEY, consultant_id TEXT NOT NULL, status TEXT NOT NULL,
      version INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")

def validate(data):
    if not isinstance(data,dict) or set(data)!=set(FIELDS):
        raise ValueError()
    values={}
    for key,limit in FIELDS.items():
        value=data[key]
        if not isinstance(value,str) or len(value)>limit or "\x00" in value:
            raise ValueError()
        values[key]=value.strip()
    if not all(values[k] for k in ("name","email","role","skills")):
        raise ValueError()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",values["email"]):
        raise ValueError()
    if values["experience"] and (not re.fullmatch(r"[0-9]{1,2}",values["experience"]) or int(values["experience"])>70):
        raise ValueError()
    if values["status"] not in STATUSES:
        raise ValueError()
    return values

def handle(h,connect,method):
    if not h.admin_authorized():
        return
    if (h.headers.get("Origin") and h.headers["Origin"]!=h.expected_origin()) or h.headers.get("Sec-Fetch-Site")=="cross-site":
        return h.json_response(403,{"error":"Origine non autorisée."})
    path=urlsplit(h.path).path
    if method=="GET":
        query=parse_qs(urlsplit(h.path).query)
        status=query.get("status",[""])[0]
        q=query.get("q",[""])[0][:120]
        try:
            page=max(1,min(10000,int(query.get("page",["1"])[0])))
            if status and status not in STATUSES: raise ValueError()
        except ValueError:
            return h.json_response(400,{"error":"Filtre invalide."})
        where=" WHERE (?='' OR status=?) AND (instr(lower(name),lower(?))>0 OR instr(lower(role),lower(?))>0 OR instr(lower(skills),lower(?))>0 OR instr(lower(location),lower(?))>0)"
        args=(status,status,q,q,q,q)
        with connect() as db:
            db.row_factory=sqlite3.Row
            total=db.execute("SELECT count(*) FROM consultants"+where,args).fetchone()[0]
            rows=[dict(row) for row in db.execute("SELECT * FROM consultants"+where+" ORDER BY name,id LIMIT 25 OFFSET ?",(*args,(page-1)*25))]
            counts=dict(db.execute("SELECT status,count(*) FROM consultants GROUP BY status").fetchall())
        return h.json_response(200,{"items":rows,"counts":counts,"total":total})
    try:
        length=int(h.headers.get("Content-Length","0"))
        if not 0<length<=16000 or h.headers.get_content_type()!="application/json": raise ValueError()
        data=json.loads(h.rfile.read(length))
        version=data.pop("version",None) if isinstance(data,dict) else None
        values=validate(data)
        if method=="PATCH" and (type(version) is not int or version<1): raise ValueError()
        if method=="POST" and version is not None: raise ValueError()
    except (ValueError,TypeError,UnicodeError):
        return h.json_response(400,{"error":"Champs invalides."})
    keys=list(values)
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if method=="POST":
            cid=str(uuid.uuid4())
            db.execute("INSERT INTO consultants(id,"+",".join(keys)+") VALUES("+",".join("?" for _ in range(len(keys)+1))+")",(cid,*values.values()))
            version=1
        else:
            cid=path.rsplit("/",1)[-1]
            row=db.execute("SELECT version FROM consultants WHERE id=?",(cid,)).fetchone()
            if not row: return h.json_response(404,{"error":"Profil introuvable."})
            if row[0]!=version: return h.json_response(409,{"error":"Profil modifié. Actualisez."})
            version+=1
            db.execute("UPDATE consultants SET "+",".join(k+"=?" for k in keys)+",version=? WHERE id=?",(*values.values(),version,cid))
        db.execute("INSERT INTO consultant_events(consultant_id,status,version) VALUES(?,?,?)",(cid,values["status"],version))
    return h.json_response(201 if method=="POST" else 200,{"id":cid,"version":version})
