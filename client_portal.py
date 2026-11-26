"""Client-only read projections and support intake, scoped by the session's organization."""
import json
import sqlite3
import time
import uuid
from datetime import date,timedelta
from decimal import Decimal
from urllib.parse import parse_qs,urlsplit
import accounts
import crm


def schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS client_accounts(
        account_id TEXT PRIMARY KEY REFERENCES accounts(id),
        organization_id TEXT NOT NULL REFERENCES organizations(id))""")
    db.execute('CREATE INDEX IF NOT EXISTS client_accounts_org ON client_accounts(organization_id)')
    db.execute("""CREATE TABLE IF NOT EXISTS client_portal_tickets(
        ticket_id TEXT PRIMARY KEY REFERENCES customer_tickets(id),
        account_id TEXT NOT NULL REFERENCES accounts(id),
        request_text TEXT NOT NULL)""")


def records(db,org,kind):
    if kind not in ('contracts','subscriptions','invoices','tickets'):
        raise ValueError('invalid projection')
    if kind=='contracts':
        return [dict(r) for r in db.execute("""SELECT m.contract_ref AS reference,q.title,m.start_date,m.end_date,m.status
            FROM missions m JOIN quotes q ON q.id=m.quote_id AND q.opportunity_id=m.opportunity_id
            JOIN organization_links l ON l.opportunity_id=m.opportunity_id
            WHERE l.organization_id=? ORDER BY m.start_date DESC,m.id""",(org,))]
    if kind=='subscriptions':
        rows=[]
        today=date.today().isoformat()
        for r in db.execute("""SELECT s.id,s.reference,f.title,s.starts_on,s.ends_on
            FROM saas_subscriptions s JOIN saas_offers f ON f.id=s.offer_id
            JOIN organization_links l ON l.opportunity_id=f.opportunity_id
            WHERE l.organization_id=? ORDER BY s.starts_on DESC,s.id""",(org,)):
            item=dict(r);sid=item.pop('id')
            item['status']=crm.subscription_status(item['starts_on'],item['ends_on'],today)
            lifecycle=crm.subscription_lifecycle(db,sid,item['starts_on'],item['ends_on'],today,'CLIENT')
            item['lifecycle']=lifecycle['state'];rows.append(item)
        return rows
    if kind=='invoices':
        rows=[]
        for r in db.execute("""SELECT i.id,i.reference,q.title,q.currency,i.amount,i.due_date
            FROM invoices i JOIN missions m ON m.id=i.mission_id
            JOIN quotes q ON q.id=m.quote_id AND q.opportunity_id=m.opportunity_id
            JOIN organization_links l ON l.opportunity_id=m.opportunity_id
            WHERE l.organization_id=? ORDER BY i.due_date DESC,i.id""",(org,)):
            item=dict(r);iid=item.pop('id')
            item['kind']='PRESTATION'
            item['payments']=[dict(p) for p in db.execute('SELECT reference,amount,paid_date AS paid_on FROM payments WHERE invoice_id=? ORDER BY paid_date,id',(iid,))]
            rows.append(item)
        for r in db.execute("""SELECT i.id,i.reference,f.title,p.currency,p.recurring,p.one_off,i.tax,i.due_on AS due_date
            FROM saas_invoice_register i JOIN saas_billing_preparations p ON p.subscription_id=i.subscription_id AND p.period_start=i.period_start
            JOIN saas_subscriptions s ON s.id=i.subscription_id JOIN saas_offers f ON f.id=s.offer_id
            JOIN organization_links l ON l.opportunity_id=f.opportunity_id
            WHERE l.organization_id=? ORDER BY i.due_on DESC,i.id""",(org,)):
            item=dict(r);iid=item.pop('id')
            item['amount']=str(sum((Decimal(item.pop(k)) for k in ('recurring','one_off','tax')),Decimal(0)))
            item['kind']='SAAS'
            item['payments']=[dict(p) for p in db.execute('SELECT reference,amount,paid_on FROM saas_receipts WHERE invoice_id=? ORDER BY paid_on,id',(iid,))]
            rows.append(item)
        for item in rows:
            paid=sum((Decimal(p['amount']) for p in item['payments']),Decimal(0))
            item.update(paid=str(paid),balance=str(Decimal(item['amount'])-paid))
        return sorted(rows,key=lambda x:(x['due_date'],x['reference'],x['kind']),reverse=True)
    return [dict(r) for r in db.execute("""SELECT t.id,t.title,t.status,t.opened_on,t.closed_on,p.request_text
        FROM customer_tickets t JOIN client_portal_tickets p ON p.ticket_id=t.id
        WHERE t.organization_id=? ORDER BY t.opened_on DESC,t.id""",(org,))]


def handle(h,connect,method):
    if not h.admin_authorized():return
    if h.role!='CLIENT' or h.headers.get('Authorization')!='Bearer session':
        return h.json_response(403,{'error':'Session client nominative requise.'})
    try:
        if method not in ('GET','POST'):raise ValueError()
        query=parse_qs(urlsplit(h.path).query,keep_blank_values=True)
        if set(query)-{'kind','page','q'} or any(len(v)!=1 for v in query.values()):raise ValueError()
        if method=='POST' and query:raise ValueError()
        kind=query.get('kind',['contracts'])[0];page=int(query.get('page',['1'])[0]);q=query.get('q',[''])[0].strip().casefold()
        if kind not in ('contracts','subscriptions','invoices','tickets') or not 1<=page<=10000 or len(q)>120:raise ValueError()
        if method=='POST':
            size=int(h.headers.get('Content-Length','0'))
            if not 0<size<=8000 or h.headers.get_content_type()!='application/json':raise ValueError()
            data=json.loads(h.rfile.read(size))
            if not isinstance(data,dict) or set(data)!={'title','description'}:raise ValueError()
            for key,limit in (('title',180),('description',2000)):
                if not isinstance(data[key],str) or not data[key].strip() or len(data[key])>limit or '\x00' in data[key]:raise ValueError()
    except (ValueError,TypeError,UnicodeError):return h.json_response(400,{'error':'Champs invalides.'})
    with connect() as db:
        db.row_factory=sqlite3.Row
        db.execute('BEGIN IMMEDIATE' if method=='POST' else 'BEGIN')
        # Recheck binding, current session and MFA inside the same transaction as access.
        org=db.execute("""SELECT o.id,o.name FROM client_accounts c JOIN organizations o ON o.id=c.organization_id
            JOIN accounts a ON a.id=c.account_id JOIN mfa m ON m.account_id=a.id AND m.enabled=1
            JOIN credentials k ON k.account_id=a.id JOIN sessions s ON s.account_id=a.id
            WHERE a.id=? AND a.enabled=1 AND a.role='CLIENT' AND o.kind='CLIENT'
            AND s.token_hash=? AND s.expires>?""",(h.actor_id,accounts.digest(accounts.session_cookie(h)),int(time.time()))).fetchone()
        if not org:return h.json_response(403,{'error':'Rattachement client ou session invalide.'})
        if method=='GET':
            items=[r for r in records(db,org['id'],kind) if q in ' '.join(str(v) for v in r.values()).casefold()]
            return h.json_response(200,{'organization':org['name'],'items':items[(page-1)*10:page*10],'total':len(items),'page':page})
        ident=str(uuid.uuid4());today=date.today()
        # Staff see the ticket in existing customer-success workflow; no external notification.
        db.execute("""INSERT INTO customer_tickets(id,organization_id,title,priority,due_on,status,opened_on,actor)
            VALUES(?,?,?,'NORMALE',?,'OUVERT',?,?)""",(ident,org['id'],data['title'].strip(),(today+timedelta(days=7)).isoformat(),today.isoformat(),h.actor))
        db.execute('INSERT INTO client_portal_tickets VALUES(?,?,?)',(ident,h.actor_id,data['description'].strip()))
        accounts.event(db,h.actor,'DEMANDE_CLIENT_CREEE',ident)
        db.commit()
        return h.json_response(201,{'id':ident})
