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

    db.execute("""CREATE TABLE IF NOT EXISTS billing_schedule(
        id TEXT PRIMARY KEY, mission_id TEXT NOT NULL REFERENCES missions(id),
        label TEXT NOT NULL, kind TEXT NOT NULL, amount TEXT NOT NULL, due_date TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'PREVU', invoice_id TEXT UNIQUE REFERENCES invoices(id),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")

    db.execute("""CREATE TABLE IF NOT EXISTS billing_reminders(
        id TEXT PRIMARY KEY, invoice_id TEXT NOT NULL REFERENCES invoices(id),
        channel TEXT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    db.execute('CREATE INDEX IF NOT EXISTS billing_reminders_invoice ON billing_reminders(invoice_id,created_at)')

    db.execute("""CREATE TABLE IF NOT EXISTS planned_expenses(
        id TEXT PRIMARY KEY, reference TEXT NOT NULL UNIQUE COLLATE NOCASE, currency TEXT NOT NULL,
        amount TEXT NOT NULL, due_date TEXT NOT NULL, category TEXT NOT NULL, description TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'PREVU', expense_id TEXT UNIQUE REFERENCES expenses(id),
        actor TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")

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
        try:
            query=parse_qs(urlsplit(h.path).query)
            page=max(1,min(10000,int(query.get('page',['1'])[0])))
            page_size=int(query.get('page_size',['25'])[0])
            if page_size not in (10,25,50):raise ValueError()
        except ValueError:return h.json_response(400,{'error':'Page invalide.'})
        with connect() as db:
            db.row_factory=sqlite3.Row
            if kind=='planned-expenses':
                items=[dict(r) for r in db.execute("""SELECT p.*,e.reference AS expense_reference
                    FROM planned_expenses p LEFT JOIN expenses e ON e.id=p.expense_id
                    ORDER BY p.due_date,p.id LIMIT ? OFFSET ?""",(page_size,(page-1)*page_size))]
                return h.json_response(200,{'items':items,'total':db.execute('SELECT count(*) FROM planned_expenses').fetchone()[0]})
            if kind=='forecast':
                db.execute('BEGIN')
                today=date.today(); buckets={}
                def bucket(currency):
                    return buckets.setdefault(currency,{k:Decimal(0) for k in ('overdue','receipts_30','receipts_60','receipts_90','planned_30','planned_60','planned_90','recorded_outflows','outflows_overdue','outflows_30','outflows_60','outflows_90')})
                def add(currency,due,value,prefix):
                    b=bucket(currency); days=(date.fromisoformat(due)-today).days
                    if days<0:
                        if prefix=='receipts':b['overdue']+=value
                        return
                    for horizon in (30,60,90):
                        if days<=horizon:b[f'{prefix}_{horizon}']+=value
                for i in db.execute('SELECT i.*,q.currency FROM invoices i JOIN missions m ON m.id=i.mission_id JOIN quotes q ON q.id=m.quote_id'):
                    balance=Decimal(i['amount'])-total(db.execute('SELECT amount FROM payments WHERE invoice_id=?',(i['id'],)))
                    if balance>0:add(i['currency'],i['due_date'],balance,'receipts')
                for s in db.execute("SELECT s.*,q.currency FROM billing_schedule s JOIN missions m ON m.id=s.mission_id JOIN quotes q ON q.id=m.quote_id WHERE s.state='PREVU' AND s.invoice_id IS NULL"):
                    add(s['currency'],s['due_date'],Decimal(s['amount']),'planned')
                for e in db.execute('SELECT currency,amount FROM expenses'):
                    bucket(e['currency'])['recorded_outflows']+=Decimal(e['amount'])
                for e in db.execute("SELECT currency,amount,due_date FROM planned_expenses WHERE state='PREVU'"):
                    b=bucket(e['currency']); value=Decimal(e['amount']); days=(date.fromisoformat(e['due_date'])-today).days
                    if days<0:b['outflows_overdue']+=value
                    for horizon in (30,60,90):
                        if days<=horizon:b[f'outflows_{horizon}']+=value
                for b in buckets.values():
                    for horizon in (30,60,90):
                        b[f'net_{horizon}']=b[f'receipts_{horizon}']-b[f'outflows_{horizon}']
                return h.json_response(200,{'as_of':today.isoformat(),'items':[{'currency':c,**{k:str(v) for k,v in b.items()}} for c,b in sorted(buckets.items())]})
            if kind=='receivables':
                items=[]; aging={}; today=date.today()
                for record in db.execute("""SELECT i.*,q.currency,o.company,m.contract_ref
                    FROM invoices i JOIN missions m ON m.id=i.mission_id JOIN quotes q ON q.id=m.quote_id
                    JOIN opportunities o ON o.id=m.opportunity_id ORDER BY i.due_date,i.id"""):
                    x=dict(record)
                    balance=Decimal(x['amount'])-total(db.execute('SELECT amount FROM payments WHERE invoice_id=?',(x['id'],)))
                    if balance<=0:continue
                    days=max(0,(today-date.fromisoformat(x['due_date'])).days)
                    bucket='current' if days==0 else 'd1_30' if days<=30 else 'd31_60' if days<=60 else 'd61_90' if days<=90 else 'd90_plus'
                    sums=aging.setdefault(x['currency'],{k:Decimal(0) for k in ('current','d1_30','d31_60','d61_90','d90_plus')})
                    sums[bucket]+=balance
                    history=[dict(y) for y in db.execute('SELECT channel,note,created_at FROM billing_reminders WHERE invoice_id=? ORDER BY created_at DESC,rowid DESC LIMIT 10',(x['id'],))]
                    x.update(balance=str(balance),days_overdue=days,bucket=bucket,reminders=history,
                             reminder_count=db.execute('SELECT count(*) FROM billing_reminders WHERE invoice_id=?',(x['id'],)).fetchone()[0])
                    items.append(x)
                return h.json_response(200,{'items':items[(page-1)*page_size:page*page_size],'total':len(items),
                    'aging':{c:{k:str(v) for k,v in sums.items()} for c,sums in aging.items()}})
            if kind=='schedule':
                items=[]
                for record in db.execute("""SELECT s.*,q.currency,q.title,o.company,m.contract_ref,i.reference invoice_reference
                    FROM billing_schedule s JOIN missions m ON m.id=s.mission_id JOIN quotes q ON q.id=m.quote_id
                    JOIN opportunities o ON o.id=m.opportunity_id LEFT JOIN invoices i ON i.id=s.invoice_id
                    ORDER BY s.due_date,s.id LIMIT ? OFFSET ?""",(page_size,(page-1)*page_size)):
                    x=dict(record)
                    x['overdue']=x['state']=='PREVU' and x['due_date']<date.today().isoformat()
                    items.append(x)
                return h.json_response(200,{'items':items,'total':db.execute('SELECT count(*) FROM billing_schedule').fetchone()[0]})
            if kind=='contracts':
                items=[]
                today=date.today().isoformat()
                for record in db.execute("""SELECT q.*, m.id mission_id,m.contract_ref,m.status mission_status,
                    o.company,sc.signed_date FROM missions m JOIN quotes q ON q.id=m.quote_id
                    JOIN opportunities o ON o.id=m.opportunity_id LEFT JOIN signed_contracts sc ON sc.quote_id=q.id
                    ORDER BY m.created_at DESC,m.id LIMIT ? OFFSET ?""",(page_size,(page-1)*page_size)):
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
                rows=[dict(r) for r in db.execute('SELECT j.*,q.currency,q.title AS mission_title FROM milestones j JOIN missions m ON m.id=j.mission_id JOIN quotes q ON q.id=m.quote_id ORDER BY j.id LIMIT ? OFFSET ?',(page_size,(page-1)*page_size))]
                return h.json_response(200,{'items':rows,'total':db.execute('SELECT count(*) FROM milestones').fetchone()[0]})
            query=parse_qs(urlsplit(h.path).query)
            search=query.get('q',[''])[0].strip().casefold()
            state=query.get('state',[''])[0]
            if len(search)>180 or state not in ('','OPEN','OVERDUE','PAID'):
                return h.json_response(400,{'error':'Filtre invalide.'})
            db.execute('BEGIN')
            items=[]; totals={};today=date.today().isoformat()
            for r in db.execute('SELECT i.*,q.currency,q.title FROM invoices i JOIN missions m ON m.id=i.mission_id JOIN quotes q ON q.id=m.quote_id ORDER BY i.created_at DESC,i.id'):
                x=dict(r);paid=total(db.execute('SELECT amount FROM payments WHERE invoice_id=?',(x['id'],)));due=Decimal(x['amount'])-paid
                x.update(paid=str(paid),balance=str(due),overdue=due>0 and x['due_date']<today)
                t=totals.setdefault(x['currency'],{'invoiced':Decimal(0),'paid':Decimal(0),'balance':Decimal(0),'overdue':Decimal(0)})
                t['invoiced']+=Decimal(x['amount']);t['paid']+=paid;t['balance']+=due;t['overdue']+=due if x['overdue'] else 0
                if search and not any(search in x[k].casefold() for k in ('reference','title','currency')):continue
                if state=='OPEN' and due<=0 or state=='OVERDUE' and not x['overdue'] or state=='PAID' and due!=0:continue
                items.append(x)
            return h.json_response(200,{'items':items[(page-1)*page_size:page*page_size],'total':len(items),'totals':{c:{k:str(v) for k,v in t.items()} for c,t in totals.items()}})
    try:
        n=int(h.headers.get('Content-Length','0'))
        if not 0<n<=16000 or h.headers.get_content_type()!='application/json':raise ValueError()
        v=json.loads(h.rfile.read(n))
        if not isinstance(v,dict) or any(not isinstance(x,str) or len(x)>180 or '\x00' in x for x in v.values()):raise ValueError()
        v={k:x.strip() for k,x in v.items()};oid=str(uuid.uuid4())
        with connect() as db:
            db.row_factory=sqlite3.Row;db.execute('BEGIN IMMEDIATE')
            if kind=='planned-expenses' and method=='POST':
                if set(v)!={'reference','currency','amount','due_date','category','description'} or not v['reference'] or not v['description'] or v['currency'] not in ('GNF','XOF','EUR','USD') or v['category'] not in ('CONSULTANT','REMBOURSEMENT','FONCTIONNEMENT','AUTRE') or date.fromisoformat(v['due_date']).isoformat()!=v['due_date'] or v['due_date']<date.today().isoformat():raise ValueError()
                a=amount(v['amount'],v['currency'])
                db.execute('INSERT INTO planned_expenses(id,reference,currency,amount,due_date,category,description,actor) VALUES(?,?,?,?,?,?,?,?)',(oid,v['reference'],v['currency'],str(a),v['due_date'],v['category'],v['description'],h.actor));event='DEPENSE_PLANIFIEE'
            elif kind=='planned-expenses' and method=='PATCH':
                oid=path.rsplit('/',1)[-1]
                p=db.execute("SELECT * FROM planned_expenses WHERE id=? AND state='PREVU'",(oid,)).fetchone()
                if not p:return h.json_response(409,{'error':'Prévision absente ou déjà traitée.'})
                if v=={'state':'ANNULE'}:
                    db.execute("UPDATE planned_expenses SET state='ANNULE' WHERE id=?",(oid,));event='DEPENSE_PREVISION_ANNULEE'
                elif set(v)=={'expense_reference'} and v['expense_reference']:
                    e=db.execute('SELECT * FROM expenses WHERE reference=?',(v['expense_reference'],)).fetchone()
                    if not e or e['currency']!=p['currency'] or Decimal(e['amount'])!=Decimal(p['amount']):return h.json_response(409,{'error':'Décaissement absent, devise ou montant différent.'})
                    db.execute("UPDATE planned_expenses SET state='RAPPROCHE',expense_id=? WHERE id=?",(e['id'],oid));event='DEPENSE_PREVISION_RAPPROCHEE'
                else:raise ValueError()
            elif kind=='reminders' and method=='POST':
                if set(v)!={'invoice_id','channel','note'} or v['channel'] not in ('EMAIL','TELEPHONE','WHATSAPP','AUTRE') or not v['note']:raise ValueError()
                i=db.execute('SELECT * FROM invoices WHERE id=?',(v['invoice_id'],)).fetchone()
                if not i:raise ValueError()
                if i['due_date']>=date.today().isoformat() or total(db.execute('SELECT amount FROM payments WHERE invoice_id=?',(i['id'],)))>=Decimal(i['amount']):
                    return h.json_response(409,{'error':'Seules les créances échues non soldées peuvent être relancées.'})
                db.execute('INSERT INTO billing_reminders(id,invoice_id,channel,note) VALUES(?,?,?,?)',(oid,i['id'],v['channel'],v['note']));event='RELANCE_MANUELLE'
            elif kind=='schedule' and method=='POST':
                if set(v)!={'mission_id','label','kind','amount','due_date'} or not v['label'] or v['kind'] not in ('ACOMPTE','PERIODIQUE','SOLDE') or date.fromisoformat(v['due_date']).isoformat()!=v['due_date']:raise ValueError()
                m=mission(db,v['mission_id'])
                if not m:raise ValueError()
                a=amount(v['amount'],m['currency'])
                used=total(db.execute("SELECT amount FROM billing_schedule WHERE mission_id=? AND state<>'ANNULE'",(v['mission_id'],)))
                if used+a>Decimal(quotes.calculate(m)['revenue']):return h.json_response(409,{'error':'Échéancier supérieur au montant prévisionnel du devis.'})
                if db.execute("SELECT 1 FROM billing_schedule WHERE mission_id=? AND label=? AND due_date=? AND state<>'ANNULE'",(v['mission_id'],v['label'],v['due_date'])).fetchone():return h.json_response(409,{'error':'Échéance déjà planifiée.'})
                db.execute('INSERT INTO billing_schedule(id,mission_id,label,kind,amount,due_date) VALUES(?,?,?,?,?,?)',(oid,v['mission_id'],v['label'],v['kind'],str(a),v['due_date']));event='ECHEANCE_PLANIFIEE'
            elif kind=='schedule' and method=='PATCH':
                oid=path.rsplit('/',1)[-1]
                s=db.execute("SELECT * FROM billing_schedule WHERE id=? AND state='PREVU'",(oid,)).fetchone()
                if not s:return h.json_response(409,{'error':'Échéance absente ou déjà traitée.'})
                if v=={'state':'ANNULE'}:
                    db.execute("UPDATE billing_schedule SET state='ANNULE' WHERE id=?",(oid,));event='ECHEANCE_ANNULEE'
                elif set(v)=={'invoice_reference'} and v['invoice_reference']:
                    i=db.execute('SELECT * FROM invoices WHERE reference=? AND mission_id=?',(v['invoice_reference'],s['mission_id'])).fetchone()
                    if not i or Decimal(i['amount'])!=Decimal(s['amount']):return h.json_response(409,{'error':'Créance absente ou montant différent.'})
                    db.execute("UPDATE billing_schedule SET state='RAPPROCHE',invoice_id=? WHERE id=?",(i['id'],oid));event='ECHEANCE_RAPPROCHEE'
                else:raise ValueError()
            elif method=='PATCH' and kind=='milestones':
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
