"""Internal contract extension register; approval is not a legal signature."""
import json
import sqlite3
import uuid
from datetime import date,timedelta
from urllib.parse import urlsplit
import missions

def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS contract_renewals(id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, old_end TEXT NOT NULL, new_end TEXT NOT NULL, reference TEXT NOT NULL, reason TEXT NOT NULL, requester TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'SOUMIS', reviewer TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, decided_at TEXT NOT NULL DEFAULT '')''')
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_pending_renewal ON contract_renewals(mission_id) WHERE status='SOUMIS'")

def handle(h,connect,method):
    if not h.admin_authorized():return
    if (h.headers.get('Origin') and h.headers['Origin']!=h.expected_origin()) or h.headers.get('Sec-Fetch-Site')=='cross-site':return h.json_response(403,{'error':'Origine non autorisée.'})
    mid=urlsplit(h.path).path.split('/')[4]
    if method=='GET':
        with connect() as db:
            db.row_factory=sqlite3.Row
            m=db.execute('SELECT end_date,contract_ref,status FROM missions WHERE id=?',(mid,)).fetchone()
            if not m:return h.json_response(404,{'error':'Mission introuvable.'})
            remaining=(date.fromisoformat(m['end_date'])-date.today()).days
            return h.json_response(200,{'contract':dict(m),'remaining_days':remaining,'can_request':h.role in ('ADMIN','PROJET'),'can_review':h.role=='ADMIN','actor':h.actor,'items':[dict(r) for r in db.execute('SELECT * FROM contract_renewals WHERE mission_id=? ORDER BY created_at DESC,id DESC',(mid,))]})
    try:
        size=int(h.headers.get('Content-Length','0'))
        if not 0<size<=8000 or h.headers.get_content_type()!='application/json':raise ValueError()
        v=json.loads(h.rfile.read(size))
        if not isinstance(v,dict) or any(not isinstance(x,str) or '\x00' in x or len(x)>1000 for x in v.values()):raise ValueError()
        v={k:x.strip() for k,x in v.items()}
        with connect() as db:
            db.row_factory=sqlite3.Row;db.execute('BEGIN IMMEDIATE')
            m=db.execute("SELECT * FROM missions WHERE id=? AND status='ACTIVE'",(mid,)).fetchone()
            if not m:return h.json_response(409,{'error':'Mission absente ou clôturée.'})
            if method=='POST':
                if set(v)!={'new_end','reference','reason'} or not v['reason'] or not 0<len(v['reference'])<=180:raise ValueError()
                end=date.fromisoformat(v['new_end'])
                if end.isoformat()!=v['new_end'] or v['new_end']<=m['end_date']:raise ValueError()
                rid=str(uuid.uuid4());db.execute('INSERT INTO contract_renewals(id,mission_id,old_end,new_end,reference,reason,requester) VALUES(?,?,?,?,?,?,?)',(rid,mid,m['end_date'],v['new_end'],v['reference'],v['reason'],h.actor));event='RENOUVELLEMENT_SOUMIS'
            else:
                if h.role!='ADMIN':return h.json_response(403,{'error':'Validation réservée à un administrateur.'})
                if set(v)!={'status'} or v['status'] not in ('VALIDE','REFUSE'):raise ValueError()
                rid=h.path.rsplit('/',1)[-1];r=db.execute("SELECT * FROM contract_renewals WHERE id=? AND mission_id=? AND status='SOUMIS'",(rid,mid)).fetchone()
                if not r:return h.json_response(409,{'error':'Demande absente ou déjà traitée.'})
                if r['requester']==h.actor:return h.json_response(403,{'error':'Le demandeur ne peut pas valider sa propre demande.'})
                if v['status']=='VALIDE':
                    if m['end_date']!=r['old_end']:return h.json_response(409,{'error':'Échéance modifiée depuis la demande.'})
                    start=(date.fromisoformat(m['end_date'])+timedelta(days=1)).isoformat()
                    team=[m['consultant_id']]+[x[0] for x in db.execute('SELECT consultant_id FROM mission_members WHERE mission_id=?',(mid,))]
                    if any(missions.conflict(db,cid,start,r['new_end']) for cid in team):return h.json_response(409,{'error':'Chevauchement avec une autre mission.'})
                    db.execute('UPDATE missions SET end_date=? WHERE id=?',(r['new_end'],mid))
                db.execute('UPDATE contract_renewals SET status=?,reviewer=?,decided_at=CURRENT_TIMESTAMP WHERE id=?',(v['status'],h.actor,rid));event='RENOUVELLEMENT_'+v['status']
            db.execute('INSERT INTO mission_events(entity_id,event) VALUES(?,?)',(mid,event))
        return h.json_response(201 if method=='POST' else 200,{'id':rid})
    except (ValueError,TypeError,UnicodeError,OverflowError):return h.json_response(400,{'error':'Champs invalides.'})
    except sqlite3.IntegrityError:return h.json_response(409,{'error':'Une demande est déjà en attente.'})
