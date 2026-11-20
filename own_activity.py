"""Consultant-scoped read and submit, never exposing commercial rates."""
import json,re,uuid,sqlite3
from datetime import date
from decimal import Decimal

def handle(h,connect,method):
    if not h.admin_authorized():return
    if h.role!='CONSULTANT' or not h.consultant_id:return h.json_response(403,{'error':'Réservé au consultant associé.'})
    if (h.headers.get('Origin') and h.headers['Origin']!='http://'+h.headers.get('Host','')) or h.headers.get('Sec-Fetch-Site')=='cross-site':return h.json_response(403,{'error':'Origine interdite.'})
    if method=='GET':
        with connect() as db:
            db.row_factory=sqlite3.Row
            rows=[dict(r) for r in db.execute('SELECT m.id,m.start_date,m.end_date,m.status,q.title,q.mode,q.currency FROM missions m JOIN quotes q ON q.id=m.quote_id WHERE m.consultant_id=? OR EXISTS(SELECT 1 FROM mission_members x WHERE x.mission_id=m.id AND x.consultant_id=?) ORDER BY m.start_date DESC',(h.consultant_id,h.consultant_id))]
            entries=[dict(r) for r in db.execute('SELECT a.* FROM activity a WHERE a.consultant_id=? ORDER BY a.work_date DESC LIMIT 100',(h.consultant_id,))]
        return h.json_response(200,{'missions':rows,'items':entries})
    try:
        size=int(h.headers.get('Content-Length','0'))
        if not 0<size<=16000 or h.headers.get_content_type()!='application/json':raise ValueError()
        v=json.loads(h.rfile.read(size))
        if not isinstance(v,dict) or set(v)!={'mission_id','work_date','worked','billable','expenses','description'} or any(not isinstance(x,str) or len(x)>2000 or '\x00' in x for x in v.values()):raise ValueError()
        v={k:x.strip() for k,x in v.items()}
        day=date.fromisoformat(v['work_date'])
        if day.isoformat()!=v['work_date'] or day>date.today() or not v['description']:raise ValueError()
        if any(not re.fullmatch(r'\d{1,12}(?:\.\d{1,2})?',v[k]) for k in ('worked','billable','expenses')):raise ValueError()
        w,b,e=(Decimal(v[k]) for k in ('worked','billable','expenses'))
        if not 0<w<=1 or not 0<=b<=w:raise ValueError()
        with connect() as db:
            db.row_factory=sqlite3.Row;db.execute('BEGIN IMMEDIATE')
            m=db.execute("SELECT m.*,q.mode,q.currency FROM missions m JOIN quotes q ON q.id=m.quote_id WHERE m.id=? AND m.status='ACTIVE' AND (m.consultant_id=? OR EXISTS(SELECT 1 FROM mission_members x WHERE x.mission_id=m.id AND x.consultant_id=?))",(v['mission_id'],h.consultant_id,h.consultant_id)).fetchone()
            if not m:return h.json_response(403,{'error':'Mission non accessible.'})
            if not m['start_date']<=v['work_date']<=m['end_date'] or (m['mode']=='FORFAIT' and b!=0) or (m['currency'] in ('GNF','XOF') and e%1):raise ValueError()
            oid=str(uuid.uuid4());db.execute('INSERT INTO activity(id,mission_id,consultant_id,work_date,worked,billable,expenses,description) VALUES(?,?,?,?,?,?,?,?)',(oid,v['mission_id'],h.consultant_id,v['work_date'],v['worked'],v['billable'],v['expenses'],v['description']))
            db.execute('INSERT INTO mission_events(entity_id,event) VALUES(?,?)',(oid,'CRA_SOUMIS'))
        return h.json_response(201,{'id':oid})
    except (ValueError,TypeError,UnicodeError):return h.json_response(400,{'error':'Champs invalides.'})
    except sqlite3.IntegrityError:return h.json_response(409,{'error':'CRA déjà enregistré.'})
