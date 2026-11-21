"""REC candidate qualification: link a spontaneous application to the existing talent register."""
import json
import sqlite3
import uuid
from urllib.parse import parse_qs, urlsplit
import accounts
import consultants


def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS recruitment_links (
        request_id TEXT PRIMARY KEY REFERENCES requests(id), consultant_id TEXT NOT NULL UNIQUE REFERENCES consultants(id),
        actor TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')


def qualify(db, request_id, role, skills, actor):
    schema(db)
    if not isinstance(request_id,str) or str(uuid.UUID(request_id))!=request_id:raise ValueError('Référence invalide.')
    row=db.execute("SELECT nom,email FROM requests WHERE id=? AND besoin='Candidature spontanée'",(request_id,)).fetchone()
    if not row:raise ValueError('Candidature introuvable.')
    existing=db.execute('SELECT consultant_id FROM recruitment_links WHERE request_id=?',(request_id,)).fetchone()
    if existing:return existing[0],False
    v=consultants.validate(dict(name=row[0],email=row[1],role=role,skills=skills,location='',experience='',availability='',notes='',status='A_QUALIFIER'))
    cid=str(uuid.uuid4())
    db.execute('INSERT INTO consultants(id,name,email,role,skills,location,experience,availability,notes,status) VALUES (?,?,?,?,?,?,?,?,?,?)',(cid,*v.values()))
    db.execute('INSERT INTO consultant_events(consultant_id,status,version) VALUES (?,?,1)',(cid,'A_QUALIFIER'))
    db.execute('INSERT INTO recruitment_links(request_id,consultant_id,actor) VALUES (?,?,?)',(request_id,cid,actor))
    accounts.event(db,actor,'CANDIDATURE_QUALIFIEE',request_id)
    return cid,True


def handle(h,connect,method):
    if not h.admin_authorized():return
    if method=='GET':
        query=parse_qs(urlsplit(h.path).query)
        q=query.get('q',[''])[0].strip()[:120]
        state=query.get('state',[''])[0]
        try:
            page=int(query.get('page',['1'])[0])
            if not 1<=page<=10000 or state not in ('','PENDING','QUALIFIED'):raise ValueError()
        except ValueError:return h.json_response(400,{'error':'Filtre invalide.'})
        where=" WHERE r.besoin='Candidature spontanée' AND (?='' OR instr(lower(r.nom),lower(?))>0 OR instr(lower(r.email),lower(?))>0 OR instr(lower(r.message),lower(?))>0) AND (?='' OR (?='PENDING' AND l.consultant_id IS NULL) OR (?='QUALIFIED' AND l.consultant_id IS NOT NULL))"
        args=(q,q,q,q,state,state,state)
        with connect() as db:
            schema(db);db.row_factory=sqlite3.Row
            source=' FROM requests r LEFT JOIN recruitment_links l ON r.id=l.request_id'+where
            total=db.execute('SELECT count(*)'+source,args).fetchone()[0]
            rows=[dict(r) for r in db.execute('SELECT r.id,r.nom,r.email,r.created_at,r.message,l.consultant_id'+source+' ORDER BY r.created_at DESC,r.id LIMIT 25 OFFSET ?',(*args,(page-1)*25))]
        return h.json_response(200,{'items':rows,'total':total})
    try:
        n=int(h.headers.get('Content-Length','0'))
        if not 0<n<=4096 or h.headers.get_content_type()!='application/json':raise ValueError()
        v=json.loads(h.rfile.read(n))
        if not isinstance(v,dict) or set(v)!={'request_id','role','skills'}:raise ValueError()
        with connect() as db:
            db.execute('BEGIN IMMEDIATE');cid,created=qualify(db,v['request_id'],v['role'],v['skills'],h.actor)
        return h.json_response(201 if created else 200,{'consultant_id':cid,'created':created})
    except (ValueError,TypeError,UnicodeError):return h.json_response(400,{'error':'Candidature ou qualification invalide.'})
    except sqlite3.IntegrityError:return h.json_response(409,{'error':'Conflit de qualification.'})
