"""Internal receivables ledger, not statutory invoicing or accounting."""
import json, re, sqlite3, uuid
from datetime import date
from decimal import Decimal
from urllib.parse import urlsplit, parse_qs
import missions
import quotes
import crm
import accounts

SAAS_COST_CATEGORIES=('INFRASTRUCTURE','SUPPORT','ACQUISITION','EXPLOITATION')

def saas_budget_report(db,report,product='',currency=''):
    products=report['products']
    rows={(r['month'],r['product_id'],r['currency']):dict(r) for r in report['items']}
    targets={}
    for r in db.execute('''SELECT month,product_id,currency,revenue_target,cost_budget
        FROM saas_budget_revisions ORDER BY id'''):
        m,p,c=r[:3]
        if report['start']<=m<=report['end'] and (not product or product==p) and (not currency or currency==c):
            targets[m,p,c]=(Decimal(r[3]),Decimal(r[4]))
    for (m,p,c) in targets:
        rows.setdefault((m,p,c),{'month':m,'product_id':p,'product':products[p],'currency':c,'invoiced_ht':'0','received_ttc':'0','allocated':'0','cash_contribution':'0',**dict.fromkeys(SAAS_COST_CATEGORIES,'0')})
    def compare(r,target):
        revenue,cost=Decimal(r['invoiced_ht']),Decimal(r['allocated'])
        if target is None:return dict(r,revenue_target=None,cost_budget=None,revenue_gap=None,cost_remaining=None,achievement_pct=None,over_budget=False)
        rt,cb=target
        return dict(r,revenue_target=str(rt),cost_budget=str(cb),revenue_gap=str(revenue-rt),cost_remaining=str(cb-cost),
                    achievement_pct=str((revenue*100/rt).quantize(Decimal('0.01'))) if rt else None,over_budget=cost>cb)
    items=[compare(r,targets.get(k)) for k,r in sorted(rows.items())]
    totals={}
    for key,r in rows.items():
        if key not in targets:continue
        _,p,c=key
        t=totals.setdefault((p,c),[Decimal(0)]*4+[0])
        t[0]+=Decimal(r['invoiced_ht']);t[1]+=Decimal(r['allocated']);t[2]+=targets[key][0];t[3]+=targets[key][1];t[4]+=1
    return report|{'items':items,'budget_totals':[compare({'product':products[p],'currency':c,'invoiced_ht':str(t[0]),'allocated':str(t[1]),'months_planned':t[4]},(t[2],t[3])) for (p,c),t in sorted(totals.items())]}

def save_saas_budget(h,connect):
    if h.role not in ('ADMIN','COMPTABLE'):return h.json_response(403,{'error':'Action réservée à la finance.'})
    try:
        n=int(h.headers.get('Content-Length','0'))
        if not 0<n<=4000 or h.headers.get_content_type()!='application/json':raise ValueError()
        v=json.loads(h.rfile.read(n))
        if not isinstance(v,dict) or set(v)!={'month','product_id','currency','revenue_target','cost_budget'} or any(not isinstance(x,str) or len(x)>80 for x in v.values()):raise ValueError()
        if not re.fullmatch(r'[0-9]{4}-[0-9]{2}',v['month']):raise ValueError()
        date.fromisoformat(v['month']+'-01')
        if v['product_id'] not in {p['id'] for p in crm.CATALOGUE} or v['currency'] not in ('EUR','USD','GNF','XOF'):raise ValueError()
        revenue=crm.saas_money(v['revenue_target'],v['currency']);cost=crm.saas_money(v['cost_budget'],v['currency'])
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('INSERT INTO saas_budget_revisions(month,product_id,currency,revenue_target,cost_budget,actor) VALUES(?,?,?,?,?,?)',(v['month'],v['product_id'],v['currency'],str(revenue),str(cost),h.actor))
            accounts.event(db,h.actor,'BUDGET_SAAS_REVISE',str(row.lastrowid))
        return h.json_response(201,{'id':row.lastrowid})
    except (ValueError,TypeError,UnicodeError):return h.json_response(400,{'error':'Budget invalide.'})

def saas_monthly(db,start,end,product='',currency=''):
    """Calendar months, each flow dated by its own source event."""
    months={}
    products={p['id']:p['name'] for p in crm.CATALOGUE}
    def add(day,p,c,key,amount):
        month=day[:7]
        if not start<=month<=end or (product and p!=product) or (currency and c!=currency):return
        values=months.setdefault((month,p,c),dict.fromkeys(('invoiced_ht','received_ttc','allocated',*SAAS_COST_CATEGORIES),Decimal(0)))
        values[key]+=Decimal(amount)
        if key in SAAS_COST_CATEGORIES:values['allocated']+=Decimal(amount)
    join=''' FROM saas_invoice_register i JOIN saas_billing_preparations b
      ON b.subscription_id=i.subscription_id AND b.period_start=i.period_start
      JOIN saas_subscriptions s ON s.id=i.subscription_id JOIN saas_offers f ON f.id=s.offer_id'''
    for day,raw,c,rec,one in db.execute('SELECT i.issued_on,f.inputs,b.currency,b.recurring,b.one_off'+join):
        add(day,json.loads(raw)['product_id'],c,'invoiced_ht',Decimal(rec)+Decimal(one))
    for day,raw,c,amount in db.execute('SELECT r.paid_on,f.inputs,b.currency,r.amount'+join+' JOIN saas_receipts r ON r.invoice_id=i.id'):
        add(day,json.loads(raw)['product_id'],c,'received_ttc',amount)
    for day,p,c,category,amount in db.execute('''SELECT e.paid_date,a.product_id,e.currency,a.category,a.amount
      FROM saas_expense_allocations a JOIN expenses e ON e.id=a.expense_id'''):
        add(day,p,c,category,amount)
    return {'start':start,'end':end,'products':products,'items':[
        {'month':m,'product_id':p,'product':products.get(p,p),'currency':c,
         **{k:str(v) for k,v in g.items()},'cash_contribution':str(g['received_ttc']-g['allocated'])}
        for (m,p,c),g in sorted(months.items())]}

def saas_profitability(db,search='',page=1,page_size=10):
    db.row_factory=sqlite3.Row
    products={p['id']:p['name'] for p in crm.CATALOGUE}
    groups={}; residual={}
    def group(product,currency):
        return groups.setdefault((product,currency),dict.fromkeys(('invoiced_ht','received_ttc','allocated',*SAAS_COST_CATEGORIES),Decimal(0)))
    for r in db.execute('''SELECT i.subscription_id,i.period_start,f.inputs FROM saas_invoice_register i
        JOIN saas_subscriptions s ON s.id=i.subscription_id JOIN saas_offers f ON f.id=s.offer_id'''):
        x=crm.saas_invoice_details(db,r[0],r[1],date.today().isoformat())
        g=group(json.loads(r[2])['product_id'],x['currency'])
        g['invoiced_ht']+=Decimal(x['recurring'])+Decimal(x['one_off'])
        g['received_ttc']+=Decimal(x['paid'])
    for r in db.execute("SELECT currency,amount FROM expenses WHERE mission_id=''"):
        residual[r[0]]=residual.get(r[0],Decimal(0))+Decimal(r[1])
    for r in db.execute('''SELECT a.product_id,a.category,a.amount,e.currency FROM saas_expense_allocations a
        JOIN expenses e ON e.id=a.expense_id'''):
        n=Decimal(r[2]);g=group(r[0],r[3]);g['allocated']+=n;g[r[1]]+=n
        residual[r[3]]-=n
    rows,count=searched_page(db,'''SELECT a.*,e.reference,e.currency,e.paid_date FROM saas_expense_allocations a
        JOIN expenses e ON e.id=a.expense_id''',('reference','product_id','category','currency'),'created_at DESC,id',search,page,page_size)
    return {'products':products,'categories':SAAS_COST_CATEGORIES,'groups':[
        {'product_id':p,'product':products.get(p,p),'currency':c,**{k:str(v) for k,v in g.items()},
         'cash_contribution':str(g['received_ttc']-g['allocated'])} for (p,c),g in sorted(groups.items())],
        'unallocated':{c:str(v) for c,v in sorted(residual.items())},'items':[dict(r) for r in rows],'total':count}

def allocate_saas_cost(h,connect):
    if h.role not in ('ADMIN','COMPTABLE'):return h.json_response(403,{'error':'Action réservée à la finance.'})
    try:
        n=int(h.headers.get('Content-Length','0'))
        if not 0<n<=4000 or h.headers.get_content_type()!='application/json':raise ValueError()
        v=json.loads(h.rfile.read(n))
        if not isinstance(v,dict) or set(v)!={'reference','product_id','category','amount'} or any(not isinstance(x,str) or len(x)>180 or '\x00' in x for x in v.values()):raise ValueError()
        if v['product_id'] not in {p['id'] for p in crm.CATALOGUE} or v['category'] not in SAAS_COST_CATEGORIES:raise ValueError()
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            e=db.execute('SELECT id,currency,amount,mission_id FROM expenses WHERE reference=? COLLATE NOCASE',(v['reference'].strip(),)).fetchone()
            if not e:return h.json_response(404,{'error':'Décaissement introuvable.'})
            if e[3]:return h.json_response(409,{'error':'Décaissement déjà affecté à une mission.'})
            a=crm.saas_money(v['amount'],e[1])
            if a<=0:raise ValueError()
            used=sum((Decimal(r[0]) for r in db.execute('SELECT amount FROM saas_expense_allocations WHERE expense_id=?',(e[0],))),Decimal(0))
            if used+a>Decimal(e[2]):return h.json_response(409,{'error':'Montant supérieur au solde disponible.'})
            identifier=str(uuid.uuid4())
            db.execute('INSERT INTO saas_expense_allocations(id,expense_id,product_id,category,amount,actor) VALUES(?,?,?,?,?,?)',(identifier,e[0],v['product_id'],v['category'],str(a),h.actor))
            accounts.event(db,h.actor,'COUT_SAAS_AFFECTE',identifier)
        return h.json_response(201,{'id':identifier})
    except (ValueError,TypeError,UnicodeError):return h.json_response(400,{'error':'Données invalides.'})
    except sqlite3.IntegrityError:return h.json_response(409,{'error':'Affectation déjà enregistrée.'})

def saas_receivables(db,today,search,state,page,page_size):
    db.row_factory=sqlite3.Row
    totals={};items=[];clients={}
    source=db.execute('''SELECT i.subscription_id,i.period_start,o.company,f.estimate
      FROM saas_invoice_register i JOIN saas_subscriptions s ON s.id=i.subscription_id
      JOIN saas_offers f ON f.id=s.offer_id JOIN opportunities o ON o.id=f.opportunity_id
      ORDER BY i.due_on,i.id''').fetchall()
    for entry in source:
        invoice=crm.saas_invoice_details(db,entry['subscription_id'],entry['period_start'],today.isoformat())
        product=json.loads(entry['estimate'])['product_name']
        invoice.update(company=entry['company'],product=product)
        days=max(0,(today-date.fromisoformat(invoice['due_on'])).days)
        invoice['days_overdue']=days if Decimal(invoice['balance'])>0 else 0
        currency=invoice['currency'];balance=Decimal(invoice['balance'])
        bucket='current' if days==0 else 'd30' if days<=30 else 'd60' if days<=60 else 'd90' if days<=90 else 'older'
        group=totals.setdefault(currency,dict.fromkeys(('invoiced','paid','balance','overdue','current','d30','d60','d90','older','receipts_30','receipts_60','receipts_90'),Decimal(0)))
        for key,field in (('invoiced','total'),('paid','paid'),('balance','balance')):group[key]+=Decimal(invoice[field])
        group[bucket]+=balance
        if days:group['overdue']+=balance
        else:
            remaining=(date.fromisoformat(invoice['due_on'])-today).days
            for horizon in (30,60,90):
                if remaining<=horizon:group[f'receipts_{horizon}']+=balance
        invoice['reminders']=[dict(r) for r in db.execute('SELECT channel,note,actor,created_at FROM saas_collection_reminders WHERE invoice_id=? ORDER BY created_at DESC,id DESC LIMIT 10',(invoice['id'],))]
        # The company is a display label, not a legal customer identifier.
        client=clients.setdefault((invoice['company'],currency),{'company':invoice['company'],'currency':currency,'balance':Decimal(0),'overdue':Decimal(0)})
        client['balance']+=balance
        if days:client['overdue']+=balance
        if (not state or invoice['status']==state) and matches_search(search,invoice,('company','product','reference','currency')):items.append(invoice)
    return {'items':items[(page-1)*page_size:page*page_size],'total':len(items),'as_of':today.isoformat(),
            'totals':{c:{k:str(v) for k,v in g.items()} for c,g in totals.items()},
            'clients':[dict(g,balance=str(g['balance']),overdue=str(g['overdue'])) for _,g in sorted(clients.items()) if g['balance']>0]}

def matches_search(search, record, fields):
    return not search or any(search in str(record[k] or '').casefold() for k in fields)


def searched_page(db, select, fields, order, search, page, page_size):
    # SQL fragments are fixed by callers; user input is always a bound parameter.
    db.create_function('dsig_match', -1, lambda *values: int(any(
        values[0] in str(value or '').casefold() for value in values[1:])), deterministic=True)
    source = ' FROM (' + select + ') AS ledger'
    where = ' WHERE dsig_match(?, ' + ', '.join(fields) + ')' if search else ''
    args = (search,) if search else ()
    count = db.execute('SELECT count(*)' + source + where, args).fetchone()[0]
    rows = db.execute('SELECT *' + source + where + ' ORDER BY ' + order + ' LIMIT ? OFFSET ?',
                      (*args, page_size, (page-1)*page_size))
    return rows, count


def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS saas_budget_revisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, month TEXT NOT NULL, product_id TEXT NOT NULL,
        currency TEXT NOT NULL, revenue_target TEXT NOT NULL, cost_budget TEXT NOT NULL,
        actor TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    db.execute('''CREATE TABLE IF NOT EXISTS saas_expense_allocations (
      id TEXT PRIMARY KEY, expense_id TEXT NOT NULL REFERENCES expenses(id),
      product_id TEXT NOT NULL, category TEXT NOT NULL, amount TEXT NOT NULL,
      actor TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(expense_id,product_id,category))''')
    db.execute('''CREATE TABLE IF NOT EXISTS saas_collection_reminders (
      id TEXT PRIMARY KEY, invoice_id INTEGER NOT NULL REFERENCES saas_invoice_register(id),
      channel TEXT NOT NULL, note TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    db.execute('CREATE INDEX IF NOT EXISTS saas_collection_reminders_invoice ON saas_collection_reminders(invoice_id)')
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
    if method=='POST' and kind=='saas-profitability':return allocate_saas_cost(h,connect)
    if method=='POST' and kind=='saas-budget':return save_saas_budget(h,connect)
    action=re.fullmatch(r'/api/admin/billing/saas-receivables/([0-9]{1,18})/(receipt|reminder)',path)
    if method=='POST' and action:
        if h.role not in ('ADMIN','COMPTABLE'):return h.json_response(403,{'error':'Action réservée à la finance.'})
        try:
            length=int(h.headers.get('Content-Length','0'))
            if not 0<length<=4000 or h.headers.get_content_type()!='application/json':raise ValueError()
            data=json.loads(h.rfile.read(length))
            if not isinstance(data,dict):raise ValueError()
            if action[2]=='receipt' and set(data)!={'reference','paid_on','amount'}:raise ValueError()
            if action[2]=='reminder' and (set(data)!={'channel','note'} or data['channel'] not in ('EMAIL','TELEPHONE','AUTRE') or not isinstance(data['note'],str) or not data['note'].strip() or len(data['note'])>1000 or '\x00' in data['note']):raise ValueError()
        except (ValueError,TypeError,UnicodeError):return h.json_response(400,{'error':'Données invalides.'})
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            invoice=db.execute('SELECT subscription_id,period_start FROM saas_invoice_register WHERE id=?',(int(action[1]),)).fetchone()
            if not invoice:return h.json_response(404,{'error':'Facture introuvable.'})
            if action[2]=='receipt':return crm.saas_register_invoice(h,db,invoice[0],data|{'action':'receipt','period_start':invoice[1]})
            details=crm.saas_invoice_details(db,invoice[0],invoice[1],date.today().isoformat())
            if Decimal(details['balance'])<=0:return h.json_response(409,{'error':'Facture soldée.'})
            db.execute('INSERT INTO saas_collection_reminders(id,invoice_id,channel,note,actor) VALUES(?,?,?,?,?)',(str(uuid.uuid4()),int(action[1]),data['channel'],data['note'].strip(),h.actor))
            accounts.event(db,h.actor,'RELANCE_SAAS_DOCUMENTEE',str(action[1]))
        return h.json_response(201,{'status':'ENREGISTREE','sent':False})
    if method=='GET':
        try:
            query=parse_qs(urlsplit(h.path).query)
            page=max(1,min(10000,int(query.get('page',['1'])[0])))
            page_size=int(query.get('page_size',['25'])[0])
            if page_size not in (10,25,50):raise ValueError()
        except ValueError:return h.json_response(400,{'error':'Page invalide.'})
        search=query.get('q',[''])[0].strip().casefold()
        if len(search)>180:return h.json_response(400,{'error':'Filtre invalide.'})
        with connect() as db:
            db.row_factory=sqlite3.Row
            if kind=='saas-profitability':
                db.execute('BEGIN')
                return h.json_response(200,saas_profitability(db,search,page,page_size)|{'can_allocate':h.role in ('ADMIN','COMPTABLE')})
            if kind=='saas-monthly':
                start=query.get('start',[str(date.today().year)+'-01'])[0]
                end=query.get('end',[date.today().isoformat()[:7]])[0]
                product=query.get('product',[''])[0];currency=query.get('currency',[''])[0]
                try:
                    if not all(re.fullmatch(r'[0-9]{4}-[0-9]{2}',v) for v in (start,end)):raise ValueError()
                    a,b=(date.fromisoformat(v+'-01') for v in (start,end))
                    if not 0<=(b.year-a.year)*12+b.month-a.month<24:raise ValueError()
                    if product and product not in {p['id'] for p in crm.CATALOGUE}:raise ValueError()
                    if currency not in ('','EUR','USD','GNF','XOF'):raise ValueError()
                except ValueError:return h.json_response(400,{'error':'Période ou filtre invalide (24 mois maximum).'})
                db.execute('BEGIN')
                report=saas_monthly(db,start,end,product,currency)
                return h.json_response(200,saas_budget_report(db,report,product,currency)|{'can_budget':h.role in ('ADMIN','COMPTABLE')})
            if kind=='saas-receivables':
                state=query.get('state',[''])[0]
                if state not in ('','OUVERTE','PARTIELLE','REGLEE','EN_RETARD'):return h.json_response(400,{'error':'État invalide.'})
                db.execute('BEGIN')
                return h.json_response(200,saas_receivables(db,date.today(),search,state,page,page_size)|{'can_collect':h.role in ('ADMIN','COMPTABLE')})
            if kind=='planned-expenses':
                rows,count=searched_page(db,"""SELECT p.*,e.reference AS expense_reference
                    FROM planned_expenses p LEFT JOIN expenses e ON e.id=p.expense_id""",
                    ('reference','currency','amount','due_date','category','description','state','expense_reference'),
                    'due_date,id',search,page,page_size)
                return h.json_response(200,{'items':[dict(r) for r in rows],'total':count})
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
                    if not matches_search(search,x,('company','reference','contract_ref','currency','due_date','amount')):continue
                    history=[dict(y) for y in db.execute('SELECT channel,note,created_at FROM billing_reminders WHERE invoice_id=? ORDER BY created_at DESC,rowid DESC LIMIT 10',(x['id'],))]
                    x.update(balance=str(balance),days_overdue=days,bucket=bucket,reminders=history,
                             reminder_count=db.execute('SELECT count(*) FROM billing_reminders WHERE invoice_id=?',(x['id'],)).fetchone()[0])
                    items.append(x)
                return h.json_response(200,{'items':items[(page-1)*page_size:page*page_size],'total':len(items),
                    'aging':{c:{k:str(v) for k,v in sums.items()} for c,sums in aging.items()}})
            if kind=='schedule':
                items=[]
                rows,count=searched_page(db,"""SELECT s.*,q.currency,q.title,o.company,m.contract_ref,i.reference invoice_reference
                    FROM billing_schedule s JOIN missions m ON m.id=s.mission_id JOIN quotes q ON q.id=m.quote_id
                    JOIN opportunities o ON o.id=m.opportunity_id LEFT JOIN invoices i ON i.id=s.invoice_id""",
                    ('company','contract_ref','title','label','kind','amount','currency','due_date','state','invoice_reference'),
                    'due_date,id',search,page,page_size)
                for record in rows:
                    x=dict(record)
                    x['overdue']=x['state']=='PREVU' and x['due_date']<date.today().isoformat()
                    items.append(x)
                return h.json_response(200,{'items':items,'total':count})
            if kind=='contracts':
                items=[]
                today=date.today().isoformat()
                rows,count=searched_page(db,"""SELECT q.*, m.id mission_id,m.contract_ref,m.status mission_status,
                    o.company,sc.signed_date,m.created_at AS mission_created_at FROM missions m JOIN quotes q ON q.id=m.quote_id
                    JOIN opportunities o ON o.id=m.opportunity_id LEFT JOIN signed_contracts sc ON sc.quote_id=q.id""",
                    ('company','contract_ref','title','currency','mission_status'),
                    'mission_created_at DESC,mission_id',search,page,page_size)
                for record in rows:
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
                return h.json_response(200,{'items':items,'total':count})
            if kind=='milestones':
                rows,count=searched_page(db,'SELECT j.*,q.currency,q.title AS mission_title FROM milestones j JOIN missions m ON m.id=j.mission_id JOIN quotes q ON q.id=m.quote_id',
                    ('title','mission_title','currency','amount','status'),'id',search,page,page_size)
                return h.json_response(200,{'items':[dict(r) for r in rows],'total':count})
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
