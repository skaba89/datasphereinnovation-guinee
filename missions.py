"""Private mission register and daily activity approval."""
import json, re, sqlite3, uuid
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlsplit, parse_qs
import quotes
import accounts

def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS missions(id TEXT PRIMARY KEY, quote_id TEXT NOT NULL UNIQUE, opportunity_id TEXT NOT NULL UNIQUE, consultant_id TEXT NOT NULL, contract_ref TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'ACTIVE', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    db.execute('''CREATE TABLE IF NOT EXISTS activity(id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, consultant_id TEXT NOT NULL, work_date TEXT NOT NULL, worked TEXT NOT NULL, billable TEXT NOT NULL, expenses TEXT NOT NULL, description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'SOUMIS', UNIQUE(mission_id,consultant_id,work_date))''')
    db.execute('''CREATE TABLE IF NOT EXISTS mission_events(id INTEGER PRIMARY KEY, entity_id TEXT NOT NULL, event TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    db.execute('''CREATE TABLE IF NOT EXISTS mission_members(mission_id TEXT NOT NULL, consultant_id TEXT NOT NULL, PRIMARY KEY(mission_id,consultant_id))''')
    if 'consultant_id' not in {r[1] for r in db.execute('PRAGMA table_info(activity)')}:
        with db:
            db.execute('BEGIN IMMEDIATE')
            if 'consultant_id' not in {r[1] for r in db.execute('PRAGMA table_info(activity)')}:
                db.execute('ALTER TABLE activity RENAME TO activity_legacy')
                db.execute('''CREATE TABLE activity(id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, consultant_id TEXT NOT NULL, work_date TEXT NOT NULL, worked TEXT NOT NULL, billable TEXT NOT NULL, expenses TEXT NOT NULL, description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'SOUMIS', UNIQUE(mission_id,consultant_id,work_date))''')
                db.execute('''INSERT INTO activity SELECT a.id,a.mission_id,m.consultant_id,a.work_date,a.worked,a.billable,a.expenses,a.description,a.status FROM activity_legacy a LEFT JOIN missions m ON m.id=a.mission_id''')
                db.execute('DROP TABLE activity_legacy')

def member(db,mid,cid):
    return db.execute('SELECT 1 FROM missions WHERE id=? AND consultant_id=? UNION SELECT 1 FROM mission_members WHERE mission_id=? AND consultant_id=?',(mid,cid,mid,cid)).fetchone()

def conflict(db,cid,start,end):
    return db.execute("SELECT 1 FROM missions m WHERE m.status='ACTIVE' AND m.start_date<=? AND m.end_date>=? AND (m.consultant_id=? OR EXISTS(SELECT 1 FROM mission_members x WHERE x.mission_id=m.id AND x.consultant_id=?))",(end,start,cid,cid)).fetchone()

def amounts(m, entries):
    approved=[e for e in entries if e['status']=='VALIDE']
    worked=sum((Decimal(e['worked']) for e in approved),Decimal(0))
    billable=sum((Decimal(e['billable']) for e in approved),Decimal(0))
    expense=sum((Decimal(e['expenses']) for e in approved),Decimal(0))
    unit=Decimal('1' if m['currency'] in ('GNF','XOF') else '0.01')
    money=lambda n:n.quantize(unit,rounding=ROUND_HALF_UP)
    cost=money(worked*Decimal(m['daily_cost'])+expense)
    revenue=money(billable*Decimal(m['rate'])) if m['mode']=='REGIE' else None
    return {'worked':str(worked),'billable':str(billable),'actual_cost':str(cost),'billable_revenue':str(revenue) if revenue is not None else None,'actual_margin':str(revenue-cost) if revenue is not None else None, 'planned_margin':quotes.calculate(m)['margin']}

def handle(h,connect,method):
    if not h.admin_authorized():return
    if (h.headers.get('Origin') and h.headers['Origin']!=h.expected_origin()) or h.headers.get('Sec-Fetch-Site')=='cross-site':return h.json_response(403,{'error':'Origine non autorisée.'})
    path=urlsplit(h.path).path
    if method=='GET':
        try: page=max(1,min(10000,int(parse_qs(urlsplit(h.path).query).get('page',['1'])[0])))
        except ValueError:return h.json_response(400,{'error':'Page invalide.'})
        with connect() as db:
            db.row_factory=sqlite3.Row
            if path.endswith('/eligible'):
                rows=db.execute("SELECT q.id,q.title,o.company,COALESCE(sc.reference,'') contract_ref FROM quotes q JOIN opportunities o ON q.opportunity_id=o.id LEFT JOIN signed_contracts sc ON sc.quote_id=q.id WHERE q.status='ACCEPTE' AND (sc.quote_id IS NOT NULL OR NOT EXISTS(SELECT 1 FROM quote_decisions d WHERE d.quote_id=q.id)) AND NOT EXISTS(SELECT 1 FROM missions m WHERE m.opportunity_id=q.opportunity_id) ORDER BY q.created_at DESC LIMIT 25 OFFSET ?",((page-1)*25,))
                return h.json_response(200,{'items':[dict(r) for r in rows]})
            match=re.fullmatch(r'/api/admin/missions/([0-9a-f-]{36})/activity',path)
            if match:
                if not db.execute('SELECT 1 FROM missions WHERE id=?',(match[1],)).fetchone():return h.json_response(404,{'error':'Mission introuvable.'})
                return h.json_response(200,{'items':[dict(r) for r in db.execute('SELECT * FROM activity WHERE mission_id=? ORDER BY work_date DESC LIMIT 25 OFFSET ?',(match[1],(page-1)*25))],'total':db.execute('SELECT count(*) FROM activity WHERE mission_id=?',(match[1],)).fetchone()[0]})
            rows=[]
            for r in db.execute('SELECT q.*,m.id AS mission_id,m.consultant_id,m.contract_ref,m.start_date,m.end_date,m.status AS mission_status,o.company,c.name AS consultant FROM missions m JOIN quotes q ON q.id=m.quote_id JOIN opportunities o ON o.id=m.opportunity_id JOIN consultants c ON c.id=m.consultant_id ORDER BY m.created_at DESC,m.id LIMIT 25 OFFSET ?',((page-1)*25,)):
                m=dict(r); entries=[dict(e) for e in db.execute('SELECT * FROM activity WHERE mission_id=?',(m['mission_id'],))];m['team']=[{'id':m['consultant_id'],'name':m['consultant']}]+[dict(e) for e in db.execute('SELECT c.id,c.name FROM mission_members x JOIN consultants c ON c.id=x.consultant_id WHERE x.mission_id=? ORDER BY c.name,c.id',(m['mission_id'],))];rows.append(m|amounts(m,entries))
            return h.json_response(200,{'items':rows,'total':db.execute('SELECT count(*) FROM missions').fetchone()[0],'can_write':accounts.allowed(h.role,'missions','POST')})
    try:
        n=int(h.headers.get('Content-Length','0'))
        if not 0<n<=16000 or h.headers.get_content_type()!='application/json':raise ValueError()
        v=json.loads(h.rfile.read(n))
        if not isinstance(v,dict) or any(not isinstance(x,str) or len(x)>2000 or '\x00' in x for x in v.values()):raise ValueError()
        v={k:x.strip() for k,x in v.items()}
        with connect() as db:
            db.row_factory=sqlite3.Row;db.execute('BEGIN IMMEDIATE')
            if path=='/api/admin/missions' and method=='POST':
                if set(v)!={'quote_id','consultant_id','contract_ref','start_date','end_date'} or not v['contract_ref'] or len(v['contract_ref'])>180:raise ValueError()
                start=date.fromisoformat(v['start_date']);end=date.fromisoformat(v['end_date'])
                if start>end or start.isoformat()!=v['start_date'] or end.isoformat()!=v['end_date']:raise ValueError()
                q=db.execute("SELECT * FROM quotes WHERE id=? AND status='ACCEPTE'",(v['quote_id'],)).fetchone()
                if not q or not db.execute("SELECT 1 FROM consultants WHERE id=? AND status='DISPONIBLE'",(v['consultant_id'],)).fetchone():raise ValueError()
                sc=db.execute('SELECT reference,signed_date FROM signed_contracts WHERE quote_id=?',(q['id'],)).fetchone()
                if not sc and db.execute('SELECT 1 FROM quote_decisions WHERE quote_id=?',(q['id'],)).fetchone():return h.json_response(409,{'error':'Enregistrez le contrat signé avant la mission.'})
                if sc and (sc['reference']!=v['contract_ref'] or v['start_date']<sc['signed_date']):return h.json_response(409,{'error':'Référence ou début incompatible avec le contrat signé.'})
                if conflict(db,v['consultant_id'],v['start_date'],v['end_date']):return h.json_response(409,{'error':'Consultant déjà affecté sur cette période.'})
                oid=str(uuid.uuid4());db.execute('INSERT INTO missions(id,quote_id,opportunity_id,consultant_id,contract_ref,start_date,end_date) VALUES(?,?,?,?,?,?,?)',(oid,v['quote_id'],q['opportunity_id'],v['consultant_id'],v['contract_ref'],v['start_date'],v['end_date']));event='MISSION_CREEE'
            elif method=='POST' and path.endswith('/team'):
                mid=path.split('/')[-2];m=db.execute("SELECT * FROM missions WHERE id=? AND status='ACTIVE'",(mid,)).fetchone()
                if not m or set(v)!={'consultant_id'} or not db.execute("SELECT 1 FROM consultants WHERE id=? AND status='DISPONIBLE'",(v['consultant_id'],)).fetchone():raise ValueError()
                if conflict(db,v['consultant_id'],m['start_date'],m['end_date']):return h.json_response(409,{'error':'Consultant déjà affecté sur cette période.'})
                db.execute('INSERT INTO mission_members VALUES(?,?)',(mid,v['consultant_id']));oid=mid;event='EQUIPE_AJOUT_'+v['consultant_id']
            elif method=='POST' and path.endswith('/activity'):
                mid=path.split('/')[-2];m=db.execute("SELECT m.*,q.currency,q.mode FROM missions m JOIN quotes q ON q.id=m.quote_id WHERE m.id=? AND m.status='ACTIVE'",(mid,)).fetchone()
                if not m:raise ValueError()
                cid=v.pop('consultant_id',m['consultant_id'])
                if not member(db,mid,cid) or set(v)!={'work_date','worked','billable','expenses','description'} or not v['description']:raise ValueError()
                day=date.fromisoformat(v['work_date'])
                if day.isoformat()!=v['work_date'] or not m['start_date']<=v['work_date']<=m['end_date'] or day>date.today():raise ValueError()
                if any(not re.fullmatch(r'\d{1,12}(?:\.\d{1,2})?',v[k]) for k in ('worked','billable','expenses')):raise ValueError()
                w,b,e=(Decimal(v[k]) for k in ('worked','billable','expenses'))
                if not 0<w<=1 or not 0<=b<=w or (m['mode']=='FORFAIT' and b!=0) or (m['currency'] in ('GNF','XOF') and e%1):raise ValueError()
                oid=str(uuid.uuid4());db.execute('INSERT INTO activity(id,mission_id,consultant_id,work_date,worked,billable,expenses,description) VALUES(?,?,?,?,?,?,?,?)',(oid,mid,cid,v['work_date'],v['worked'],v['billable'],v['expenses'],v['description']));event='CRA_SOUMIS'
            elif method=='PATCH' and '/activity/' in path:
                oid=path.rsplit('/',1)[-1]
                if set(v)!={'status'} or v['status'] not in ('VALIDE','REFUSE'):raise ValueError()
                result=db.execute("UPDATE activity SET status=? WHERE id=? AND status='SOUMIS'",(v['status'],oid))
                if result.rowcount!=1:return h.json_response(409,{'error':'CRA absent ou déjà traité.'})
                event='CRA_'+v['status']
            elif method=='PATCH':
                oid=path.rsplit('/',1)[-1]
                if v!={'status':'TERMINE'}:raise ValueError()
                if db.execute("SELECT 1 FROM contract_renewals WHERE mission_id=? AND status='SOUMIS'",(oid,)).fetchone():return h.json_response(409,{'error':'Renouvellement en attente.'})
                if db.execute("SELECT 1 FROM activity WHERE mission_id=? AND status='SOUMIS'",(oid,)).fetchone():return h.json_response(409,{'error':'CRA en attente.'})
                if db.execute("UPDATE missions SET status='TERMINE' WHERE id=? AND status='ACTIVE'",(oid,)).rowcount!=1:return h.json_response(409,{'error':'Mission absente ou clôturée.'})
                event='MISSION_TERMINEE'
            else:return h.json_response(404,{'error':'Route inconnue.'})
            db.execute('INSERT INTO mission_events(entity_id,event) VALUES(?,?)',(oid,event))
        return h.json_response(201 if method=='POST' else 200,{'id':oid})
    except (ValueError,TypeError,UnicodeError):return h.json_response(400,{'error':'Champs invalides.'})
    except sqlite3.IntegrityError:return h.json_response(409,{'error':'Doublon : enregistrement déjà existant.'})
