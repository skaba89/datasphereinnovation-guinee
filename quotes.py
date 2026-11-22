"""Private commercial estimates. All amounts are computed server-side."""
import json
import re
import sqlite3
import uuid
from datetime import date
import accounts
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlsplit, parse_qs

FIELDS = ('opportunity_id','title','scope','mode','currency','days','rate','daily_cost','expenses','fixed_price','status')
STATUSES = ('BROUILLON','PROPOSE','ACCEPTE','REFUSE')

def incomplete_template(*values):
    return any('[à préciser]' in (value or '').casefold() for value in values)

def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS quotes(id TEXT PRIMARY KEY,
        opportunity_id TEXT NOT NULL, title TEXT NOT NULL, scope TEXT NOT NULL,
        mode TEXT NOT NULL, currency TEXT NOT NULL, days TEXT NOT NULL, rate TEXT NOT NULL,
        daily_cost TEXT NOT NULL, expenses TEXT NOT NULL, fixed_price TEXT NOT NULL,
        status TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    db.execute('''CREATE TABLE IF NOT EXISTS quote_events(id INTEGER PRIMARY KEY,
        quote_id TEXT NOT NULL, version INTEGER NOT NULL, snapshot TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')

    db.execute("""CREATE TABLE IF NOT EXISTS quote_proposal_terms (
        quote_id TEXT PRIMARY KEY REFERENCES quotes(id), valid_until TEXT NOT NULL,
        terms TEXT NOT NULL)""")


    db.execute("""CREATE TABLE IF NOT EXISTS quote_transmissions (
        quote_id TEXT NOT NULL, version INTEGER NOT NULL, actor TEXT NOT NULL,
        evidence TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(quote_id,version))""")
    db.execute("""CREATE TABLE IF NOT EXISTS quote_decisions (
        quote_id TEXT PRIMARY KEY, version INTEGER NOT NULL, actor TEXT NOT NULL,
        decision TEXT NOT NULL, evidence TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")


    db.execute("""CREATE TABLE IF NOT EXISTS signed_contracts (
        quote_id TEXT PRIMARY KEY REFERENCES quotes(id), quote_version INTEGER NOT NULL,
        reference TEXT NOT NULL UNIQUE COLLATE NOCASE, signed_date TEXT NOT NULL,
        evidence TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")

def register_contract(h,connect,oid):
    if not h.admin_authorized():return
    if h.role not in ('ADMIN','COMMERCIAL'):return h.json_response(403,{'error':'Permission insuffisante.'})
    try:
        n=int(h.headers.get('Content-Length','0'))
        if not 0<n<=8192 or h.headers.get_content_type()!='application/json':raise ValueError()
        v=json.loads(h.rfile.read(n))
        if not isinstance(v,dict) or set(v)!={'version','reference','signed_date','evidence'} or type(v['version']) is not int:raise ValueError()
        for k,maxlen in [('reference',180),('evidence',1000),('signed_date',10)]:
            if not isinstance(v[k],str) or not v[k].strip() or len(v[k])>maxlen or '\x00' in v[k]:raise ValueError()
            v[k]=v[k].strip()
        d=date.fromisoformat(v['signed_date'])
        if d.isoformat()!=v['signed_date'] or d>date.today():raise ValueError()
    except (ValueError,TypeError,UnicodeError):return h.json_response(400,{'error':'Référence, date ou preuve invalide.'})
    try:
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            q=db.execute("SELECT version FROM quotes WHERE id=? AND status='ACCEPTE'",(oid,)).fetchone()
            if not q or q[0]!=v['version']:return h.json_response(409,{'error':'Devis non accepté ou version modifiée.'})
            m=db.execute('SELECT contract_ref FROM missions WHERE quote_id=?',(oid,)).fetchone()
            if m and m[0]!=v['reference']:return h.json_response(409,{'error':'Référence différente de la mission existante.'})
            db.execute('INSERT INTO signed_contracts(quote_id,quote_version,reference,signed_date,evidence,actor) VALUES(?,?,?,?,?,?)',(oid,v['version'],v['reference'],v['signed_date'],v['evidence'],h.actor))
            accounts.event(db,h.actor,'CONTRAT_SIGNATURE_ENREGISTREE',oid)
        return h.json_response(201,{'id':oid})
    except sqlite3.IntegrityError:return h.json_response(409,{'error':'Contrat ou référence déjà enregistré.'})

def calculate(v):
    unit = Decimal('1' if v['currency'] in ('GNF','XOF') else '0.01')
    days,rate,cost,expenses,fixed = (Decimal(v[k]) for k in FIELDS[5:10])
    money = lambda n: n.quantize(unit, rounding=ROUND_HALF_UP)
    revenue = money(days*rate if v['mode']=='REGIE' else fixed)
    direct = money(days*cost+expenses)
    margin = revenue-direct
    percent = (margin*100/revenue).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if revenue else None
    return {'revenue':str(revenue),'direct_cost':str(direct),'margin':str(margin),'margin_pct':str(percent) if percent is not None else None}

def validate(v):
    if not isinstance(v,dict) or set(v)!=set(FIELDS): raise ValueError()
    if any(not isinstance(x,str) or '\x00' in x or len(x)>4000 for x in v.values()): raise ValueError()
    v={k:x.strip() for k,x in v.items()}
    if not v['title'] or len(v['title'])>180 or not v['scope']: raise ValueError()
    if str(uuid.UUID(v['opportunity_id']))!=v['opportunity_id']: raise ValueError()
    if v['mode'] not in ('REGIE','FORFAIT') or v['currency'] not in ('GNF','XOF','EUR','USD') or v['status'] not in STATUSES: raise ValueError()
    for k in FIELDS[5:10]:
        if not re.fullmatch(r'\d{1,12}(?:\.\d{1,2})?',v[k]): raise ValueError()
        if k!='days' and v['currency'] in ('GNF','XOF') and Decimal(v[k])%1: raise ValueError()
    if not Decimal(v['days']) or not Decimal(v['rate' if v['mode']=='REGIE' else 'fixed_price']): raise ValueError()
    return v

def handle(h,connect,method):
    if not h.admin_authorized(): return
    if (h.headers.get('Origin') and h.headers['Origin']!=h.expected_origin()) or h.headers.get('Sec-Fetch-Site')=='cross-site':
        return h.json_response(403,{'error':'Origine non autorisée.'})
    if method=='GET':
        q=parse_qs(urlsplit(h.path).query)
        try:
            page=max(1,min(10000,int(q.get('page',['1'])[0])))
            size=int(q.get('page_size',['25'])[0])
            if size not in (10,25,50):raise ValueError()
        except ValueError: return h.json_response(400,{'error':'Page invalide.'})
        with connect() as db:
            db.row_factory=sqlite3.Row
            search=q.get('q',[''])[0].strip()[:120]
            source=' FROM quotes q JOIN opportunities o ON q.opportunity_id=o.id LEFT JOIN quote_proposal_terms p ON p.quote_id=q.id WHERE instr(lower(q.title),lower(?))>0 OR instr(lower(o.company),lower(?))>0 OR instr(lower(q.status),lower(?))>0 OR instr(lower(q.currency),lower(?))>0'
            args=(search,)*4
            rows=[dict(r) for r in db.execute('SELECT q.*,o.company,COALESCE(p.valid_until,\'\') valid_until,COALESCE(p.terms,\'\') terms'+source+' ORDER BY q.created_at DESC,q.id DESC LIMIT ? OFFSET ?',(*args,size,(page-1)*size))]
            for row in rows:
                row['transmission']=dict(t) if (t:=db.execute('SELECT version,actor,evidence,created_at FROM quote_transmissions WHERE quote_id=? ORDER BY version DESC LIMIT 1',(row['id'],)).fetchone()) else None
                row['contract']=dict(c) if (c:=db.execute('SELECT reference,signed_date,actor,created_at FROM signed_contracts WHERE quote_id=?',(row['id'],)).fetchone()) else None
                row['decision']=dict(d) if (d:=db.execute('SELECT version,actor,decision,evidence,created_at FROM quote_decisions WHERE quote_id=?',(row['id'],)).fetchone()) else None
            total=db.execute('SELECT count(*)'+source,args).fetchone()[0]
        return h.json_response(200,{'items':[r|calculate(r) for r in rows],'total':total,'can_manage':h.role in ('ADMIN','COMMERCIAL')})
    try:
        n=int(h.headers.get('Content-Length','0'))
        if not 0<n<=16000 or h.headers.get_content_type()!='application/json': raise ValueError()
        data=json.loads(h.rfile.read(n)); version=data.pop('version',None) if isinstance(data,dict) else None
        metadata=None
        if isinstance(data,dict) and ('valid_until' in data or 'terms' in data):
            until=data.pop('valid_until','');terms=data.pop('terms','')
            if not isinstance(until,str) or not isinstance(terms,str) or len(terms)>2000 or '\x00' in terms or (until and (len(until)!=10 or date.fromisoformat(until).isoformat()!=until)):
                raise ValueError()
            metadata=(until,terms.strip())
        v=validate(data)
        if v['status'] != 'BROUILLON' and incomplete_template(v['title'],v['scope'],metadata[1] if metadata else ''):
            return h.json_response(400,{'error':'Complétez les éléments [à préciser] du modèle avant de proposer le devis.'})
        if method=='PATCH' and (type(version) is not int or version<1): raise ValueError()
        if method=='POST' and version is not None: raise ValueError()
    except (ValueError,TypeError,UnicodeError): return h.json_response(400,{'error':'Champs invalides.'})
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM opportunities WHERE id=?',(v['opportunity_id'],)).fetchone(): return h.json_response(400,{'error':'Opportunité introuvable.'})
        if method=='POST':
            oid=str(uuid.uuid4()); version=1
            db.execute('INSERT INTO quotes(id,'+','.join(FIELDS)+') VALUES('+','.join('?' for _ in range(len(FIELDS)+1))+')',(oid,*(v[k] for k in FIELDS)))
        else:
            oid=h.path.rsplit('/',1)[-1]
            row=db.execute('SELECT version,status FROM quotes WHERE id=?',(oid,)).fetchone()
            if not row: return h.json_response(404,{'error':'Devis introuvable.'})
            if row[0]!=version: return h.json_response(409,{'error':'Devis modifié. Actualisez.'})
            if row[1] in ('ACCEPTE','REFUSE'): return h.json_response(409,{'error':'Devis clôturé. Créez une nouvelle proposition.'})
            if db.execute('SELECT 1 FROM quote_transmissions WHERE quote_id=? AND version=?',(oid,version)).fetchone(): return h.json_response(409,{'error':'Proposition transmise : utilisez le suivi de décision.'})
            if metadata is None and v['status'] != 'BROUILLON':
                previous=db.execute('SELECT terms FROM quote_proposal_terms WHERE quote_id=?',(oid,)).fetchone()
                if previous and incomplete_template(previous[0]):return h.json_response(400,{'error':'Complétez les conditions [à préciser] du modèle.'})
            version+=1
            db.execute('UPDATE quotes SET '+','.join(k+'=?' for k in FIELDS)+',version=? WHERE id=?',(*(v[k] for k in FIELDS),version,oid))
        if metadata is not None:
            db.execute("""INSERT INTO quote_proposal_terms VALUES (?,?,?)
                ON CONFLICT(quote_id) DO UPDATE SET valid_until=excluded.valid_until,terms=excluded.terms""",(oid,*metadata))
        stored=db.execute('SELECT valid_until,terms FROM quote_proposal_terms WHERE quote_id=?',(oid,)).fetchone()
        computed=calculate(v)
        db.execute('INSERT INTO quote_events(quote_id,version,snapshot) VALUES(?,?,?)',(oid,version,json.dumps(v|computed|({'valid_until':stored[0],'terms':stored[1]} if stored else {}),ensure_ascii=False)))
    return h.json_response(201 if method=='POST' else 200,{'id':oid,'version':version,**computed})


def record_transmission(h,connect,oid):
    if not h.admin_authorized():return
    if h.role not in ('ADMIN','COMMERCIAL'):
        return h.json_response(403,{'error':'Permission insuffisante.'})
    try:
        size=int(h.headers.get('Content-Length','0'))
        if not 0<size<=8192 or h.headers.get_content_type()!='application/json':raise ValueError()
        v=json.loads(h.rfile.read(size))
        if not isinstance(v,dict) or set(v)!={'version','action','evidence'} or type(v['version']) is not int or v['action'] not in ('TRANSMIS','ACCEPTE','REFUSE') or not isinstance(v['evidence'],str) or not v['evidence'].strip() or len(v['evidence'])>1000 or '\x00' in v['evidence']:raise ValueError()
    except (ValueError,TypeError):return h.json_response(400,{'error':'Preuve ou action invalide.'})
    with connect() as db:
        db.row_factory=sqlite3.Row
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT q.*,p.valid_until,p.terms FROM quotes q LEFT JOIN quote_proposal_terms p ON p.quote_id=q.id WHERE q.id=?',(oid,)).fetchone()
        if not row:return h.json_response(404,{'error':'Devis introuvable.'})
        if row['version']!=v['version'] or row['status']!='PROPOSE':return h.json_response(409,{'error':'Version ou statut incompatible.'})
        sent=db.execute('SELECT 1 FROM quote_transmissions WHERE quote_id=? AND version=?',(oid,v['version'])).fetchone()
        if v['action']=='TRANSMIS':
            if incomplete_template(row['title'],row['scope'],row['terms']):return h.json_response(409,{'error':'Modèle incomplet : complétez les éléments [à préciser].'})
            if sent or not row['valid_until'] or row['valid_until']<date.today().isoformat():return h.json_response(409,{'error':'Déjà transmis ou validité absente/expirée.'})
            db.execute('INSERT INTO quote_transmissions(quote_id,version,actor,evidence) VALUES (?,?,?,?)',(oid,v['version'],h.actor,v['evidence'].strip()))
        else:
            if not sent:return h.json_response(409,{'error':'Transmission non enregistrée.'})
            if v['action']=='ACCEPTE' and row['valid_until']<date.today().isoformat():return h.json_response(409,{'error':'Proposition expirée.'})
            db.execute('INSERT INTO quote_decisions(quote_id,version,actor,decision,evidence) VALUES (?,?,?,?,?)',(oid,v['version'],h.actor,v['action'],v['evidence'].strip()))
            db.execute('UPDATE quotes SET status=?,version=version+1 WHERE id=?',(v['action'],oid))
            snapshot={k:row[k] for k in FIELDS}|calculate(row)|{'status':v['action'],'valid_until':row['valid_until'],'terms':row['terms']}
            db.execute('INSERT INTO quote_events(quote_id,version,snapshot) VALUES (?,?,?)',(oid,v['version']+1,json.dumps(snapshot,ensure_ascii=False)))
        accounts.event(db,h.actor,'DEVIS_'+v['action'],oid)
    return h.json_response(200,{'status':v['action']})
