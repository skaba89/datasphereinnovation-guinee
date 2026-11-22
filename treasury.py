"""Recorded cash outflows; separate from accrued mission costs."""
import json,re,sqlite3,uuid
from datetime import date
from decimal import Decimal
from urllib.parse import urlsplit,parse_qs
import billing

CURRENCIES=('GNF','XOF','EUR','USD')
CATEGORIES=('CONSULTANT','REMBOURSEMENT','FONCTIONNEMENT','AUTRE')

def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS expenses(id TEXT PRIMARY KEY, reference TEXT NOT NULL UNIQUE COLLATE NOCASE, currency TEXT NOT NULL, amount TEXT NOT NULL, paid_date TEXT NOT NULL, category TEXT NOT NULL, description TEXT NOT NULL, mission_id TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')

def cash(db):
    buckets={}
    def bucket(c):return buckets.setdefault(c,{'received':Decimal(0),'outflows':Decimal(0)})
    for r in db.execute('SELECT q.currency,p.amount FROM payments p JOIN invoices i ON i.id=p.invoice_id JOIN missions m ON m.id=i.mission_id JOIN quotes q ON q.id=m.quote_id'):
        bucket(r[0])['received']+=Decimal(r[1])
    for r in db.execute('SELECT currency,amount FROM expenses'):
        bucket(r[0])['outflows']+=Decimal(r[1])
    return [{'currency':c,**{k:str(v) for k,v in b.items()},'net_flow':str(b['received']-b['outflows'])} for c,b in sorted(buckets.items())]

def handle(h,connect,method):
    if not h.admin_authorized():return
    if (h.headers.get('Origin') and h.headers['Origin']!=h.expected_origin()) or h.headers.get('Sec-Fetch-Site')=='cross-site':return h.json_response(403,{'error':'Origine non autorisée.'})
    if method=='GET':
        try:
            query=parse_qs(urlsplit(h.path).query)
            page=max(1,min(10000,int(query.get('page',['1'])[0])))
            page_size=int(query.get('page_size',['25'])[0])
            if page_size not in (10,25,50):raise ValueError()
        except ValueError:return h.json_response(400,{'error':'Page invalide.'})
        with connect() as db:
            db.row_factory=sqlite3.Row;db.execute('BEGIN')
            items=[dict(r) for r in db.execute('SELECT e.*,q.title AS mission_title FROM expenses e LEFT JOIN missions m ON m.id=e.mission_id LEFT JOIN quotes q ON q.id=m.quote_id ORDER BY paid_date DESC,e.id LIMIT ? OFFSET ?',(page_size,(page-1)*page_size))]
            return h.json_response(200,{'items':items,'total':db.execute('SELECT count(*) FROM expenses').fetchone()[0],'cash':cash(db)})
    try:
        size=int(h.headers.get('Content-Length','0'))
        if not 0<size<=8000 or h.headers.get_content_type()!='application/json':raise ValueError()
        v=json.loads(h.rfile.read(size))
        if not isinstance(v,dict) or set(v)!={'reference','currency','amount','paid_date','category','description','mission_id'} or any(not isinstance(x,str) or len(x)>180 or '\x00' in x for x in v.values()):raise ValueError()
        v={k:x.strip() for k,x in v.items()}
        if not v['reference'] or not v['description'] or v['currency'] not in CURRENCIES or v['category'] not in CATEGORIES or date.fromisoformat(v['paid_date']).isoformat()!=v['paid_date'] or v['paid_date']>date.today().isoformat():raise ValueError()
        a=billing.amount(v['amount'],v['currency'])
        with connect() as db:
            db.row_factory=sqlite3.Row;db.execute('BEGIN IMMEDIATE')
            if v['mission_id']:
                m=billing.mission(db,v['mission_id'])
                if not m or m['currency']!=v['currency']:raise ValueError()
            oid=str(uuid.uuid4());db.execute('INSERT INTO expenses(id,reference,currency,amount,paid_date,category,description,mission_id,actor) VALUES(?,?,?,?,?,?,?,?,?)',(oid,v['reference'],v['currency'],str(a),v['paid_date'],v['category'],v['description'],v['mission_id'],h.actor));db.execute('INSERT INTO billing_events(entity_id,event) VALUES(?,?)',(oid,'DECAISSEMENT_ENREGISTRE'))
        return h.json_response(201,{'id':oid})
    except (ValueError,TypeError,UnicodeError):return h.json_response(400,{'error':'Champs invalides.'})
    except sqlite3.IntegrityError:return h.json_response(409,{'error':'Référence de dépense déjà enregistrée.'})
