"""Internal receivables ledger, not statutory invoicing or accounting."""
import json, re, sqlite3, uuid
from datetime import date
from decimal import Decimal
from urllib.parse import urlsplit, parse_qs
import missions
import quotes

def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS milestones(id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, title TEXT NOT NULL, amount TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'PREVU')''')
    db.execute('''CREATE TABLE IF NOT EXISTS invoices(id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, reference TEXT NOT NULL UNIQUE, amount TEXT NOT NULL, due_date TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    db.execute('''CREATE TABLE IF NOT EXISTS payments(id TEXT PRIMARY KEY, invoice_id TEXT NOT NULL, reference TEXT NOT NULL UNIQUE, amount TEXT NOT NULL, paid_date TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS billing_events(id INTEGER PRIMARY KEY, entity_id TEXT NOT NULL, event TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')

def total(rows):return sum((Decimal(r[0]) for r in rows),Decimal(0))
def amount(value,currency):
    if not re.fullmatch(r'\d{1,12}(?:\.\d{1,2})?',value):raise ValueError()
    n=Decimal(value)
    if n<=0 or (currency in ('GNF','XOF') and n%1):raise ValueError()
    return n

def mission(db,mid):
    return db.execute('SELECT q.*,m.id AS mission_id FROM missions m JOIN quotes q ON q.id=m.quote_id WHERE m.id=?',(mid,)).fetchone()

def billable(db,m):
    mid=m['mission_id']
    if m['mode']=='FORFAIT':return total(db.execute("SELECT amount FROM milestones WHERE mission_id=? AND status='VALIDE'",(mid,)))
    return Decimal(missions.amounts(dict(m),[dict(r) for r in db.execute('SELECT * FROM activity WHERE mission_id=?',(mid,))])['billable_revenue'])

def handle(h,connect,method):
    if not h.admin_authorized():return
    if (h.headers.get('Origin') and h.headers['Origin']!=h.expected_origin()) or h.headers.get('Sec-Fetch-Site')=='cross-site':return h.json_response(403,{'error':'Origine interdite.'})
    path=urlsplit(h.path).path; kind=path.split('/')[4] if len(path.split('/'))>4 else ''
    if method=='GET':
        try:page=max(1,min(10000,int(parse_qs(urlsplit(h.path).query).get('page',['1'])[0])))
        except ValueError:return h.json_response(400,{'error':'Page invalide.'})
        with connect() as db:
            db.row_factory=sqlite3.Row
            if kind=='contracts':
                items=[]
                today=date.today().isoformat()
                for record in db.execute("""SELECT q.*, m.id mission_id,m.contract_ref,m.status mission_status,
                    o.company,sc.signed_date FROM missions m JOIN quotes q ON q.id=m.quote_id
                    JOIN opportunities o ON o.id=m.opportunity_id LEFT JOIN signed_contracts sc ON sc.quote_id=q.id
                    ORDER BY m.created_at DESC,m.id LIMIT 25 OFFSET ?""",((page-1)*25,)):
                    m=dict(record);mid=m['mission_id']
                    planned=Decimal(quotes.calculate(m)['revenue'])
                    activity=missions.amounts(m,[dict(a) for a in db.execute('SELECT * FROM activity WHERE mission_id=?',(mid,))])
                    earned=billable(db,m);cost=Decimal(activity['actual_cost'])
                    invoiced=paid=overdue=Decimal(0)
                    for invoice in db.execute('SELECT id,amount,due_date FROM invoices WHERE mission_id=?',(mid,)):
                        received=total(db.execute('SELECT amount FROM payments WHERE invoice_id=?',(invoice['id'],)))
                        invoiced+=Decimal(invoice['amount']);paid+=received
                        if invoice['due_date']<today:overdue+=Decimal(invoice['amount'])-received
                    unit=Decimal('1' if m['currency'] in ('GNF','XOF') else '0.01')
                    values={'planned':planned,'earned':earned,'invoiced':invoiced,'paid':paid,
                            'balance':invoiced-paid,'overdue':overdue,'remaining_billable':earned-invoiced,
                            'actual_cost':cost,'earned_margin':earned-cost}
                    items.append({k:m[k] for k in ('mission_id','contract_ref','mission_status','company','title','currency','signed_date')}|
                        {k:str(v.quantize(unit)) for k,v in values.items()})
                return h.json_response(200,{'items':items,'total':db.execute('SELECT count(*) FROM missions').fetchone()[0]})
            if kind=='milestones':
                rows=[dict(r) for r in db.execute('SELECT j.*,q.currency,q.title AS mission_title FROM milestones j JOIN missions m ON m.id=j.mission_id JOIN quotes q ON q.id=m.quote_id ORDER BY j.id LIMIT 25 OFFSET ?',((page-1)*25,))]
                return h.json_response(200,{'items':rows,'total':db.execute('SELECT count(*) FROM milestones').fetchone()[0]})
            items=[]; totals={};today=date.today().isoformat()
            for r in db.execute('SELECT i.*,q.currency,q.title FROM invoices i JOIN missions m ON m.id=i.mission_id JOIN quotes q ON q.id=m.quote_id ORDER BY i.created_at DESC,i.id'):
                x=dict(r);paid=total(db.execute('SELECT amount FROM payments WHERE invoice_id=?',(x['id'],)));due=Decimal(x['amount'])-paid
                x.update(paid=str(paid),balance=str(due),overdue=due>0 and x['due_date']<today)
                t=totals.setdefault(x['currency'],{'invoiced':Decimal(0),'paid':Decimal(0),'balance':Decimal(0),'overdue':Decimal(0)})
                t['invoiced']+=Decimal(x['amount']);t['paid']+=paid;t['balance']+=due;t['overdue']+=due if x['overdue'] else 0;items.append(x)
            return h.json_response(200,{'items':items[(page-1)*25:page*25],'total':len(items),'totals':{c:{k:str(v) for k,v in t.items()} for c,t in totals.items()}})
    try:
        n=int(h.headers.get('Content-Length','0'))
        if not 0<n<=16000 or h.headers.get_content_type()!='application/json':raise ValueError()
        v=json.loads(h.rfile.read(n))
        if not isinstance(v,dict) or any(not isinstance(x,str) or len(x)>180 or '\x00' in x for x in v.values()):raise ValueError()
        v={k:x.strip() for k,x in v.items()};oid=str(uuid.uuid4())
        with connect() as db:
            db.row_factory=sqlite3.Row;db.execute('BEGIN IMMEDIATE')
            if method=='PATCH' and kind=='milestones':
                oid=path.rsplit('/',1)[-1]
                if v!={'status':'VALIDE'}:raise ValueError()
                if db.execute("UPDATE milestones SET status='VALIDE' WHERE id=? AND status='PREVU'",(oid,)).rowcount!=1:return h.json_response(409,{'error':'Jalon absent ou déjà validé.'})
                event='JALON_VALIDE'
            elif kind=='milestones':
                if set(v)!={'mission_id','title','amount'} or not v['title']:raise ValueError()
                m=mission(db,v['mission_id'])
                if not m or m['mode']!='FORFAIT':raise ValueError()
                a=amount(v['amount'],m['currency']);used=total(db.execute('SELECT amount FROM milestones WHERE mission_id=?',(v['mission_id'],)))
                if used+a>Decimal(m['fixed_price']):return h.json_response(409,{'error':'Montant supérieur au forfait.'})
                db.execute('INSERT INTO milestones(id,mission_id,title,amount) VALUES(?,?,?,?)',(oid,v['mission_id'],v['title'],str(a)));event='JALON_CREE'
            elif kind=='invoices':
                if set(v)!={'mission_id','reference','amount','due_date'} or not v['reference'] or date.fromisoformat(v['due_date']).isoformat()!=v['due_date']:raise ValueError()
                m=mission(db,v['mission_id'])
                if not m:raise ValueError()
                a=amount(v['amount'],m['currency']);used=total(db.execute('SELECT amount FROM invoices WHERE mission_id=?',(v['mission_id'],)))
                if used+a>billable(db,m):return h.json_response(409,{'error':'Montant supérieur au disponible facturable validé.'})
                db.execute('INSERT INTO invoices(id,mission_id,reference,amount,due_date) VALUES(?,?,?,?,?)',(oid,v['mission_id'],v['reference'],str(a),v['due_date']));event='CREANCE_ENREGISTREE'
            elif kind=='payments':
                if set(v)!={'invoice_id','reference','amount','paid_date'} or not v['reference'] or date.fromisoformat(v['paid_date']).isoformat()!=v['paid_date'] or v['paid_date']>date.today().isoformat():raise ValueError()
                i=db.execute('SELECT * FROM invoices WHERE id=?',(v['invoice_id'],)).fetchone()
                if not i:raise ValueError()
                m=mission(db,i['mission_id']);a=amount(v['amount'],m['currency']);paid=total(db.execute('SELECT amount FROM payments WHERE invoice_id=?',(i['id'],)))
                if paid+a>Decimal(i['amount']):return h.json_response(409,{'error':'Paiement supérieur au solde.'})
                db.execute('INSERT INTO payments(id,invoice_id,reference,amount,paid_date) VALUES(?,?,?,?,?)',(oid,i['id'],v['reference'],str(a),v['paid_date']));event='PAIEMENT_ENREGISTRE'
            else:return h.json_response(404,{'error':'Route inconnue.'})
            db.execute('INSERT INTO billing_events(entity_id,event) VALUES(?,?)',(oid,event))
        return h.json_response(200 if method=='PATCH' else 201,{'id':oid})
    except (ValueError,TypeError,UnicodeError):return h.json_response(400,{'error':'Champs invalides.'})
    except sqlite3.IntegrityError:return h.json_response(409,{'error':'Référence déjà enregistrée.'})
