"""Local CRM: opportunities, clients and linked consultant profiles."""
import json
import re
import sqlite3
import uuid
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
    return {'as_of':today,'counts':counts,'groups':[groups[k] for k in sorted(groups)]}

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
