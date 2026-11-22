"""Local CRM: opportunities, clients and linked consultant profiles."""
import json
import re
import sqlite3
import uuid
import calendar
import accounts
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, timedelta
from urllib.parse import parse_qs, urlsplit

STATUSES=("PROSPECT","QUALIFIE","PROPOSITION","NEGOCIATION","GAGNE","EN_MISSION","TERMINE","PERDU")
FIELDS={"company":180,"contact":120,"email":254,"title":180,"mode":20,"skills":1000,
        "consultant_id":36,"next_action":500,"followup":10,"notes":2000,"status":30}

CRITERIA = ('need', 'budget', 'decision_maker', 'timeline')
QUALIFICATION_DEFAULT = dict.fromkeys(CRITERIA, 'UNKNOWN') | {'demo_status': 'NONE', 'demo_date': ''}

def validate_qualification(values):
    if not isinstance(values, dict) or set(values) != set(QUALIFICATION_DEFAULT):
        raise ValueError()
    if any(values[k] not in ('UNKNOWN', 'NO', 'YES') for k in CRITERIA):
        raise ValueError()
    if values['demo_status'] not in ('NONE', 'REQUESTED', 'SCHEDULED', 'DONE', 'CANCELLED'):
        raise ValueError()
    day = values['demo_date']
    if not isinstance(day, str) or (day and date.fromisoformat(day).isoformat() != day):
        raise ValueError()
    if (values['demo_status'] in ('SCHEDULED', 'DONE') and not day) or (values['demo_status'] == 'NONE' and day):
        raise ValueError()
    return values

# Catalogue interne : périmètres documentés, sans promesse de disponibilité commerciale.
CATALOGUE = [
    {
        "id": "guinee-logistique",
        "name": "Guinée Logistique",
        "sector": "Transport & Supply Chain",
        "status": "Prototype de démonstration",
        "scope": "Fret maritime, aérien et terrestre, expéditions, entrepôt, douanes, tarification et suivi.",
        "conditions": "Données fictives uniquement. Authentification, persistance métier et permissions serveur à industrialiser avant pilote."
    },
    {
        "id": "minefleet360",
        "name": "MineFleet360",
        "sector": "Mines & flotte",
        "status": "Développement actif",
        "scope": "Gestion des flottes minières, maintenance, carburant et géolocalisation.",
        "conditions": "Pilote conditionné aux essais terrain, sécurité, sauvegardes et validation du déploiement."
    },
    {
        "id": "gestion-scolaire-pro",
        "name": "Gestion Scolaire Pro",
        "sector": "Éducation",
        "status": "Disponibilité commerciale à qualifier",
        "scope": "Gestion scolaire multi-établissements et multi-tenant.",
        "conditions": "Validation métier et déploiement à confirmer avant engagement client."
    },
    {
        "id": "makitiplus",
        "name": "MakitiPlus",
        "sector": "Commerce",
        "status": "Disponibilité commerciale à qualifier",
        "scope": "Caisse POS, stocks, clients, fournisseurs et fonctionnement hors ligne.",
        "conditions": "Validation des parcours caisse, synchronisation et paiements avant engagement."
    },
    {
        "id": "kora-finance",
        "name": "Kora Finance",
        "sector": "Finance",
        "status": "Disponibilité commerciale à qualifier",
        "scope": "Comptabilité SYSCOHADA, rapprochements et reporting financier.",
        "conditions": "Validation comptable, sécurité et exploitation à confirmer."
    }
]

def simulate_saas(data):
    """Indicative HT scenario; no subscription, contract or accounting write."""
    fields = {'product_id','currency','cycle','quantity','unit_price','options','setup','training'}
    if not isinstance(data,dict) or set(data)!=fields:
        raise ValueError()
    product = next((p for p in CATALOGUE if p['id']==data['product_id']),None)
    if not product or data['currency'] not in ('GNF','XOF','EUR','USD') or data['cycle'] not in ('MONTHLY','ANNUAL'):
        raise ValueError()
    quantity=data['quantity']
    if type(quantity) is not int or not 1<=quantity<=100000:
        raise ValueError()
    unit=Decimal('1' if data['currency'] in ('GNF','XOF') else '0.01')
    amounts={}
    for key in ('unit_price','options','setup','training'):
        raw=data[key]
        if not isinstance(raw,str) or not re.fullmatch(r'\d{1,12}(?:\.\d{1,2})?',raw):raise ValueError()
        value=Decimal(raw)
        if value!=value.quantize(unit):raise ValueError()
        amounts[key]=value
    if amounts['unit_price']<=0:raise ValueError()
    recurring=quantity*amounts['unit_price']+amounts['options']
    annual=recurring*(12 if data['cycle']=='MONTHLY' else 1)
    one_off=amounts['setup']+amounts['training']
    money=lambda x:str(x.quantize(unit,rounding=ROUND_HALF_UP))
    return {'product_id':product['id'],'product_name':product['name'],'currency':data['currency'],'cycle':data['cycle'],
            'recurring':money(recurring),'mrr':money(annual/12),'arr':money(annual),
            'one_off':money(one_off),'first_year':money(annual+one_off),'simulation_only':True}

def schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS opportunities (
      id TEXT PRIMARY KEY, company TEXT NOT NULL, contact TEXT NOT NULL,
      email TEXT NOT NULL, title TEXT NOT NULL, mode TEXT NOT NULL, skills TEXT NOT NULL,
      consultant_id TEXT NOT NULL, next_action TEXT NOT NULL, followup TEXT NOT NULL,
      notes TEXT NOT NULL, status TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    db.execute("""CREATE TABLE IF NOT EXISTS opportunity_events (
      id INTEGER PRIMARY KEY, opportunity_id TEXT NOT NULL, status TEXT NOT NULL,
      version INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    db.execute("""CREATE TABLE IF NOT EXISTS opportunity_qualification (
      opportunity_id TEXT PRIMARY KEY REFERENCES opportunities(id), payload TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS saas_offers (
      id TEXT PRIMARY KEY, opportunity_id TEXT NOT NULL REFERENCES opportunities(id),
      title TEXT NOT NULL, valid_until TEXT NOT NULL, inputs TEXT NOT NULL,
      estimate TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    db.execute('CREATE INDEX IF NOT EXISTS saas_offers_opportunity ON saas_offers(opportunity_id)')
    db.execute('''CREATE TABLE IF NOT EXISTS saas_offer_events (
      offer_id TEXT NOT NULL REFERENCES saas_offers(id), version INTEGER NOT NULL,
      status TEXT NOT NULL, actor TEXT NOT NULL, evidence TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(offer_id,version))''')
    db.execute('''CREATE TABLE IF NOT EXISTS saas_subscriptions (
      id TEXT PRIMARY KEY, offer_id TEXT NOT NULL UNIQUE REFERENCES saas_offers(id),
      starts_on TEXT NOT NULL, ends_on TEXT NOT NULL, reference TEXT NOT NULL,
      actor TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    db.execute('''CREATE TABLE IF NOT EXISTS saas_subscription_renewals (
      predecessor_id TEXT PRIMARY KEY REFERENCES saas_subscriptions(id),
      successor_id TEXT NOT NULL UNIQUE REFERENCES saas_subscriptions(id))''')
    db.execute('''CREATE TABLE IF NOT EXISTS saas_subscription_events (
      subscription_id TEXT NOT NULL REFERENCES saas_subscriptions(id), version INTEGER NOT NULL,
      action TEXT NOT NULL, evidence TEXT NOT NULL, actor TEXT NOT NULL,
      effective_on TEXT NOT NULL, previous_end TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(subscription_id,version))''')
    db.execute('''CREATE TABLE IF NOT EXISTS saas_renewal_contacts (
      subscription_id TEXT NOT NULL REFERENCES saas_subscriptions(id), milestone INTEGER NOT NULL,
      note TEXT NOT NULL, actor TEXT NOT NULL, contacted_on TEXT NOT NULL,
      PRIMARY KEY(subscription_id,milestone))''')
    db.execute('''CREATE TABLE IF NOT EXISTS customer_tickets (
      id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id),
      title TEXT NOT NULL, priority TEXT NOT NULL, due_on TEXT NOT NULL, status TEXT NOT NULL,
      opened_on TEXT NOT NULL, closed_on TEXT, resolution TEXT NOT NULL DEFAULT '',
      csat INTEGER, nps INTEGER, feedback_note TEXT NOT NULL DEFAULT '',
      actor TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1)''')
    db.execute('CREATE INDEX IF NOT EXISTS customer_tickets_org ON customer_tickets(organization_id,status,due_on)')
    db.execute('''CREATE TABLE IF NOT EXISTS customer_actions (
      id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id),
      kind TEXT NOT NULL, title TEXT NOT NULL, due_on TEXT NOT NULL, actor TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'OUVERTE', version INTEGER NOT NULL DEFAULT 1,
      outcome TEXT NOT NULL DEFAULT '', closed_on TEXT)''')
    db.execute('''CREATE TABLE IF NOT EXISTS customer_surveys (
      id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id),
      reference TEXT NOT NULL, captured_on TEXT NOT NULL, csat INTEGER, nps INTEGER,
      actor TEXT NOT NULL, UNIQUE(organization_id,reference))''')
    db.execute('''CREATE TABLE IF NOT EXISTS partner_agreements (
      id TEXT PRIMARY KEY, partner_id TEXT NOT NULL REFERENCES organizations(id),
      reference TEXT NOT NULL COLLATE NOCASE, kind TEXT NOT NULL, starts_on TEXT NOT NULL,
      ends_on TEXT NOT NULL, rate TEXT NOT NULL, actor TEXT NOT NULL,
      UNIQUE(partner_id,reference))''')
    db.execute('''CREATE TABLE IF NOT EXISTS partner_referrals (
      opportunity_id TEXT PRIMARY KEY REFERENCES opportunities(id),
      agreement_id TEXT NOT NULL REFERENCES partner_agreements(id),
      currency TEXT NOT NULL, basis TEXT NOT NULL, commission TEXT NOT NULL,
      actor TEXT NOT NULL, created_on TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS partner_commission_approvals (
      opportunity_id TEXT PRIMARY KEY REFERENCES partner_referrals(opportunity_id),
      amount TEXT NOT NULL, reference TEXT NOT NULL, approved_on TEXT NOT NULL, actor TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS partner_commission_payments (
      id TEXT PRIMARY KEY, opportunity_id TEXT NOT NULL REFERENCES partner_commission_approvals(opportunity_id),
      reference TEXT NOT NULL UNIQUE COLLATE NOCASE, amount TEXT NOT NULL, paid_on TEXT NOT NULL, actor TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS saas_billing_preparations (
      subscription_id TEXT NOT NULL REFERENCES saas_subscriptions(id), period_start TEXT NOT NULL,
      period_end TEXT NOT NULL, currency TEXT NOT NULL, recurring TEXT NOT NULL, one_off TEXT NOT NULL,
      actor TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY(subscription_id,period_start))''')
    db.execute('''CREATE TABLE IF NOT EXISTS saas_invoice_register (
      id INTEGER PRIMARY KEY AUTOINCREMENT, subscription_id TEXT NOT NULL, period_start TEXT NOT NULL,
      reference TEXT NOT NULL UNIQUE COLLATE NOCASE, issued_on TEXT NOT NULL, due_on TEXT NOT NULL,
      tax TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(subscription_id,period_start), FOREIGN KEY(subscription_id,period_start)
      REFERENCES saas_billing_preparations(subscription_id,period_start))''')
    db.execute('''CREATE TABLE IF NOT EXISTS saas_receipts (
      id TEXT PRIMARY KEY, invoice_id INTEGER NOT NULL REFERENCES saas_invoice_register(id),
      reference TEXT NOT NULL UNIQUE COLLATE NOCASE, amount TEXT NOT NULL, paid_on TEXT NOT NULL,
      actor TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')

def saas_invoice_details(db,subscription_id,period_start,today):
    db.row_factory=sqlite3.Row
    row=db.execute('''SELECT i.*,p.currency,p.recurring,p.one_off FROM saas_invoice_register i
      JOIN saas_billing_preparations p ON p.subscription_id=i.subscription_id AND p.period_start=i.period_start
      WHERE i.subscription_id=? AND i.period_start=?''',(subscription_id,period_start)).fetchone()
    if not row:return None
    result=dict(row)
    receipts=[dict(r) for r in db.execute('SELECT reference,amount,paid_on FROM saas_receipts WHERE invoice_id=? ORDER BY paid_on,id',(row['id'],))]
    total=Decimal(row['recurring'])+Decimal(row['one_off'])+Decimal(row['tax'])
    paid=sum((Decimal(r['amount']) for r in receipts),Decimal(0))
    balance=total-paid
    result.update(total=str(total),paid=str(paid),balance=str(balance),receipts=receipts,
                  status='REGLEE' if balance==0 else 'EN_RETARD' if row['due_on']<today else 'PARTIELLE' if paid else 'OUVERTE')
    return result

def saas_money(value,currency):
    if not isinstance(value,str) or not re.fullmatch(r'\d{1,18}(?:\.\d{1,2})?',value):raise ValueError()
    amount=Decimal(value)
    unit=Decimal('1' if currency in ('GNF','XOF') else '0.01')
    if amount!=amount.quantize(unit):raise ValueError()
    return amount.quantize(unit)

def saas_register_invoice(h,db,identifier,data):
    action=data.get('action');period=data.get('period_start')
    try:
        if not isinstance(period,str) or date.fromisoformat(period).isoformat()!=period:raise ValueError()
        keys={'action','period_start','reference','issued_on','due_on','tax'} if action=='invoice' else {'action','period_start','reference','paid_on','amount'} if action=='receipt' else set()
        if set(data)!=keys:raise ValueError()
        reference=data['reference']
        if not isinstance(reference,str) or not reference.strip() or len(reference)>120 or any(ord(c)<32 for c in reference):raise ValueError()
        reference=reference.strip()
        fields=('issued_on','due_on') if action=='invoice' else ('paid_on',)
        if any(not isinstance(data[k],str) or date.fromisoformat(data[k]).isoformat()!=data[k] for k in fields):raise ValueError()
        today=date.today().isoformat()
        if action=='invoice' and (data['issued_on']>today or data['due_on']<data['issued_on']):raise ValueError()
        if action=='receipt' and data['paid_on']>today:raise ValueError()
    except (ValueError,TypeError):return h.json_response(400,{'error':'Référence ou dates invalides.'})
    preparation=db.execute('SELECT currency FROM saas_billing_preparations WHERE subscription_id=? AND period_start=?',(identifier,period)).fetchone()
    if not preparation:return h.json_response(409,{'error':'Échéance non préparée.'})
    invoice=saas_invoice_details(db,identifier,period,today)
    try:
        if action=='invoice':
            tax=saas_money(data['tax'],preparation[0])
            if invoice or db.execute('SELECT 1 FROM saas_invoice_register WHERE reference=? COLLATE NOCASE',(reference,)).fetchone():return h.json_response(409,{'error':'Facture ou référence déjà enregistrée.'})
            db.execute('INSERT INTO saas_invoice_register(subscription_id,period_start,reference,issued_on,due_on,tax,actor) VALUES(?,?,?,?,?,?,?)',(identifier,period,reference,data['issued_on'],data['due_on'],str(tax),h.actor))
        else:
            amount=saas_money(data['amount'],preparation[0])
            if not invoice or data['paid_on']<invoice['issued_on'] or amount<=0 or amount>Decimal(invoice['balance']):return h.json_response(409,{'error':'Facture absente, date ou montant incompatible avec le solde.'})
            if db.execute('SELECT 1 FROM saas_receipts WHERE reference=? COLLATE NOCASE',(reference,)).fetchone():return h.json_response(409,{'error':'Référence de règlement déjà enregistrée.'})
            db.execute('INSERT INTO saas_receipts(id,invoice_id,reference,amount,paid_on,actor) VALUES(?,?,?,?,?,?)',(str(uuid.uuid4()),invoice['id'],reference,str(amount),data['paid_on'],h.actor))
    except ValueError:return h.json_response(400,{'error':'Montant invalide pour cette devise.'})
    accounts.event(db,h.actor,'FACTURE_SAAS_RAPPROCHEE' if action=='invoice' else 'REGLEMENT_SAAS_ENREGISTRE',identifier)
    return h.json_response(201,saas_invoice_details(db,identifier,period,today))

def billing_boundary(anchor,months):
    year,month=divmod(anchor.year*12+anchor.month-1+months,12)
    return date(year,month+1,min(anchor.day,calendar.monthrange(year,month+1)[1]))

def subscription_schedule(start,end,estimate):
    anchor=date.fromisoformat(start);finish=date.fromisoformat(end)
    step=1 if estimate['cycle']=='MONTHLY' else 12
    months=(finish.year-anchor.year)*12+finish.month-anchor.month
    count=(months+step-1)//step
    if count<1 or count>120 or count*step!=months or billing_boundary(anchor,count*step)!=finish:
        return None
    return [{'period_start':billing_boundary(anchor,i*step).isoformat(),
             'period_end':billing_boundary(anchor,(i+1)*step).isoformat(),
             'currency':estimate['currency'],'recurring':estimate['recurring'],
             'one_off':estimate['one_off'] if i==0 else '0'} for i in range(count)]

def saas_billing(h,connect,method,identifier):
    if method=='POST' and h.role!='ADMIN':return h.json_response(403,{'error':'Préparation réservée à un administrateur.'})
    try:
        if method=='GET':
            page=int(parse_qs(urlsplit(h.path).query).get('page',['1'])[0])
            if not 1<=page<=12:raise ValueError()
        else:
            length=int(h.headers.get('Content-Length','0'))
            if not 0<length<=1000 or h.headers.get_content_type()!='application/json':raise ValueError()
            data=json.loads(h.rfile.read(length))
            if not isinstance(data,dict) or ('action' not in data and (set(data)!={'period_start'} or not isinstance(data['period_start'],str) or date.fromisoformat(data['period_start']).isoformat()!=data['period_start'])):raise ValueError()
    except (ValueError,TypeError,UnicodeError):return h.json_response(400,{'error':'Période ou page invalide.'})
    with connect() as db:
        db.execute('BEGIN IMMEDIATE' if method=='POST' else 'BEGIN')
        row=db.execute('SELECT s.starts_on,s.ends_on,f.estimate FROM saas_subscriptions s JOIN saas_offers f ON f.id=s.offer_id WHERE s.id=?',(identifier,)).fetchone()
        if not row:return h.json_response(404,{'error':'Abonnement introuvable.'})
        if method=='POST' and 'action' in data:return saas_register_invoice(h,db,identifier,data)
        schedule=subscription_schedule(row[0],row[1],json.loads(row[2]))
        if schedule is None:return h.json_response(409,{'error':'Durée non alignée sur le cycle ou supérieure à 120 périodes : échéancier à convenir manuellement.'})
        if method=='GET':
            prepared={r[0] for r in db.execute('SELECT period_start FROM saas_billing_preparations WHERE subscription_id=?',(identifier,))}
            for item in schedule:
                item['prepared']=item['period_start'] in prepared
                item['total_ht']=str(Decimal(item['recurring'])+Decimal(item['one_off']))
                item['invoice']=saas_invoice_details(db,identifier,item['period_start'],date.today().isoformat())
            return h.json_response(200,{'items':schedule[(page-1)*10:page*10],'total':len(schedule),'page':page,'can_prepare':h.role=='ADMIN','prepared_count':len(prepared)})
        item=next((p for p in schedule if p['period_start']==data['period_start']),None)
        if not item:return h.json_response(400,{'error':'Période hors échéancier.'})
        if db.execute('SELECT 1 FROM saas_billing_preparations WHERE subscription_id=? AND period_start=?',(identifier,item['period_start'])).fetchone():return h.json_response(409,{'error':'Période déjà préparée.'})
        db.execute('INSERT INTO saas_billing_preparations(subscription_id,period_start,period_end,currency,recurring,one_off,actor) VALUES(?,?,?,?,?,?,?)',(identifier,item['period_start'],item['period_end'],item['currency'],item['recurring'],item['one_off'],h.actor))
        accounts.event(db,h.actor,'ECHEANCE_SAAS_PREPAREE',identifier)
    return h.json_response(201,{'subscription_id':identifier,'period_start':item['period_start'],'status':'PREPAREE'})

def subscription_status(start,end,today):
    return 'PLANIFIE' if today<start else 'EXPIRE' if today>=end else 'ACTIF'

def subscription_metrics(db,today):
    counts=dict.fromkeys(('PLANIFIE','ACTIF','EXPIRE','ECHEANCE_30J'),0)
    groups={}
    limit=(date.fromisoformat(today)+timedelta(days=30)).isoformat()
    for start,end,raw in db.execute('SELECT s.starts_on,s.ends_on,f.estimate FROM saas_subscriptions s JOIN saas_offers f ON f.id=s.offer_id'):
        status=subscription_status(start,end,today)
        counts[status]+=1
        if status!='ACTIF':continue
        if end<=limit:counts['ECHEANCE_30J']+=1
        estimate=json.loads(raw)
        key=(estimate['product_id'],estimate['currency'])
        group=groups.setdefault(key,{'product_id':key[0],'product_name':estimate['product_name'],'currency':key[1],'active':0,'mrr':Decimal(0),'arr':Decimal(0)})
        group['active']+=1
        group['mrr']+=Decimal(estimate['mrr']);group['arr']+=Decimal(estimate['arr'])
    for group in groups.values():
        for field in ('mrr','arr'):group[field]=format(group[field],'.2f')
    invoiced={}
    for sid,period,raw in db.execute('''SELECT i.subscription_id,i.period_start,f.estimate FROM saas_invoice_register i
      JOIN saas_subscriptions s ON s.id=i.subscription_id JOIN saas_offers f ON f.id=s.offer_id''').fetchall():
        invoice=saas_invoice_details(db,sid,period,today)
        estimate=json.loads(raw);key=(estimate['product_id'],invoice['currency'])
        group=invoiced.setdefault(key,{'product_name':estimate['product_name'],'currency':key[1],'invoiced':Decimal(0),'received':Decimal(0),'outstanding':Decimal(0),'overdue':Decimal(0)})
        for field,source in (('invoiced','total'),('received','paid'),('outstanding','balance')):group[field]+=Decimal(invoice[source])
        if invoice['status']=='EN_RETARD':group['overdue']+=Decimal(invoice['balance'])
    for group in invoiced.values():
        for key in ('invoiced','received','outstanding','overdue'):group[key]=str(group[key])
    return {'as_of':today,'counts':counts,'groups':[groups[k] for k in sorted(groups)],'billing_groups':[invoiced[k] for k in sorted(invoiced)]}

def saas_commercial_report(db,today):
    """Contractual forecast, offer conversion and maturity cohort; no assumed probabilities."""
    now=date.fromisoformat(today)
    beginning=(now-timedelta(days=30)).isoformat()
    horizon=(now+timedelta(days=90)).isoformat()
    groups={}
    def group(e):
        key=(e['product_id'],e['currency'])
        return groups.setdefault(key,{'product':e['product_name'],'currency':key[1],
            'draft':0,'validated':0,'sent':0,'accepted':0,'refused':0,'cancelled':0,'expired_offers':0,
            'active':0,'mrr':Decimal(0),'arr':Decimal(0),'cohort_open':0,'cohort_lost':0,
            'due_30':0,'renewed_30':0,'unrenewed_30':0,'forecast_90':Decimal(0),'past_unbilled':Decimal(0),'manual_schedule':0,
            'terminated_30':0})
    opportunities={};converted={}
    for oid,raw,until,status in db.execute("""SELECT f.opportunity_id,f.estimate,f.valid_until,COALESCE(
      (SELECT e.status FROM saas_offer_events e WHERE e.offer_id=f.id ORDER BY version DESC LIMIT 1),'BROUILLON') FROM saas_offers f"""):
        e=json.loads(raw);g=group(e)
        opportunities.setdefault((e['product_id'],e['currency']),set()).add(oid)
        if status in ('BROUILLON','VALIDEE','TRANSMISE') and until<today:g['expired_offers']+=1
        else:g[{'BROUILLON':'draft','VALIDEE':'validated','TRANSMISE':'sent','ACCEPTEE':'accepted','REFUSEE':'refused','ANNULEE':'cancelled'}[status]]+=1
    billed={tuple(r) for r in db.execute('SELECT subscription_id,period_start FROM saas_invoice_register')}
    for sid,start,end,raw,successor,oid in db.execute('''SELECT s.id,s.starts_on,s.ends_on,f.estimate,r.successor_id,f.opportunity_id
      FROM saas_subscriptions s JOIN saas_offers f ON f.id=s.offer_id
      LEFT JOIN saas_subscription_renewals r ON r.predecessor_id=s.id'''):
        e=json.loads(raw);g=group(e)
        converted.setdefault((e['product_id'],e['currency']),set()).add(oid)
        if start<=today<end:
            g['active']+=1;g['mrr']+=Decimal(e['mrr']);g['arr']+=Decimal(e['arr'])
        if start<=beginning<end:
            g['cohort_open']+=1
            if end<=today and not successor:g['cohort_lost']+=1
        if beginning<end<=today:
            g['due_30']+=1
            g['renewed_30' if successor else 'unrenewed_30']+=1
        schedule=subscription_schedule(start,end,e)
        if schedule is None:
            if end>today:g['manual_schedule']+=1
            continue
        for p in schedule:
            if (sid,p['period_start']) in billed:continue
            amount=Decimal(p['recurring'])+Decimal(p['one_off'])
            if p['period_start']<today:g['past_unbilled']+=amount
            elif p['period_start']<=horizon:g['forecast_90']+=amount
    for raw,effective in db.execute("""SELECT f.estimate,e.effective_on FROM saas_subscription_events e
      JOIN saas_subscriptions s ON s.id=e.subscription_id JOIN saas_offers f ON f.id=s.offer_id
      WHERE e.action='RESILIATION' AND e.effective_on>? AND e.effective_on<=?""",(beginning,today)):
        group(json.loads(raw))['terminated_30']+=1
    def ratio(n,d):
        return str((Decimal(n)*100/d).quantize(Decimal('0.01'))) if d else None
    items=[]
    for key,g in sorted(groups.items()):
        prospect_count=len(opportunities.get(key,()))
        converted_count=len(converted.get(key,()))
        items.append({**{k:str(v) if isinstance(v,Decimal) else v for k,v in g.items()},
            'opportunities':prospect_count,'converted_opportunities':converted_count,'subscription_conversion_pct':ratio(converted_count,prospect_count),
            'offer_conversion_pct':ratio(g['accepted'],g['accepted']+g['refused']),
            'churn_proxy_pct':ratio(g['cohort_lost'],g['cohort_open'])})
    return {'as_of':today,'cohort_start':beginning,'forecast_end':horizon,'items':items}

def saas_commercial(h,connect):
    with connect() as db:
        db.execute('BEGIN')
        return h.json_response(200,saas_commercial_report(db,date.today().isoformat()))

def partner_profitability(h,connect):
    try:
        query=parse_qs(urlsplit(h.path).query);page=int(query.get('page',['1'])[0]);q=query.get('q',[''])[0][:120].casefold();currency=query.get('currency',[''])[0]
        if not 1<=page<=10000 or currency not in ('','EUR','USD','GNF','XOF'):raise ValueError()
    except ValueError:return h.json_response(400,{'error':'Filtre invalide.'})
    with connect() as db:
        db.execute('BEGIN');groups={}
        def group(pid,name,c):
            return groups.setdefault((pid,c),{'partner_id':pid,'partner':name,'currency':c,'mission_received':Decimal(0),'saas_received':Decimal(0),'mission_expenses':Decimal(0),'commission_paid':Decimal(0),'commission_approved':Decimal(0),'commission_overlap':Decimal(0),'conflicts':0,'referrals':0})
        for oid,pid,name,c in db.execute('''SELECT r.opportunity_id,o.id,o.name,r.currency FROM partner_referrals r JOIN partner_agreements a ON a.id=r.agreement_id JOIN organizations o ON o.id=a.partner_id'''):
            group(pid,name,c)['referrals']+=1
            for cur,amount in db.execute('''SELECT q.currency,p.amount FROM payments p JOIN invoices i ON i.id=p.invoice_id JOIN missions m ON m.id=i.mission_id JOIN quotes q ON q.id=m.quote_id WHERE m.opportunity_id=?''',(oid,)):
                group(pid,name,cur)['mission_received']+=Decimal(amount)
            for cur,amount in db.execute('''SELECT e.currency,e.amount FROM expenses e JOIN missions m ON m.id=e.mission_id WHERE m.opportunity_id=?''',(oid,)):
                group(pid,name,cur)['mission_expenses']+=Decimal(amount)
            for cur,amount in db.execute('''SELECT p.currency,r.amount FROM saas_receipts r JOIN saas_invoice_register i ON i.id=r.invoice_id JOIN saas_billing_preparations p ON p.subscription_id=i.subscription_id AND p.period_start=i.period_start JOIN saas_subscriptions s ON s.id=i.subscription_id JOIN saas_offers f ON f.id=s.offer_id WHERE f.opportunity_id=?''',(oid,)):
                group(pid,name,cur)['saas_received']+=Decimal(amount)
            g=group(pid,name,c)
            for (amount,) in db.execute('SELECT amount FROM partner_commission_approvals WHERE opportunity_id=?',(oid,)):g['commission_approved']+=Decimal(amount)
            for ref,amount in db.execute('SELECT reference,amount FROM partner_commission_payments WHERE opportunity_id=?',(oid,)):
                n=Decimal(amount);g['commission_paid']+=n
                expense=db.execute('SELECT e.currency,e.amount,m.opportunity_id FROM expenses e LEFT JOIN missions m ON m.id=e.mission_id WHERE e.reference=? COLLATE NOCASE',(ref,)).fetchone()
                if expense:
                    if expense[0]==c and Decimal(expense[1])==n and expense[2]==oid:g['commission_overlap']+=n
                    else:g['conflicts']+=1
        items=[]
        for g in groups.values():
            received=g['mission_received']+g['saas_received'];out=g['mission_expenses']+g['commission_paid']-g['commission_overlap'];net=received-out
            g.update(received=received,documented_outflows=out,contribution=None if g['conflicts'] else net,contribution_pct=None if g['conflicts'] or not received else (net*100/received).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP))
            if (not currency or g['currency']==currency) and q in (g['partner']+' '+g['currency']).casefold():items.append(g)
        items.sort(key=lambda g:(g['currency'],g['contribution'] is None,-(g['contribution'] or Decimal(0)),g['partner'].casefold(),g['partner_id']))
    return h.json_response(200,{'items':[{k:str(v) if isinstance(v,Decimal) else v for k,v in g.items()} for g in items[(page-1)*10:page*10]],'total':len(items),'page':page,'as_of':date.today().isoformat()})

def partner_finance(h,connect,method):
    today=date.today().isoformat()
    if method=='GET':
        try:
            query=parse_qs(urlsplit(h.path).query);page=int(query.get('page',['1'])[0]);q=query.get('q',[''])[0][:120].casefold()
            if not 1<=page<=10000:raise ValueError()
        except ValueError:return h.json_response(400,{'error':'Page invalide.'})
        with connect() as db:
            db.row_factory=sqlite3.Row;db.execute('BEGIN')
            rows=[dict(r) for r in db.execute('''SELECT r.opportunity_id,r.currency,r.commission,r.basis,p.status,p.title,o.id AS partner_id,o.name AS partner,
                a.amount AS approved,a.reference AS approval_reference,a.approved_on FROM partner_referrals r
                JOIN opportunities p ON p.id=r.opportunity_id JOIN partner_agreements g ON g.id=r.agreement_id
                JOIN organizations o ON o.id=g.partner_id LEFT JOIN partner_commission_approvals a ON a.opportunity_id=r.opportunity_id
                WHERE a.opportunity_id IS NOT NULL OR p.status IN ('GAGNE','EN_MISSION','TERMINE') ORDER BY o.name_key,p.title,r.opportunity_id''')]
            groups={}
            for r in rows:
                payments=[dict(p) for p in db.execute('SELECT reference,amount,paid_on FROM partner_commission_payments WHERE opportunity_id=? ORDER BY paid_on,id',(r['opportunity_id'],))]
                paid=sum((Decimal(p['amount']) for p in payments),Decimal(0));approved=Decimal(r['approved'] or '0');balance=approved-paid
                r.update(payments=payments,paid=str(paid),balance=str(balance),state='A_VALIDER' if r['approved'] is None else 'REGLEE' if balance==0 else 'PARTIELLE' if paid else 'DUE')
                g=groups.setdefault((r['partner_id'],r['currency']),{'partner':r['partner'],'currency':r['currency'],'approved':Decimal(0),'paid':Decimal(0),'balance':Decimal(0),'pending':0})
                g['approved']+=approved;g['paid']+=paid;g['balance']+=balance;g['pending']+=r['approved'] is None
        totals=[{k:str(v) if isinstance(v,Decimal) else v for k,v in g.items()} for g in groups.values()]
        if urlsplit(h.path).path.startswith('/api/admin/direction/'):return h.json_response(200,{'items':totals,'as_of':today})
        rows=[r for r in rows if q in (r['partner']+' '+r['title']+' '+r['state']+' '+(r['approval_reference'] or '')+' '+' '.join(p['reference'] for p in r['payments'])).casefold()]
        return h.json_response(200,{'items':rows[(page-1)*10:page*10],'total':len(rows),'page':page,'can_write':h.role in ('ADMIN','COMPTABLE')})
    if h.role not in ('ADMIN','COMPTABLE'):return h.json_response(403,{'error':'Action réservée à la comptabilité.'})
    try:
        size=int(h.headers.get('Content-Length','0'))
        if not 0<size<=8000 or h.headers.get_content_type()!='application/json':raise ValueError()
        data=json.loads(h.rfile.read(size))
        if not isinstance(data,dict):raise ValueError()
        action=data['action'];oid=data['opportunity_id'];reference=data['reference']
        if not isinstance(oid,str) or str(uuid.UUID(oid))!=oid or not isinstance(reference,str) or not reference.strip() or len(reference)>120 or any(ord(c)<32 for c in reference):raise ValueError()
        reference=reference.strip()
        if action=='approve':
            if set(data)!={'action','opportunity_id','reference'}:raise ValueError()
        elif action=='payment':
            if set(data)!={'action','opportunity_id','reference','amount','paid_on'}:raise ValueError()
            paid_on=data['paid_on']
            if not isinstance(paid_on,str) or date.fromisoformat(paid_on).isoformat()!=paid_on or paid_on>today:raise ValueError()
        else:raise ValueError()
    except (ValueError,TypeError,KeyError,UnicodeError):return h.json_response(400,{'error':'Champs invalides.'})
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT r.currency,r.commission,p.status FROM partner_referrals r JOIN opportunities p ON p.id=r.opportunity_id WHERE r.opportunity_id=?',(oid,)).fetchone()
        if not row:return h.json_response(404,{'error':'Apport introuvable.'})
        approval=db.execute('SELECT amount,approved_on FROM partner_commission_approvals WHERE opportunity_id=?',(oid,)).fetchone()
        if action=='approve':
            if approval or row[2] not in ('GAGNE','EN_MISSION','TERMINE'):return h.json_response(409,{'error':'Apport non gagné ou déjà validé.'})
            db.execute('INSERT INTO partner_commission_approvals VALUES(?,?,?,?,?)',(oid,row[1],reference,today,h.actor));event='COMMISSION_PARTENAIRE_VALIDEE'
        else:
            if not approval or paid_on<approval[1]:return h.json_response(409,{'error':'Validation préalable requise.'})
            try:
                amount=saas_money(data['amount'],row[0])
                if amount<=0:raise ValueError()
            except ValueError:return h.json_response(400,{'error':'Montant invalide.'})
            paid=sum((Decimal(p[0]) for p in db.execute('SELECT amount FROM partner_commission_payments WHERE opportunity_id=?',(oid,))),Decimal(0))
            if paid+amount>Decimal(approval[0]) or db.execute('SELECT 1 FROM partner_commission_payments WHERE reference=?',(reference,)).fetchone():return h.json_response(409,{'error':'Surpaiement ou référence déjà utilisée.'})
            db.execute('INSERT INTO partner_commission_payments VALUES(?,?,?,?,?,?)',(str(uuid.uuid4()),oid,reference,str(amount),paid_on,h.actor));event='COMMISSION_PARTENAIRE_REGLEE'
        accounts.event(db,h.actor,event,oid)
    return h.json_response(201,{'id':oid})

def partners(h,connect,method):
    today=date.today().isoformat()
    if method=='GET':
        try:
            query=parse_qs(urlsplit(h.path).query);page=int(query.get('page',['1'])[0]);q=query.get('q',[''])[0][:120].casefold()
            if not 1<=page<=10000:raise ValueError()
        except ValueError:return h.json_response(400,{'error':'Page invalide.'})
        with connect() as db:
            db.row_factory=sqlite3.Row;db.execute('BEGIN')
            agreements=[dict(r) for r in db.execute('SELECT a.*,o.name AS partner FROM partner_agreements a JOIN organizations o ON o.id=a.partner_id ORDER BY a.ends_on,a.id')]
            referrals=[dict(r) for r in db.execute('''SELECT r.*,a.partner_id,a.reference,o.name AS partner,p.title,p.status FROM partner_referrals r
                JOIN partner_agreements a ON a.id=r.agreement_id JOIN organizations o ON o.id=a.partner_id
                JOIN opportunities p ON p.id=r.opportunity_id ORDER BY r.created_on DESC,r.opportunity_id''')]
            groups=[]
            for oid,name in db.execute("SELECT id,name FROM organizations WHERE kind='PARTENAIRE' OR id IN (SELECT partner_id FROM partner_agreements) ORDER BY name_key,id"):
                rows=[r for r in referrals if r['partner_id']==oid];totals={}
                for r in rows:
                    if r['status']=='PERDU':continue
                    bucket=totals.setdefault(r['currency'],{'pipeline':Decimal(0),'won':Decimal(0)})
                    bucket['won' if r['status'] in ('GAGNE','EN_MISSION','TERMINE') else 'pipeline']+=Decimal(r['commission'])
                groups.append({'id':oid,'name':name,'active_agreements':sum(a['partner_id']==oid and a['starts_on']<=today<=a['ends_on'] for a in agreements),'referrals':len(rows),'won':sum(r['status'] in ('GAGNE','EN_MISSION','TERMINE') for r in rows),'commission':{c:{k:str(v) for k,v in b.items()} for c,b in totals.items()}})
            if urlsplit(h.path).path.startswith('/api/admin/direction/'):
                return h.json_response(200,{'partners':groups,'as_of':today})
            available=[dict(r) for r in db.execute('SELECT id,title,company FROM opportunities WHERE id NOT IN (SELECT opportunity_id FROM partner_referrals) ORDER BY title,id')]
        aa=[a for a in agreements if q in (a['partner']+' '+a['reference']+' '+a['kind']).casefold()]
        rr=[r for r in referrals if q in (r['partner']+' '+r['title']+' '+r['reference']).casefold()]
        return h.json_response(200,{'partners':groups,'agreements':aa[(page-1)*10:page*10],'agreement_total':len(aa),'referrals':rr[(page-1)*10:page*10],'referral_total':len(rr),'active_agreements':[{'id':a['id'],'label':a['partner']+' · '+a['reference']} for a in agreements if a['starts_on']<=today<=a['ends_on']],'opportunities':available,'page':page,'can_write':h.role in ('ADMIN','COMMERCIAL')})
    if h.role not in ('ADMIN','COMMERCIAL'):return h.json_response(403,{'error':'Action réservée au commerce.'})
    try:
        size=int(h.headers.get('Content-Length','0'))
        if not 0<size<=8000 or h.headers.get_content_type()!='application/json':raise ValueError()
        data=json.loads(h.rfile.read(size))
        if not isinstance(data,dict):raise ValueError()
        def content(k,n):
            v=data[k]
            if not isinstance(v,str) or not v.strip() or len(v)>n or any(ord(c)<32 for c in v):raise ValueError()
            return v.strip()
        def identifier(k):
            v=content(k,36)
            if str(uuid.UUID(v))!=v:raise ValueError()
            return v
        action=data.get('action')
        if action=='agreement':
            if set(data)!={'action','partner_id','reference','kind','starts_on','ends_on','rate'}:raise ValueError()
            partner=identifier('partner_id');reference=content('reference',120);kind=content('kind',20)
            starts=content('starts_on',10);ends=content('ends_on',10)
            if kind not in ('COMMERCIAL','TECHNOLOGIQUE','APPORTEUR') or any(date.fromisoformat(v).isoformat()!=v for v in (starts,ends)) or starts>ends:raise ValueError()
            rate=saas_money(data['rate'],'EUR')
            if rate>100:raise ValueError()
        elif action=='referral':
            if set(data)!={'action','opportunity_id','agreement_id','currency','basis'}:raise ValueError()
            opportunity=identifier('opportunity_id');agreement=identifier('agreement_id');currency=content('currency',3)
            if currency not in ('EUR','USD','GNF','XOF'):raise ValueError()
            basis=saas_money(data['basis'],currency)
        else:raise ValueError()
    except (ValueError,TypeError,KeyError,UnicodeError):return h.json_response(400,{'error':'Champs invalides.'})
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if action=='agreement':
            if not db.execute("SELECT 1 FROM organizations WHERE id=? AND kind='PARTENAIRE'",(partner,)).fetchone():return h.json_response(409,{'error':'Organisation partenaire requise.'})
            if db.execute('SELECT 1 FROM partner_agreements WHERE partner_id=? AND reference=?',(partner,reference)).fetchone():return h.json_response(409,{'error':'Convention déjà enregistrée.'})
            oid=str(uuid.uuid4());db.execute('INSERT INTO partner_agreements VALUES(?,?,?,?,?,?,?,?)',(oid,partner,reference,kind,starts,ends,str(rate),h.actor));event='CONVENTION_PARTENAIRE_CREEE'
        else:
            row=db.execute('''SELECT a.rate FROM partner_agreements a JOIN organizations o ON o.id=a.partner_id WHERE a.id=? AND o.kind='PARTENAIRE' AND a.starts_on<=? AND a.ends_on>=?''',(agreement,today,today)).fetchone()
            if not row or not db.execute('SELECT 1 FROM opportunities WHERE id=?',(opportunity,)).fetchone():return h.json_response(409,{'error':'Convention active et opportunité requises.'})
            if db.execute('SELECT 1 FROM partner_referrals WHERE opportunity_id=?',(opportunity,)).fetchone():return h.json_response(409,{'error':'Opportunité déjà attribuée.'})
            commission=(basis*Decimal(row[0])/100).quantize(Decimal('1' if currency in ('GNF','XOF') else '0.01'),rounding=ROUND_HALF_UP)
            oid=opportunity;db.execute('INSERT INTO partner_referrals VALUES(?,?,?,?,?,?,?)',(oid,agreement,currency,str(basis),str(commission),h.actor,today));event='OPPORTUNITE_PARTENAIRE_ATTRIBUEE'
        accounts.event(db,h.actor,event,oid)
    return h.json_response(201,{'id':oid})

def customer_growth(h,connect,method,operation='actions',identifier=None):
    today=date.today().isoformat()
    if method=='GET':
        query=parse_qs(urlsplit(h.path).query)
        try:
            page=int(query.get('page',['1'])[0]);q=query.get('q',[''])[0][:120].casefold()
            if not 1<=page<=10000:raise ValueError()
        except ValueError:return h.json_response(400,{'error':'Page invalide.'})
        with connect() as db:
            db.row_factory=sqlite3.Row;db.execute('BEGIN')
            actions=[dict(r) for r in db.execute('SELECT a.*,o.name AS company FROM customer_actions a JOIN organizations o ON o.id=a.organization_id ORDER BY a.due_on,a.id')]
            surveys=[dict(r) for r in db.execute('SELECT s.*,o.name AS company FROM customer_surveys s JOIN organizations o ON o.id=s.organization_id ORDER BY s.captured_on DESC,s.id')]
            groups=[]
            for oid,name in db.execute("SELECT id,name FROM organizations WHERE kind='CLIENT' ORDER BY name_key,id"):
                tickets=list(db.execute('SELECT status,due_on,closed_on,csat,nps FROM customer_tickets WHERE organization_id=?',(oid,)))
                client_actions=[a for a in actions if a['organization_id']==oid]
                client_surveys=[s for s in surveys if s['organization_id']==oid]
                scores=[r[3] for r in tickets if r[3] is not None]+[s['csat'] for s in client_surveys if s['csat'] is not None]
                nps=[r[4] for r in tickets if r[4] is not None]+[s['nps'] for s in client_surveys if s['nps'] is not None]
                closed=[r for r in tickets if r[2]]
                overdue=sum(r[0]=='OUVERT' and r[1]<today for r in tickets)
                late=sum(a['status']=='OUVERTE' and a['due_on']<today for a in client_actions)
                components={}
                if tickets:components['support']=0 if overdue else 100
                if closed:components['sla']=round(100*sum(r[2]<=r[1] for r in closed)/len(closed),1)
                if scores:components['csat']=round(100*sum(v>=4 for v in scores)/len(scores),1)
                if client_actions:components['actions']=0 if late else 100
                groups.append({'organization_id':oid,'company':name,'score':round(sum(components.values())/len(components),1) if components else None,
                    'components':components,'csat_count':len(scores),'nps_count':len(nps),
                    'nps':round(100*(sum(v>=9 for v in nps)-sum(v<=6 for v in nps))/len(nps),1) if nps else None,
                    'actions_open':sum(a['status']=='OUVERTE' for a in client_actions),'actions_overdue':late})
        selected=[a for a in actions if q in (a['company']+' '+a['title']).casefold()]
        if urlsplit(h.path).path.startswith('/api/admin/direction/'):
            return h.json_response(200,{'accounts':groups,'as_of':today})
        selected_surveys=[s for s in surveys if q in (s['company']+' '+s['reference']).casefold()]
        return h.json_response(200,{'accounts':groups,'items':selected[(page-1)*10:page*10],'total':len(selected),'surveys':selected_surveys[(page-1)*10:page*10],'survey_total':len(selected_surveys),'page':page,'as_of':today,'can_write':h.role in ('ADMIN','COMMERCIAL')})
    if h.role not in ('ADMIN','COMMERCIAL'):return h.json_response(403,{'error':'Action réservée au commerce.'})
    try:
        size=int(h.headers.get('Content-Length','0'))
        if not 0<size<=8000 or h.headers.get_content_type()!='application/json':raise ValueError()
        data=json.loads(h.rfile.read(size))
        if not isinstance(data,dict):raise ValueError()
        def content(key,limit):
            v=data[key]
            if not isinstance(v,str) or not v.strip() or len(v)>limit or chr(0) in v:raise ValueError()
            return v.strip()
        if identifier:
            if set(data)!={'version','outcome','status'} or type(data['version']) is not int or data['version']<1 or data['status'] not in ('TERMINEE','ANNULEE'):raise ValueError()
            outcome=content('outcome',1000)
        else:
            org=content('organization_id',36)
            if str(uuid.UUID(org))!=org:raise ValueError()
            if operation=='survey':
                if set(data)!={'organization_id','reference','captured_on','csat','nps'}:raise ValueError()
                reference=content('reference',180);captured=content('captured_on',10)
                if date.fromisoformat(captured).isoformat()!=captured or captured>today or all(data[k] is None for k in ('csat','nps')):raise ValueError()
                for k,lo,hi in (('csat',1,5),('nps',0,10)):
                    if data[k] is not None and (type(data[k]) is not int or not lo<=data[k]<=hi):raise ValueError()
            else:
                if set(data)!={'organization_id','kind','title','due_on'}:raise ValueError()
                kind=content('kind',20);title=content('title',180);due=content('due_on',10)
                if kind not in ('AMELIORATION','FIDELISATION','UPSELL','CROSS_SELL') or date.fromisoformat(due).isoformat()!=due or due<today:raise ValueError()
    except (ValueError,TypeError,UnicodeError,KeyError):return h.json_response(400,{'error':'Champs invalides.'})
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if identifier:
            row=db.execute('SELECT status,version FROM customer_actions WHERE id=?',(identifier,)).fetchone()
            if not row:return h.json_response(404,{'error':'Action introuvable.'})
            if tuple(row)!=('OUVERTE',data['version']):return h.json_response(409,{'error':'Action clôturée ou version obsolète.'})
            db.execute('UPDATE customer_actions SET status=?,outcome=?,closed_on=?,version=version+1 WHERE id=?',(data['status'],outcome,today,identifier))
            event='ACTION_CLIENT_CLOTUREE';code=200
        else:
            if not db.execute("SELECT 1 FROM organizations WHERE id=? AND kind='CLIENT'",(org,)).fetchone():return h.json_response(409,{'error':'Organisation cliente requise.'})
            identifier=str(uuid.uuid4());code=201
            if operation=='survey':
                if db.execute('SELECT 1 FROM customer_surveys WHERE organization_id=? AND reference=?',(org,reference)).fetchone():return h.json_response(409,{'error':'Réponse déjà enregistrée.'})
                db.execute('INSERT INTO customer_surveys VALUES(?,?,?,?,?,?,?)',(identifier,org,reference,captured,data['csat'],data['nps'],h.actor));event='ENQUETE_CLIENT_ENREGISTREE'
            else:
                db.execute('INSERT INTO customer_actions(id,organization_id,kind,title,due_on,actor) VALUES(?,?,?,?,?,?)',(identifier,org,kind,title,due,h.actor));event='ACTION_CLIENT_OUVERTE'
        accounts.event(db,h.actor,event,identifier)
    return h.json_response(code,{'id':identifier})

def customer_success(h,connect,method,identifier=None):
    today=date.today().isoformat()
    if method=='GET':
        query=parse_qs(urlsplit(h.path).query)
        try:
            page=int(query.get('page',['1'])[0]);q=query.get('q',[''])[0][:120].casefold()
            status=query.get('status',[''])[0]
            if not 1<=page<=10000 or status not in ('','OUVERT','RESOLU','RETARD'):raise ValueError()
        except ValueError:return h.json_response(400,{'error':'Filtre invalide.'})
        with connect() as db:
            db.row_factory=sqlite3.Row
            db.execute('BEGIN')
            rows=[dict(r) for r in db.execute('''SELECT t.*,o.name AS company FROM customer_tickets t
              JOIN organizations o ON o.id=t.organization_id ORDER BY t.opened_on DESC,t.id''')]
        groups={}
        for r in rows:
            r['overdue']=r['status']=='OUVERT' and r['due_on']<today
            r['sla_met']=r['closed_on']<=r['due_on'] if r['closed_on'] else None
            g=groups.setdefault(r['organization_id'],{'company':r['company'],'open':0,'overdue':0,'resolved':0,'sla_met':0,'csat':[],'nps':[]})
            g['open']+=r['status']=='OUVERT';g['overdue']+=r['overdue'];g['resolved']+=r['status']=='RESOLU';g['sla_met']+=r['sla_met'] is True
            for k in ('csat','nps'):
                if r[k] is not None:g[k].append(r[k])
        for g in groups.values():
            c,n=g.pop('csat'),g.pop('nps')
            g.update(csat_count=len(c),nps_count=len(n),csat_pct=round(sum(v>=4 for v in c)*100/len(c),1) if c else None,
                     nps_score=round((sum(v>=9 for v in n)-sum(v<=6 for v in n))*100/len(n),1) if n else None,
                     risk=g['overdue']>0 or any(v<=2 for v in c))
        if urlsplit(h.path).path=='/api/admin/direction/customer-success':
            return h.json_response(200,{'accounts':list(groups.values()),'total':len(rows),'as_of':today})
        selected=[r for r in rows if q in (r['company']+' '+r['title']).casefold() and (not status or status==r['status'] or status=='RETARD' and r['overdue'])]
        return h.json_response(200,{'items':selected[(page-1)*10:page*10],'total':len(selected),'page':page,'accounts':list(groups.values()),'as_of':today,'can_write':h.role in ('ADMIN','COMMERCIAL')})
    if h.role not in ('ADMIN','COMMERCIAL'):return h.json_response(403,{'error':'Action réservée au commerce.'})
    try:
        size=int(h.headers.get('Content-Length','0'))
        if not 0<size<=8000 or h.headers.get_content_type()!='application/json':raise ValueError()
        data=json.loads(h.rfile.read(size))
        if not isinstance(data,dict):raise ValueError()
        def content(key,limit,required=True):
            v=data[key]
            if not isinstance(v,str) or len(v)>limit or chr(0) in v or (required and not v.strip()):raise ValueError()
            return v.strip()
        if identifier is None:
            if set(data)!={'organization_id','title','priority','due_on'}:raise ValueError()
            org=content('organization_id',36);title=content('title',180);priority=content('priority',20);due=content('due_on',10)
            if str(uuid.UUID(org))!=org or priority not in ('BASSE','NORMALE','HAUTE','CRITIQUE') or date.fromisoformat(due).isoformat()!=due or due<today:raise ValueError()
        else:
            if set(data)!={'version','resolution','csat','nps','feedback_note'} or type(data['version']) is not int or data['version']<1:raise ValueError()
            resolution=content('resolution',1000);feedback=content('feedback_note',1000,False)
            for k,low,high in (('csat',1,5),('nps',0,10)):
                if data[k] is not None and (type(data[k]) is not int or not low<=data[k]<=high):raise ValueError()
    except (ValueError,TypeError,UnicodeError,KeyError):return h.json_response(400,{'error':'Champs invalides.'})
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if identifier is None:
            if not db.execute("SELECT 1 FROM organizations WHERE id=? AND kind='CLIENT'",(org,)).fetchone():return h.json_response(409,{'error':'Organisation cliente requise.'})
            identifier=str(uuid.uuid4())
            db.execute('INSERT INTO customer_tickets(id,organization_id,title,priority,due_on,status,opened_on,actor) VALUES(?,?,?,?,?,?,?,?)',(identifier,org,title,priority,due,'OUVERT',today,h.actor))
            accounts.event(db,h.actor,'TICKET_CLIENT_OUVERT',identifier)
        else:
            row=db.execute('SELECT version,status FROM customer_tickets WHERE id=?',(identifier,)).fetchone()
            if not row:return h.json_response(404,{'error':'Ticket introuvable.'})
            if row[0]!=data['version'] or row[1]!='OUVERT':return h.json_response(409,{'error':'Ticket déjà résolu ou version obsolète.'})
            db.execute("UPDATE customer_tickets SET status='RESOLU',closed_on=?,resolution=?,csat=?,nps=?,feedback_note=?,version=version+1 WHERE id=?",(today,resolution,data['csat'],data['nps'],feedback,identifier))
            accounts.event(db,h.actor,'TICKET_CLIENT_RESOLU',identifier)
    return h.json_response(201 if method=='POST' and 'organization_id' in data else 200,{'id':identifier})

def renewal_milestone(days):
    return next((n for n in (7,30,60,90) if days<=n),None) if days>=0 else None

def renewal_queue(db,today):
    now=date.fromisoformat(today)
    db.row_factory=sqlite3.Row
    items=[]
    for row in db.execute("""SELECT s.id,s.ends_on,s.reference,o.company,f.title,f.estimate
      FROM saas_subscriptions s JOIN saas_offers f ON f.id=s.offer_id JOIN opportunities o ON o.id=f.opportunity_id
      WHERE s.starts_on<=? AND s.ends_on>=? AND s.ends_on<=?
      AND NOT EXISTS(SELECT 1 FROM saas_subscription_renewals r WHERE r.predecessor_id=s.id)
      AND NOT EXISTS(SELECT 1 FROM saas_subscription_events e WHERE e.subscription_id=s.id AND e.action='RESILIATION')
      ORDER BY s.ends_on,s.id""",(today,today,(now+timedelta(days=90)).isoformat())):
        item=dict(row)
        estimate=json.loads(item.pop('estimate'))
        days=(date.fromisoformat(item['ends_on'])-now).days
        contacts=[dict(r) for r in db.execute('SELECT milestone,note,actor,contacted_on FROM saas_renewal_contacts WHERE subscription_id=? ORDER BY milestone DESC',(item['id'],))]
        milestone=renewal_milestone(days)
        pending=not any(c['milestone']==milestone for c in contacts)
        item.update(days=days,milestone=milestone,pending=pending,risk=days<=30 and pending,contacts=contacts,
                    product=estimate['product_name'],currency=estimate['currency'],arr=estimate['arr'])
        items.append(item)
    return items

def saas_renewal_queue(h,connect):
    try:
        query=parse_qs(urlsplit(h.path).query)
        page=int(query.get('page',['1'])[0]);q=query.get('q',[''])[0][:120].casefold()
        risk=query.get('risk',[''])[0]
        if not 1<=page<=10000 or risk not in ('','1'):raise ValueError()
    except ValueError:return h.json_response(400,{'error':'Filtre invalide.'})
    today=date.today().isoformat()
    with connect() as db:
        db.execute('BEGIN')
        rows=renewal_queue(db,today)
    totals={}
    for r in rows:
        totals[r['currency']]=totals.get(r['currency'],Decimal(0))+Decimal(r['arr'])
    filtered=[r for r in rows if (not risk or r['risk']) and q in (' '.join(str(r[k]) for k in ('company','title','reference','product'))).casefold()]
    return h.json_response(200,{'items':filtered[(page-1)*10:page*10],'total':len(filtered),'page':page,'as_of':today,
        'arr_exposure':{k:str(v) for k,v in totals.items()},'can_contact':h.role in ('ADMIN','COMMERCIAL')})

def saas_renewal_contact(h,connect,identifier):
    if h.role not in ('ADMIN','COMMERCIAL'):return h.json_response(403,{'error':'Relance réservée au commerce.'})
    try:
        length=int(h.headers.get('Content-Length','0'))
        if not 0<length<=4000 or h.headers.get_content_type()!='application/json':raise ValueError()
        data=json.loads(h.rfile.read(length))
        if not isinstance(data,dict) or set(data)!={'milestone','note'}:raise ValueError()
        milestone,note=data['milestone'],data['note']
        if type(milestone) is not int or milestone not in (7,30,60,90) or not isinstance(note,str) or not note.strip() or len(note)>1000 or chr(0) in note:raise ValueError()
    except (ValueError,TypeError,UnicodeError):return h.json_response(400,{'error':'Relance invalide.'})
    today=date.today().isoformat()
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=next((r for r in renewal_queue(db,today) if r['id']==identifier),None)
        if not row or row['milestone']!=milestone or not row['pending']:return h.json_response(409,{'error':'Échéance ou relance incompatible.'})
        db.execute('INSERT INTO saas_renewal_contacts VALUES(?,?,?,?,?)',(identifier,milestone,note.strip(),h.actor,today))
        accounts.event(db,h.actor,'ABONNEMENT_SAAS_RELANCE',identifier)
    return h.json_response(201,{'id':identifier,'milestone':milestone,'sent':False})

def subscription_lifecycle(db,identifier,start,end,today,role):
    db.row_factory=sqlite3.Row
    events=[dict(r) for r in db.execute('SELECT version,action,evidence,actor,effective_on,previous_end,created_at FROM saas_subscription_events WHERE subscription_id=? ORDER BY version',(identifier,))]
    last=events[-1] if events else None
    state=last['action'] if last else 'NORMAL'
    actions=[]
    if role=='ADMIN' and today<end and state!='RESILIATION':
        if start<=today: actions.append('REACTIVATION' if state=='SUSPENSION' else 'SUSPENSION')
        if not db.execute('SELECT 1 FROM saas_subscription_renewals WHERE predecessor_id=?',(identifier,)).fetchone():actions.append('RESILIATION')
    return {'state':state,'version':last['version'] if last else 0,'actions':actions,'events':events}

def saas_subscription_decision(h,connect,identifier):
    if h.role!='ADMIN':return h.json_response(403,{'error':'Décision réservée à un administrateur.'})
    try:
        length=int(h.headers.get('Content-Length','0'))
        if not 0<length<=4000 or h.headers.get_content_type()!='application/json':raise ValueError()
        data=json.loads(h.rfile.read(length))
        if not isinstance(data,dict) or set(data)!={'version','action','evidence','effective_on'}:raise ValueError()
        version,action,evidence,effective=(data[k] for k in ('version','action','evidence','effective_on'))
        if type(version) is not int or version<0 or action not in ('SUSPENSION','REACTIVATION','RESILIATION'):raise ValueError()
        if not isinstance(evidence,str) or not evidence.strip() or len(evidence)>1000 or chr(0) in evidence:raise ValueError()
        if not isinstance(effective,str) or date.fromisoformat(effective).isoformat()!=effective:raise ValueError()
    except (ValueError,TypeError,UnicodeError):return h.json_response(400,{'error':'Décision, date ou preuve invalide.'})
    today=date.today().isoformat()
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT s.starts_on,s.ends_on,f.estimate FROM saas_subscriptions s JOIN saas_offers f ON f.id=s.offer_id WHERE s.id=?',(identifier,)).fetchone()
        if not row:return h.json_response(404,{'error':'Abonnement introuvable.'})
        start,end,raw=row
        lifecycle=subscription_lifecycle(db,identifier,start,end,today,h.role)
        if version!=lifecycle['version'] or action not in lifecycle['actions']:return h.json_response(409,{'error':'Version ou état incompatible.'})
        if action=='RESILIATION':
            schedule=subscription_schedule(start,end,json.loads(raw))
            if not schedule or not today<=effective<=end or effective<=start or effective not in {p['period_end'] for p in schedule}:return h.json_response(409,{'error':'Résiliation à une limite de période contractuelle future requise.'})
            if db.execute('SELECT 1 FROM saas_billing_preparations WHERE subscription_id=? AND period_end>?',(identifier,effective)).fetchone():return h.json_response(409,{'error':'Échéances déjà préparées après cette date : régularisation manuelle requise.'})
            db.execute('UPDATE saas_subscriptions SET ends_on=? WHERE id=?',(effective,identifier))
        elif effective!=today:
            return h.json_response(400,{'error':'Suspension ou réactivation à la date du jour uniquement.'})
        db.execute('INSERT INTO saas_subscription_events(subscription_id,version,action,evidence,actor,effective_on,previous_end) VALUES(?,?,?,?,?,?,?)',(identifier,version+1,action,evidence.strip(),h.actor,effective,end))
        accounts.event(db,h.actor,'ABONNEMENT_SAAS_'+action,identifier)
    return h.json_response(200,{'id':identifier,'version':version+1,'action':action,'effective_on':effective})

def saas_subscriptions(h,connect,method):
    if method=='GET':
        query=parse_qs(urlsplit(h.path).query)
        try:
            page=int(query.get('page',['1'])[0]);q=query.get('q',[''])[0][:120]
            status=query.get('status',[''])[0]
            if not 1<=page<=10000 or status not in ('','PLANIFIE','ACTIF','EXPIRE','ECHEANCE_30J'):raise ValueError()
        except ValueError:return h.json_response(400,{'error':'Page invalide.'})
        with connect() as db:
            db.row_factory=sqlite3.Row
            today=date.today().isoformat()
            limit=(date.fromisoformat(today)+timedelta(days=30)).isoformat()
            source=''' FROM saas_subscriptions s JOIN saas_offers f ON f.id=s.offer_id
                JOIN opportunities o ON o.id=f.opportunity_id
                WHERE (instr(lower(f.title||' '||o.company||' '||s.reference),lower(?))>0 OR ?='') '''
            filters={'PLANIFIE':('s.starts_on>?',(today,)),'ACTIF':('s.starts_on<=? AND s.ends_on>?',(today,today)), 'EXPIRE':('s.ends_on<=?',(today,)), 'ECHEANCE_30J':('s.starts_on<=? AND s.ends_on>? AND s.ends_on<=?',(today,today,limit))}
            clause,params=filters.get(status,('1=1',()))
            source+=' AND ('+clause+')';args=(q,q,*params)
            db.execute('BEGIN')
            total=db.execute('SELECT count(*)'+source,args).fetchone()[0]
            rows=[dict(r) for r in db.execute('SELECT s.*,f.title,f.estimate,o.company'+source+' ORDER BY s.ends_on,s.id LIMIT 10 OFFSET ?',(*args,(page-1)*10))]
            for row in rows:
                row['estimate']=json.loads(row['estimate'])
                row['status']=subscription_status(row['starts_on'],row['ends_on'],today)
                row['days_to_end']=(date.fromisoformat(row['ends_on'])-date.fromisoformat(today)).days
                predecessor=db.execute('SELECT predecessor_id FROM saas_subscription_renewals WHERE successor_id=?',(row['id'],)).fetchone()
                successor=db.execute('SELECT successor_id FROM saas_subscription_renewals WHERE predecessor_id=?',(row['id'],)).fetchone()
                row['predecessor_id']=predecessor[0] if predecessor else None
                row['successor_id']=successor[0] if successor else None
                row['lifecycle']=subscription_lifecycle(db,row['id'],row['starts_on'],row['ends_on'],today,h.role)
            metrics=subscription_metrics(db,today)
        return h.json_response(200,{'items':rows,'total':total,'page':page,'metrics':metrics})
    if h.role!='ADMIN':return h.json_response(403,{'error':'Enregistrement réservé à un administrateur.'})
    try:
        length=int(h.headers.get('Content-Length','0'))
        if not 0<length<=4000 or h.headers.get_content_type()!='application/json':raise ValueError()
        data=json.loads(h.rfile.read(length))
        if not isinstance(data,dict) or set(data)-{'predecessor_id'}!={'offer_id','starts_on','ends_on','reference'}:raise ValueError()
        oid,start,end,reference=(data[k] for k in ('offer_id','starts_on','ends_on','reference'))
        predecessor=data.get('predecessor_id','')
        if not isinstance(predecessor,str) or (predecessor and str(uuid.UUID(predecessor))!=predecessor):raise ValueError()
        if not all(isinstance(v,str) for v in (oid,start,end,reference)) or str(uuid.UUID(oid))!=oid:raise ValueError()
        if any(date.fromisoformat(d).isoformat()!=d for d in (start,end)) or start>=end:raise ValueError()
        if not reference.strip() or len(reference)>500 or '\x00' in reference:raise ValueError()
    except (ValueError,TypeError,UnicodeError):return h.json_response(400,{'error':'Dates ou référence contractuelle invalides.'})
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        offer=db.execute('SELECT opportunity_id,inputs FROM saas_offers WHERE id=?',(oid,)).fetchone()
        if not offer:return h.json_response(404,{'error':'Offre introuvable.'})
        event=db.execute('SELECT status,created_at FROM saas_offer_events WHERE offer_id=? ORDER BY version DESC LIMIT 1',(oid,)).fetchone()
        if not event or event[0]!='ACCEPTEE' or start<event[1][:10]:return h.json_response(409,{'error':'Offre non acceptée ou début antérieur à son acceptation.'})
        if db.execute('SELECT 1 FROM saas_subscriptions WHERE offer_id=?',(oid,)).fetchone():return h.json_response(409,{'error':'Abonnement déjà enregistré.'})
        if predecessor:
            previous=db.execute('SELECT s.ends_on,f.opportunity_id,f.inputs FROM saas_subscriptions s JOIN saas_offers f ON f.id=s.offer_id WHERE s.id=?',(predecessor,)).fetchone()
            if not previous:return h.json_response(404,{'error':'Abonnement précédent introuvable.'})
            if db.execute("SELECT 1 FROM saas_subscription_events WHERE subscription_id=? AND action='RESILIATION'",(predecessor,)).fetchone():return h.json_response(409,{'error':'Abonnement résilié : nouvelle souscription distincte requise.'})
            if start!=previous[0] or offer[0]!=previous[1] or json.loads(offer[1])['product_id']!=json.loads(previous[2])['product_id'] or db.execute('SELECT 1 FROM saas_subscription_renewals WHERE predecessor_id=?',(predecessor,)).fetchone():return h.json_response(409,{'error':'Renouvellement incompatible : même opportunité, même produit, dates contiguës et un seul successeur requis.'})
        identifier=str(uuid.uuid4())
        db.execute('INSERT INTO saas_subscriptions(id,offer_id,starts_on,ends_on,reference,actor) VALUES(?,?,?,?,?,?)',(identifier,oid,start,end,reference.strip(),h.actor))
        if predecessor:
            db.execute('INSERT INTO saas_subscription_renewals VALUES(?,?)',(predecessor,identifier))
            accounts.event(db,h.actor,'ABONNEMENT_SAAS_RENOUVELE',identifier)
        accounts.event(db,h.actor,'ABONNEMENT_SAAS_ENREGISTRE',identifier)
    return h.json_response(201,{'id':identifier,'offer_id':oid})

SAAS_TRANSITIONS={'BROUILLON':('VALIDEE','ANNULEE'),'VALIDEE':('TRANSMISE','ANNULEE'),
                  'TRANSMISE':('ACCEPTEE','REFUSEE','ANNULEE')}

def saas_actions(status,until,role):
    if role not in ('ADMIN','COMMERCIAL'):return []
    return [action for action in SAAS_TRANSITIONS.get(status,())
            if (action!='VALIDEE' or role=='ADMIN') and
               (action not in ('VALIDEE','TRANSMISE','ACCEPTEE') or until>=date.today().isoformat())]

def saas_transition(h,connect,identifier):
    try:
        length=int(h.headers.get('Content-Length','0'))
        if not 0<length<=4000 or h.headers.get_content_type()!='application/json':raise ValueError()
        data=json.loads(h.rfile.read(length))
        if not isinstance(data,dict) or set(data)!={'version','action','evidence'}:raise ValueError()
        version,action,evidence=data['version'],data['action'],data['evidence']
        if type(version) is not int or version<1 or not isinstance(action,str) or action not in ('VALIDEE','TRANSMISE','ACCEPTEE','REFUSEE','ANNULEE'):raise ValueError()
        if not isinstance(evidence,str) or not evidence.strip() or len(evidence)>1000 or '\x00' in evidence:raise ValueError()
    except (ValueError,TypeError,UnicodeError):return h.json_response(400,{'error':'Décision ou preuve invalide.'})
    if action=='VALIDEE' and h.role!='ADMIN':return h.json_response(403,{'error':'Validation réservée à un administrateur.'})
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        offer=db.execute('SELECT valid_until FROM saas_offers WHERE id=?',(identifier,)).fetchone()
        if not offer:return h.json_response(404,{'error':'Offre introuvable.'})
        event=db.execute('SELECT version,status FROM saas_offer_events WHERE offer_id=? ORDER BY version DESC LIMIT 1',(identifier,)).fetchone()
        current,status=event if event else (1,'BROUILLON')
        if current!=version or action not in saas_actions(status,offer[0],h.role):return h.json_response(409,{'error':'Version, état ou validité incompatible.'})
        db.execute('INSERT INTO saas_offer_events(offer_id,version,status,actor,evidence) VALUES(?,?,?,?,?)',(identifier,version+1,action,h.actor,evidence.strip()))
        accounts.event(db,h.actor,'OFFRE_SAAS_'+action,identifier)
    return h.json_response(200,{'id':identifier,'status':action,'version':version+1})

def saas_offers(h,connect,method):
    if method=='GET':
        try:
            page=int(parse_qs(urlsplit(h.path).query).get('page',['1'])[0])
            if not 1<=page<=10000:raise ValueError()
        except ValueError:return h.json_response(400,{'error':'Page invalide.'})
        with connect() as db:
            db.row_factory=sqlite3.Row
            total=db.execute('SELECT count(*) FROM saas_offers').fetchone()[0]
            rows=[dict(r) for r in db.execute('''SELECT s.*,o.company,o.title opportunity_title FROM saas_offers s
                JOIN opportunities o ON o.id=s.opportunity_id ORDER BY s.created_at DESC,s.id DESC LIMIT 10 OFFSET ?''',((page-1)*10,))]
            for row in rows:
                row['inputs']=json.loads(row['inputs']);row['estimate']=json.loads(row['estimate'])
                history=[dict(e) for e in db.execute('SELECT version,status,actor,evidence,created_at FROM saas_offer_events WHERE offer_id=? ORDER BY version',(row['id'],))]
                row['history']=history;row['status']=history[-1]['status'] if history else 'BROUILLON';row['version']=history[-1]['version'] if history else 1
                row['actions']=saas_actions(row['status'],row['valid_until'],h.role)
                subscription=db.execute('SELECT id FROM saas_subscriptions WHERE offer_id=?',(row['id'],)).fetchone()
                row['subscription_id']=subscription[0] if subscription else None
                row['can_register_subscription']=h.role=='ADMIN' and row['status']=='ACCEPTEE' and not subscription
        return h.json_response(200,{'items':rows,'total':total,'page':page})
    try:
        length=int(h.headers.get('Content-Length','0'))
        if not 0<length<=6000 or h.headers.get_content_type()!='application/json':raise ValueError()
        data=json.loads(h.rfile.read(length))
        if not isinstance(data,dict) or set(data)!={'opportunity_id','title','valid_until','inputs'}:raise ValueError()
        oid,title,until=data['opportunity_id'],data['title'],data['valid_until']
        if not isinstance(oid,str) or str(uuid.UUID(oid))!=oid:raise ValueError()
        if not isinstance(title,str) or not title.strip() or len(title)>180 or '\x00' in title:raise ValueError()
        if not isinstance(until,str) or date.fromisoformat(until).isoformat()!=until or until<date.today().isoformat():raise ValueError()
        estimate=simulate_saas(data['inputs'])
    except (ValueError,TypeError,UnicodeError):return h.json_response(400,{'error':'Offre ou date de validité invalide.'})
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM opportunities WHERE id=?',(oid,)).fetchone():return h.json_response(404,{'error':'Opportunité introuvable.'})
        identifier=str(uuid.uuid4())
        db.execute('INSERT INTO saas_offers(id,opportunity_id,title,valid_until,inputs,estimate,actor) VALUES(?,?,?,?,?,?,?)',
                   (identifier,oid,title.strip(),until,json.dumps(data['inputs']),json.dumps(estimate,ensure_ascii=False),h.actor))
        accounts.event(db,h.actor,'OFFRE_SAAS_BROUILLON',identifier)
    return h.json_response(201,{'id':identifier,'status':'BROUILLON','estimate':estimate})

def validate(data):
    if not isinstance(data,dict) or set(data)!=set(FIELDS): raise ValueError()
    values={}
    for key,limit in FIELDS.items():
        value=data[key]
        if not isinstance(value,str) or len(value)>limit or "\x00" in value: raise ValueError()
        values[key]=value.strip()
    if not values["company"] or not values["title"]: raise ValueError()
    if values["email"] and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",values["email"]): raise ValueError()
    if values["status"] not in STATUSES or values["mode"] not in ("REGIE","FORFAIT","CONSEIL"): raise ValueError()
    if values["followup"] and date.fromisoformat(values["followup"]).isoformat()!=values["followup"]: raise ValueError()
    if values["consultant_id"] and str(uuid.UUID(values["consultant_id"]))!=values["consultant_id"]: raise ValueError()
    return values

def handle(h,connect,method):
    if not h.admin_authorized(): return
    if (h.headers.get("Origin") and h.headers["Origin"]!=h.expected_origin()) or h.headers.get("Sec-Fetch-Site")=="cross-site":
        return h.json_response(403,{"error":"Origine non autorisée."})
    path=urlsplit(h.path).path
    if path=='/api/admin/direction/partner-profitability' and method=='GET':return partner_profitability(h,connect)
    if path in ('/api/admin/billing/partner-commissions','/api/admin/direction/partner-commissions'):
        return partner_finance(h,connect,method)
    if path in ('/api/admin/crm/partners','/api/admin/direction/partners'):
        return partners(h,connect,method)
    if method=='GET' and path in ('/api/admin/crm/saas-commercial','/api/admin/direction/saas-commercial'):
        return saas_commercial(h,connect)
    if method=='GET' and path in ('/api/admin/crm/saas-renewals','/api/admin/direction/saas-renewals'):
        return saas_renewal_queue(h,connect)
    if path in ('/api/admin/crm/customer-success','/api/admin/direction/customer-success'):
        return customer_success(h,connect,method)
    if path in ('/api/admin/crm/customer-growth','/api/admin/direction/customer-growth'):
        return customer_growth(h,connect,method)
    if path=='/api/admin/crm/customer-growth/survey' and method=='POST':return customer_growth(h,connect,method,'survey')
    growth_route=re.fullmatch(r'/api/admin/crm/customer-growth/([0-9a-f-]{36})/close',path)
    if growth_route and method=='POST':return customer_growth(h,connect,method,identifier=growth_route.group(1))
    ticket_route=re.fullmatch(r'/api/admin/crm/customer-success/([0-9a-f-]{36})/resolve',path)
    if ticket_route and method=='POST':return customer_success(h,connect,method,ticket_route.group(1))
    contact_route=re.fullmatch(r'/api/admin/crm/saas-subscriptions/([0-9a-f-]{36})/renewal-contact',path)
    if contact_route and method=='POST':return saas_renewal_contact(h,connect,contact_route.group(1))
    billing_route=re.fullmatch(r'/api/admin/crm/saas-subscriptions/([0-9a-f-]{36})/billing',path)
    decision_route=re.fullmatch(r'/api/admin/crm/saas-subscriptions/([0-9a-f-]{36})/decision',path)
    if decision_route and method=='POST':return saas_subscription_decision(h,connect,decision_route.group(1))
    if billing_route and method in ('GET','POST'):return saas_billing(h,connect,method,billing_route.group(1))
    transition=re.fullmatch(r'/api/admin/crm/saas-offers/([0-9a-f-]{36})/decision',path)
    if method=='POST' and transition:return saas_transition(h,connect,transition.group(1))
    if path=='/api/admin/crm/saas-offers':
        return saas_offers(h,connect,method)
    if path=='/api/admin/crm/saas-subscriptions':
        return saas_subscriptions(h,connect,method)
    if method=="GET" and path=="/api/admin/crm/catalogue":
        return h.json_response(200,{"items":CATALOGUE})
    if method=='POST' and path=='/api/admin/crm/saas-simulation':
        try:
            length=int(h.headers.get('Content-Length','0'))
            if not 0<length<=4000 or h.headers.get_content_type()!='application/json':raise ValueError()
            result=simulate_saas(json.loads(h.rfile.read(length)))
        except (ValueError,TypeError,UnicodeError):
            return h.json_response(400,{'error':'Paramètres de simulation invalides.'})
        return h.json_response(200,result)
    if method=="GET":
        query=parse_qs(urlsplit(h.path).query)
        status=query.get("status",[""])[0]
        q=query.get("q",[""])[0][:120]
        try:
            page=max(1,min(10000,int(query.get("page",["1"])[0])))
            page_size = int(query.get("page_size", ["25"])[0])
            if page_size not in (10, 25, 50): raise ValueError()
            if status and status not in STATUSES: raise ValueError()
        except ValueError: return h.json_response(400,{"error":"Filtre invalide."})
        where=" WHERE (?='' OR o.status=?) AND (instr(lower(o.company),lower(?))>0 OR instr(lower(o.title),lower(?))>0 OR instr(lower(o.skills),lower(?))>0)"
        args=(status,status,q,q,q)
        with connect() as db:
            db.row_factory=sqlite3.Row
            total=db.execute("SELECT count(*) FROM opportunities o"+where,args).fetchone()[0]
            rows=[dict(r) for r in db.execute("SELECT o.*, c.name consultant_name,c.status consultant_status, coalesce(l.organization_id,'') organization_id, g.name organization_name FROM opportunities o LEFT JOIN consultants c ON c.id=o.consultant_id LEFT JOIN organization_links l ON l.opportunity_id=o.id LEFT JOIN organizations g ON g.id=l.organization_id"+where+" ORDER BY (o.followup=''),o.followup,o.id LIMIT ? OFFSET ?",(*args,page_size, (page-1)*page_size))]
            for row in rows:
                qualification = db.execute('SELECT payload FROM opportunity_qualification WHERE opportunity_id=?', (row['id'],)).fetchone()
                row['qualification'] = json.loads(qualification[0]) if qualification else QUALIFICATION_DEFAULT.copy()
                row['qualification_score'] = sum(row['qualification'][key] == 'YES' for key in CRITERIA)
            counts=dict(db.execute("SELECT status,count(*) FROM opportunities GROUP BY status").fetchall())
        return h.json_response(200,{"items":rows,"counts":counts,"total":total})
    try:
        length=int(h.headers.get("Content-Length","0"))
        if not 0<length<=16000 or h.headers.get_content_type()!="application/json": raise ValueError()
        data=json.loads(h.rfile.read(length))
        qualification = validate_qualification(data.pop('qualification')) if isinstance(data, dict) and 'qualification' in data else None
        version=data.pop("version",None) if isinstance(data,dict) else None
        organization_id=data.pop('organization_id',None) if isinstance(data,dict) else None
        if organization_id is not None and (not isinstance(organization_id,str) or (organization_id and str(uuid.UUID(organization_id))!=organization_id)): raise ValueError()
        values=validate(data)
        if method=="PATCH" and (type(version) is not int or version<1): raise ValueError()
        if method=="POST" and version is not None: raise ValueError()
    except (ValueError,TypeError,UnicodeError):
        return h.json_response(400,{"error":"Champs invalides."})
    keys=list(values)
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if organization_id and not db.execute('SELECT 1 FROM organizations WHERE id=?',(organization_id,)).fetchone():
            return h.json_response(400,{'error':'Organisation introuvable.'})
        if values["consultant_id"]:
            match=db.execute("SELECT status FROM consultants WHERE id=?",(values["consultant_id"],)).fetchone()
            if not match: return h.json_response(400,{"error":"Consultant introuvable."})
        if method=="POST":
            oid=str(uuid.uuid4())
            db.execute("INSERT INTO opportunities(id,"+",".join(keys)+") VALUES("+",".join("?" for _ in range(len(keys)+1))+")",(oid,*values.values()))
            version=1
        else:
            oid=path.rsplit("/",1)[-1]
            row=db.execute("SELECT version FROM opportunities WHERE id=?",(oid,)).fetchone()
            if not row: return h.json_response(404,{"error":"Opportunité introuvable."})
            if row[0]!=version: return h.json_response(409,{"error":"Dossier modifié. Actualisez."})
            version+=1
            db.execute("UPDATE opportunities SET "+",".join(k+"=?" for k in keys)+",version=? WHERE id=?",(*values.values(),version,oid))
        if qualification is not None:
            db.execute('INSERT INTO opportunity_qualification(opportunity_id,payload) VALUES(?,?) ON CONFLICT(opportunity_id) DO UPDATE SET payload=excluded.payload', (oid, json.dumps(qualification)))
        if organization_id is not None:
            db.execute('DELETE FROM organization_links WHERE opportunity_id=?',(oid,))
            if organization_id: db.execute('INSERT INTO organization_links VALUES(?,?)',(oid,organization_id))
        db.execute("INSERT INTO opportunity_events(opportunity_id,status,version) VALUES(?,?,?)",(oid,values["status"],version))
    return h.json_response(201 if method=="POST" else 200,{"id":oid,"version":version})
