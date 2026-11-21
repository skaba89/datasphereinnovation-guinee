"""REC commercial appointments, with UTC scheduling and transactional overlap checks."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
import accounts


def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS appointments(id TEXT PRIMARY KEY, opportunity_id TEXT NOT NULL, title TEXT NOT NULL, starts TEXT NOT NULL, ends TEXT NOT NULL, status TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, actor TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS appointment_events(id INTEGER PRIMARY KEY, appointment_id TEXT NOT NULL, status TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')


def utc(value):
    if not isinstance(value,str) or len(value)>40:raise ValueError()
    dt=datetime.fromisoformat(value.replace('Z','+00:00'))
    if dt.tzinfo is None:raise ValueError()
    return dt.astimezone(timezone.utc).isoformat(timespec='seconds')


def create(db,v,actor):
    if not isinstance(v,dict) or set(v)!={'opportunity_id','title','starts','ends'}:raise ValueError()
    oid=v['opportunity_id'];title=v['title']
    if not isinstance(oid,str) or not isinstance(title,str) or not 0<len(title.strip())<=180 or any(ord(c)<32 for c in title):raise ValueError()
    if not db.execute('SELECT 1 FROM opportunities WHERE id=?',(oid,)).fetchone():raise ValueError()
    start,end=utc(v['starts']),utc(v['ends'])
    if start>=end:raise ValueError()
    if db.execute("SELECT 1 FROM appointments WHERE status='PLANIFIE' AND starts<? AND ends>?",(end,start)).fetchone():raise sqlite3.IntegrityError('Créneau occupé')
    aid=str(uuid.uuid4());db.execute('INSERT INTO appointments VALUES (?,?,?,?,?,?,1,?)',(aid,oid,title.strip(),start,end,'PLANIFIE',actor))
    db.execute('INSERT INTO appointment_events(appointment_id,status,actor) VALUES (?,?,?)',(aid,'PLANIFIE',actor));accounts.event(db,actor,'RDV_CREE',aid)
    return aid


def finish(db,aid,v,actor):
    if not isinstance(v,dict) or set(v)!={'status','version'} or v['status'] not in ('TERMINE','ANNULE') or type(v['version']) is not int:raise ValueError()
    cur=db.execute("UPDATE appointments SET status=?,version=version+1 WHERE id=? AND version=? AND status='PLANIFIE'",(v['status'],aid,v['version']))
    if cur.rowcount!=1:raise sqlite3.IntegrityError('Rendez-vous modifié ou clôturé')
    db.execute('INSERT INTO appointment_events(appointment_id,status,actor) VALUES (?,?,?)',(aid,v['status'],actor));accounts.event(db,actor,'RDV_CLOTURE',aid)


def handle(h,connect,method):
    if not h.admin_authorized():return
    if method=='GET':
        with connect() as db:
            db.row_factory=sqlite3.Row
            rows=[dict(r) for r in db.execute('SELECT a.*,o.company,o.title AS opportunity_title FROM appointments a JOIN opportunities o ON o.id=a.opportunity_id ORDER BY a.starts DESC LIMIT 100')]
            for row in rows:row['history']=[dict(e) for e in db.execute('SELECT status,actor,created_at FROM appointment_events WHERE appointment_id=? ORDER BY id',(row['id'],))]
            options=[dict(r) for r in db.execute('SELECT id,company,title FROM opportunities ORDER BY created_at DESC LIMIT 100')]
        return h.json_response(200,{'items':rows,'opportunities':options})
    try:
        n=int(h.headers.get('Content-Length','0'))
        if not 0<n<=4096 or h.headers.get_content_type()!='application/json':raise ValueError()
        v=json.loads(h.rfile.read(n))
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if method=='POST':aid=create(db,v,h.actor)
            else:aid=h.path.rsplit('/',1)[-1];finish(db,aid,v,h.actor)
        return h.json_response(201 if method=='POST' else 200,{'id':aid})
    except (ValueError,TypeError,UnicodeError):return h.json_response(400,{'error':'Rendez-vous invalide.'})
    except sqlite3.IntegrityError:return h.json_response(409,{'error':'Créneau occupé ou rendez-vous déjà modifié.'})
