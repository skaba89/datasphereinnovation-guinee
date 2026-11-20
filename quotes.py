"""Private commercial estimates. All amounts are computed server-side."""
import json
import re
import sqlite3
import uuid
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlsplit, parse_qs

FIELDS = ('opportunity_id','title','scope','mode','currency','days','rate','daily_cost','expenses','fixed_price','status')
STATUSES = ('BROUILLON','PROPOSE','ACCEPTE','REFUSE')

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
        except ValueError: return h.json_response(400,{'error':'Page invalide.'})
        with connect() as db:
            db.row_factory=sqlite3.Row
            rows=[dict(r) for r in db.execute('SELECT q.*,o.company FROM quotes q JOIN opportunities o ON q.opportunity_id=o.id ORDER BY q.created_at DESC,q.id DESC LIMIT 25 OFFSET ?',((page-1)*25,))]
            total=db.execute('SELECT count(*) FROM quotes').fetchone()[0]
        return h.json_response(200,{'items':[r|calculate(r) for r in rows],'total':total})
    try:
        n=int(h.headers.get('Content-Length','0'))
        if not 0<n<=16000 or h.headers.get_content_type()!='application/json': raise ValueError()
        data=json.loads(h.rfile.read(n)); version=data.pop('version',None) if isinstance(data,dict) else None
        v=validate(data)
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
            version+=1
            db.execute('UPDATE quotes SET '+','.join(k+'=?' for k in FIELDS)+',version=? WHERE id=?',(*(v[k] for k in FIELDS),version,oid))
        computed=calculate(v)
        db.execute('INSERT INTO quote_events(quote_id,version,snapshot) VALUES(?,?,?)',(oid,version,json.dumps(v|computed,ensure_ascii=False)))
    return h.json_response(201 if method=='POST' else 200,{'id':oid,'version':version,**computed})
