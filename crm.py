"""Local CRM: opportunities, clients and linked consultant profiles."""
import json
import re
import sqlite3
import uuid
from decimal import Decimal, ROUND_HALF_UP
from datetime import date
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
