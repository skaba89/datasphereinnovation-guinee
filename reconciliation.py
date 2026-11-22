"""Documented reconciliation decisions; source movements are never modified."""
import json
import hashlib
import sqlite3
import uuid
from decimal import Decimal
from urllib.parse import parse_qs,urlsplit


def schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS reconciliation_requests(
        id TEXT PRIMARY KEY, reference TEXT NOT NULL COLLATE NOCASE,
        snapshot TEXT NOT NULL, treatment TEXT NOT NULL, reason TEXT NOT NULL,
        evidence TEXT NOT NULL, actor_id TEXT NOT NULL, actor TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    db.execute("""CREATE TABLE IF NOT EXISTS reconciliation_decisions(
        request_id TEXT PRIMARY KEY REFERENCES reconciliation_requests(id),
        decision TEXT NOT NULL, reason TEXT NOT NULL, actor_id TEXT NOT NULL,
        actor TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    db.execute('CREATE INDEX IF NOT EXISTS reconciliation_reference ON reconciliation_requests(reference)')


def conflicts(db):
    for p,e,ref,day,currency,amount,oid,ed,ec,ea,mission,opportunity in db.execute("""
        SELECT p.id,e.id,p.reference,p.paid_on,r.currency,p.amount,p.opportunity_id,
               e.paid_date,e.currency,e.amount,e.mission_id,m.opportunity_id
        FROM partner_commission_payments p JOIN partner_referrals r ON r.opportunity_id=p.opportunity_id
        JOIN expenses e ON e.reference=p.reference COLLATE NOCASE
        LEFT JOIN missions m ON m.id=e.mission_id
        ORDER BY p.reference"""):
        if (day,currency,Decimal(amount))==(ed,ec,Decimal(ea)) and (not mission or opportunity==oid):
            continue
        yield {'reference':ref,'commission_id':p,'expense_id':e,'commission_date':day,
               'commission_currency':currency,'commission_amount':amount,'opportunity_id':oid,
               'expense_date':ed,'expense_currency':ec,'expense_amount':ea,
               'expense_mission':mission,'expense_opportunity':opportunity}


def snapshot(item):
    return json.dumps(item,sort_keys=True,separators=(',',':'))

def fingerprint(item):
    return hashlib.sha256(snapshot(item).encode()).hexdigest()


def approved(db,item):
    row=db.execute("""SELECT r.treatment FROM reconciliation_requests r
        JOIN reconciliation_decisions d ON d.request_id=r.id
        WHERE r.snapshot=? AND d.decision='APPROUVE'""",(snapshot(item),)).fetchone()
    return row[0] if row else None


def handle(h,connect,method):
    if not h.admin_authorized():return
    named=bool(h.actor_id)
    if method=='GET':
        try:
            q=parse_qs(urlsplit(h.path).query);page=int(q.get('page',['1'])[0]);search=q.get('q',[''])[0].strip().casefold()
            if not 1<=page<=10000 or len(search)>120:raise ValueError()
        except ValueError:return h.json_response(400,{'error':'Filtre invalide.'})
        with connect() as db:
            db.row_factory=sqlite3.Row;db.execute('BEGIN')
            items=[]
            for item in conflicts(db):
                if search not in ' '.join(str(x) for x in item.values()).casefold():continue
                history=[dict(r) for r in db.execute("""SELECT r.id,r.treatment,r.reason,r.evidence,r.actor,r.created_at,
                    r.snapshot,d.decision,d.reason AS decision_reason,d.actor AS reviewer,d.created_at AS decided_at,
                    r.actor_id FROM reconciliation_requests r LEFT JOIN reconciliation_decisions d ON d.request_id=r.id
                    WHERE r.reference=? ORDER BY r.created_at DESC,r.id""",(item['reference'],))]
                for entry in history:
                    entry['current']=entry.pop('snapshot')==snapshot(item)
                    entry['can_decide']=named and h.role=='ADMIN' and entry['actor_id']!=h.actor_id and not entry['decision'] and entry['current']
                    del entry['actor_id']
                item.update(history=history,treatment=approved(db,item),fingerprint=fingerprint(item),
                    can_propose=named and h.role in ('ADMIN','COMPTABLE') and not any(x['current'] and x['decision'] in (None,'APPROUVE') for x in history))
                items.append(item)
        return h.json_response(200,{'items':items[(page-1)*10:page*10],'total':len(items),'page':page})
    if not named or h.role not in ('ADMIN','COMPTABLE'):
        return h.json_response(403,{'error':'Compte nominatif autorisé requis.'})
    try:
        size=int(h.headers.get('Content-Length','0'))
        if not 0<size<=8000 or h.headers.get_content_type()!='application/json':raise ValueError()
        v=json.loads(h.rfile.read(size))
        if not isinstance(v,dict) or any(not isinstance(x,str) or not x.strip() or len(x)>500 or '\x00' in x for x in v.values()):raise ValueError()
        v={k:x.strip() for k,x in v.items()}
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if set(v)=={'reference','treatment','reason','evidence','fingerprint'} and v['treatment'] in ('DISTINCTS','DOUBLON'):
                item=next((x for x in conflicts(db) if x['reference']==v['reference']),None)
                if not item:return h.json_response(409,{'error':'Écart introuvable ou déjà résolu à la source.'})
                if v['fingerprint']!=fingerprint(item):return h.json_response(409,{'error':'Les mouvements ont changé ; actualisez le registre.'})
                if v['treatment']=='DOUBLON' and (item['commission_currency']!=item['expense_currency'] or Decimal(item['commission_amount'])!=Decimal(item['expense_amount'])):
                    return h.json_response(409,{'error':'Doublon impossible : devise ou montant différent.'})
                snap=snapshot(item)
                if db.execute("""SELECT 1 FROM reconciliation_requests r LEFT JOIN reconciliation_decisions d ON d.request_id=r.id
                    WHERE r.snapshot=? AND (d.decision IS NULL OR d.decision='APPROUVE')""",(snap,)).fetchone():
                    return h.json_response(409,{'error':'Une demande est déjà active.'})
                rid=str(uuid.uuid4())
                db.execute('INSERT INTO reconciliation_requests(id,reference,snapshot,treatment,reason,evidence,actor_id,actor) VALUES(?,?,?,?,?,?,?,?)',
                    (rid,item['reference'],snap,v['treatment'],v['reason'],v['evidence'],h.actor_id,h.actor))
                event='RAPPROCHEMENT_PROPOSE'
            elif set(v)=={'request_id','decision','reason'} and v['decision'] in ('APPROUVE','REJETE'):
                if h.role!='ADMIN':return h.json_response(403,{'error':'Validation administrateur requise.'})
                rid=v['request_id']
                r=db.execute('SELECT snapshot,actor_id FROM reconciliation_requests WHERE id=?',(rid,)).fetchone()
                if not r or r[1]==h.actor_id or db.execute('SELECT 1 FROM reconciliation_decisions WHERE request_id=?',(rid,)).fetchone():
                    return h.json_response(409,{'error':'Demande indisponible ou auto-validation interdite.'})
                if not any(snapshot(x)==r[0] for x in conflicts(db)):
                    return h.json_response(409,{'error':'Les mouvements ont changé ; nouvelle demande requise.'})
                db.execute('INSERT INTO reconciliation_decisions(request_id,decision,reason,actor_id,actor) VALUES(?,?,?,?,?)',
                    (rid,v['decision'],v['reason'],h.actor_id,h.actor))
                event='RAPPROCHEMENT_'+v['decision']
            else:raise ValueError()
            db.execute('INSERT INTO billing_events(entity_id,event) VALUES(?,?)',(rid,event))
        return h.json_response(201,{'id':rid})
    except (ValueError,TypeError,UnicodeError):return h.json_response(400,{'error':'Champs invalides.'})
    except sqlite3.IntegrityError:return h.json_response(409,{'error':'Demande déjà traitée.'})
