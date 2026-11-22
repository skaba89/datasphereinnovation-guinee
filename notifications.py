"""Idempotent internal reminder runs; acknowledgements are scoped per actor."""
import sqlite3,uuid,json
from decimal import Decimal
from datetime import date, timedelta
from urllib.parse import urlsplit,parse_qs
import alerts,accounts

def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS notifications(id TEXT PRIMARY KEY, kind TEXT NOT NULL, entity_id TEXT NOT NULL, due TEXT NOT NULL, priority TEXT NOT NULL, label TEXT NOT NULL, details TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(kind,entity_id,due,priority))''')
    db.execute('''CREATE TABLE IF NOT EXISTS notification_reads(notification_id TEXT NOT NULL, actor TEXT NOT NULL, read_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(notification_id,actor))''')
    db.execute('''CREATE TABLE IF NOT EXISTS notification_runs(id INTEGER PRIMARY KEY, as_of TEXT NOT NULL, status TEXT NOT NULL, created INTEGER NOT NULL, active INTEGER NOT NULL, executed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')

def commercial_reminders(db,today):
    """Internal alerts with stable keys; no contact details or customer email."""
    now=today.isoformat()
    horizon=(today+timedelta(days=7)).isoformat()
    items=[]
    for rid,created,owner,priority,due in db.execute("""SELECT r.id,date(r.created_at),
        COALESCE(w.owner_id,''),COALESCE(w.priority,'NORMALE'),COALESCE(w.due_date,'')
        FROM requests r LEFT JOIN request_workflow w ON w.request_id=r.id
        WHERE r.status NOT IN ('GAGNEE','PERDUE')"""):
        def add(kind,deadline,level,details):
            items.append(dict(kind=kind,id=rid,due=deadline,priority=level,
                label='Demande '+rid,details=details))
        if due and due<=horizon:
            add('DEMANDE_ECHEANCE',due,'URGENT' if due<now else 'A_TRAITER',
                'Échéance commerciale dépassée' if due<now else 'Échéance commerciale à venir')
        if priority=='URGENTE' and not owner:
            add('DEMANDE_AFFECTATION',created,'URGENT','Demande urgente non affectée')
    # A stable deadline avoids creating a new notification every day.
    for rid,deadline in db.execute("""SELECT r.id,date(r.created_at,'+2 days')
        FROM requests r WHERE r.status='NOUVELLE'
        AND datetime(r.created_at,'+2 days')<=datetime(?)
        AND NOT EXISTS(SELECT 1 FROM request_events e WHERE e.request_id=r.id)""",
        (now,)):
        items.append(dict(kind='DEMANDE_RELANCE',id=rid,due=deadline,priority='URGENT',
            label='Demande '+rid,details='Demande sans changement de statut depuis au moins 48 h'))
    for oid,due in db.execute("""SELECT q.id,p.valid_until FROM quotes q
        JOIN quote_proposal_terms p ON p.quote_id=q.id
        JOIN quote_transmissions t ON t.quote_id=q.id AND t.version=q.version
        WHERE q.status='PROPOSE' AND p.valid_until<>'' AND p.valid_until<=?""",(horizon,)):
        items.append(dict(kind='DEVIS_VALIDITE',id=oid,due=due,priority='URGENT' if due<now else 'A_TRAITER',
            label='Devis '+oid,details='Validité expirée' if due<now else 'Fin de validité proche'))
    return items


def saas_reminders(db,today):
    now=today.isoformat(); horizon=(today+timedelta(days=30)).isoformat(); items=[]
    def add(kind,oid,label,due,details):
        items.append(dict(kind=kind,id=str(oid),label=label,due=due,details=details,priority='URGENT' if due<now else 'A_TRAITER'))
    for sid,ref,due in db.execute('''SELECT s.id,s.reference,s.ends_on FROM saas_subscriptions s
        WHERE s.starts_on<=? AND s.ends_on<=?
        AND NOT EXISTS(SELECT 1 FROM saas_subscription_renewals r WHERE r.predecessor_id=s.id)
        AND NOT EXISTS(SELECT 1 FROM saas_subscription_events e WHERE e.subscription_id=s.id AND e.action='RESILIATION')''',(now,horizon)):
        add('SAAS_RENOUVELLEMENT',sid,ref,due,'Renouvellement SaaS à examiner')
    for iid,ref,due,currency,recurring,one_off,tax in db.execute('''SELECT i.id,i.reference,i.due_on,p.currency,p.recurring,p.one_off,i.tax
        FROM saas_invoice_register i JOIN saas_billing_preparations p
        ON p.subscription_id=i.subscription_id AND p.period_start=i.period_start WHERE i.due_on<=?''',(horizon,)):
        paid=sum((Decimal(r[0]) for r in db.execute('SELECT amount FROM saas_receipts WHERE invoice_id=?',(iid,))),Decimal(0))
        balance=Decimal(recurring)+Decimal(one_off)+Decimal(tax)-paid
        if balance>0:add('SAAS_FACTURE',iid,ref,due,f'{balance} {currency} restant')
    return items


def _run(db,today):
    with db:
        db.execute('BEGIN IMMEDIATE');items=alerts.snapshot(db,today)+commercial_reminders(db,today)+saas_reminders(db,today);created=0
        db.execute('UPDATE notifications SET active=0 WHERE active=1')
        for x in items:
            key=(x['kind'],x['id'],x['due'],x['priority'])
            created+=db.execute('INSERT OR IGNORE INTO notifications(id,kind,entity_id,due,priority,label,details) VALUES(?,?,?,?,?,?,?)',(str(uuid.uuid4()),*key,x['label'],x['details'])).rowcount
            db.execute('UPDATE notifications SET active=1,label=?,details=? WHERE kind=? AND entity_id=? AND due=? AND priority=?',(x['label'],x['details'],*key))
        accounts.event(db,'scheduler','NOTIFICATIONS_REFRESH',f'{created} nouvelles')
        active=db.execute('SELECT count(*) FROM notifications WHERE active=1').fetchone()[0]
        db.execute('INSERT INTO notification_runs(as_of,status,created,active) VALUES(?,?,?,?)',(today.isoformat(),'PASS',created,active))
    return created

def run(db,today):
    try:
        return _run(db,today)
    except Exception:
        # Rollback first; record only a generic failure, never sensitive exception details.
        with db:
            db.execute('INSERT INTO notification_runs(as_of,status,created,active) VALUES(?,?,?,?)',(today.isoformat(),'FAIL',0,db.execute('SELECT count(*) FROM notifications WHERE active=1').fetchone()[0]))
        raise

def handle(h,connect,method):
    if not h.admin_authorized():return
    if h.headers.get('Sec-Fetch-Site')=='cross-site' or (h.headers.get('Origin') and h.headers['Origin']!=h.expected_origin()):return h.json_response(403,{'error':'Origine non autorisée.'})
    if method=='GET':
        query=parse_qs(urlsplit(h.path).query)
        try:
            page=int(query.get('page',['1'])[0]);state=query.get('state',['active'])[0]
            if not 1<=page<=10000 or state not in ('active','all','unread'):raise ValueError()
        except ValueError:return h.json_response(400,{'error':'Filtre invalide.'})
        where={'active':' WHERE n.active=1','all':'','unread':' WHERE n.active=1 AND r.read_at IS NULL'}[state]
        with connect() as db:
            db.row_factory=sqlite3.Row
            join=' FROM notifications n LEFT JOIN notification_reads r ON r.notification_id=n.id AND r.actor=?'
            items=[dict(x) for x in db.execute('SELECT n.*,r.read_at'+join+where+' ORDER BY n.active DESC,n.due,n.id LIMIT 25 OFFSET ?',(h.actor,(page-1)*25))]
            runs=[dict(x) for x in db.execute('SELECT * FROM notification_runs ORDER BY id DESC LIMIT 10')]
            return h.json_response(200,{'items':items,'total':db.execute('SELECT count(*)'+join+where,(h.actor,)).fetchone()[0],'unread':db.execute('SELECT count(*)'+join+' WHERE n.active=1 AND r.read_at IS NULL',(h.actor,)).fetchone()[0],'runs':runs})
    try:
        n=int(h.headers.get('Content-Length','0'))
        if not 0<n<=1000 or h.headers.get_content_type()!='application/json':raise ValueError()
        v=json.loads(h.rfile.read(n));oid=v['id']
        if set(v)!={'id'} or str(uuid.UUID(oid))!=oid:raise ValueError()
    except (ValueError,TypeError,KeyError,AttributeError):return h.json_response(400,{'error':'Notification invalide.'})
    with connect() as db:
        if not db.execute('SELECT 1 FROM notifications WHERE id=?',(oid,)).fetchone():return h.json_response(404,{'error':'Notification introuvable.'})
        if db.execute('INSERT OR IGNORE INTO notification_reads(notification_id,actor) VALUES(?,?)',(oid,h.actor)).rowcount:accounts.event(db,h.actor,'NOTIFICATION_LUE',oid)
    return h.json_response(200,{'status':'LUE'})
