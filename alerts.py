"""Read-only computed business alerts; no external delivery or persistent queue."""
from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import urlsplit,parse_qs
import sqlite3

KINDS=('CONTRAT','FACTURE','CRA','RELANCE','RENOUVELLEMENT')

def snapshot(db,today,horizon_days=30):
    db.row_factory=sqlite3.Row
    now=today.isoformat(); horizon=(today+timedelta(days=horizon_days)).isoformat();items=[]
    def add(kind,oid,label,due,details=''):
        items.append(dict(kind=kind,id=oid,label=label,due=due,priority='URGENT' if due<now else 'A_TRAITER',details=details,days_remaining=(date.fromisoformat(due)-today).days))
    for r in db.execute("SELECT id,contract_ref,end_date FROM missions WHERE status='ACTIVE' AND end_date<=?",(horizon,)):
        add('CONTRAT',r['id'],r['contract_ref'],r['end_date'])
    for r in db.execute('SELECT i.id,i.reference,i.amount,i.due_date,q.currency FROM invoices i JOIN missions m ON m.id=i.mission_id JOIN quotes q ON q.id=m.quote_id WHERE i.due_date<=?',(horizon,)):
        paid=sum((Decimal(p[0]) for p in db.execute('SELECT amount FROM payments WHERE invoice_id=?',(r['id'],))),Decimal(0));balance=Decimal(r['amount'])-paid
        if balance>0:add('FACTURE',r['id'],r['reference'],r['due_date'],f'{balance} {r["currency"]} restant')
    for r in db.execute("SELECT a.id,a.work_date,m.contract_ref FROM activity a JOIN missions m ON m.id=a.mission_id WHERE a.status='SOUMIS' AND a.work_date<=?",(now,)):
        add('CRA',r['id'],r['contract_ref'],r['work_date'],'CRA soumis à valider')
    for r in db.execute("SELECT id,title,followup FROM opportunities WHERE status IN ('PROSPECT','QUALIFIE','PROPOSITION','NEGOCIATION') AND followup<>'' AND followup<=?",(horizon,)):
        add('RELANCE',r['id'],r['title'],r['followup'])
    for r in db.execute("SELECT r.id,r.old_end,m.contract_ref FROM contract_renewals r JOIN missions m ON m.id=r.mission_id WHERE r.status='SOUMIS'",()):
        add('RENOUVELLEMENT',r['id'],r['contract_ref'],r['old_end'],'Décision en attente')
    return sorted(items,key=lambda x:(x['due'],x['kind'],x['id']))

def handle(h,connect):
    if not h.admin_authorized():return
    query=parse_qs(urlsplit(h.path).query)
    try:
        page=int(query.get('page',['1'])[0]);kind=query.get('kind',[''])[0];priority=query.get('priority',[''])[0];horizon=int(query.get('horizon',['30'])[0])
        if horizon not in (7,30,60,90) or not 1<=page<=10000 or kind not in ('',*KINDS) or priority not in ('','URGENT','A_TRAITER'):raise ValueError()
    except ValueError:return h.json_response(400,{'error':'Filtre invalide.'})
    with connect() as db:
        today=date.today();items=snapshot(db,today,horizon);counts={k:sum(x['kind']==k for x in items) for k in KINDS}
        filtered=[x for x in items if (not kind or x['kind']==kind) and (not priority or x['priority']==priority)]
        return h.json_response(200,{'items':filtered[(page-1)*25:page*25],'total':len(filtered),'counts':counts,'as_of':today.isoformat(),'horizon':horizon,'urgent':sum(x['priority']=='URGENT' for x in items)})
