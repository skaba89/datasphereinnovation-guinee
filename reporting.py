"""Period-based operational reports; no statutory accounting or historical reconstruction."""
import csv,io
from collections import defaultdict
from datetime import date
from decimal import Decimal
from urllib.parse import parse_qs,urlsplit
import missions
import reconciliation

FIELDS=('period','currency','worked','billable','validated_revenue','validated_cost','margin','invoiced','received','outflows','net_flow')
NUMERIC=FIELDS[2:]

FLOW_FIELDS=('mission_received','saas_received','expenses','commission_paid','commission_overlap','conflicts','reviewed_conflicts')

def consolidated(db,year,today):
    """Recorded flows only; allocations never create additional cash movements."""
    groups=defaultdict(lambda:{k:Decimal(0) for k in FLOW_FIELDS})
    def bucket(day,currency):
        if day.startswith(year+'-') and day<=today:
            return groups[(day[:7],currency)]
    queries={
        'mission_received':'''SELECT p.paid_date,q.currency,p.amount FROM payments p JOIN invoices i ON i.id=p.invoice_id JOIN missions m ON m.id=i.mission_id JOIN quotes q ON q.id=m.quote_id''',
        'saas_received':'''SELECT r.paid_on,p.currency,r.amount FROM saas_receipts r JOIN saas_invoice_register i ON i.id=r.invoice_id JOIN saas_billing_preparations p ON p.subscription_id=i.subscription_id AND p.period_start=i.period_start''',
        'expenses':'SELECT paid_date,currency,amount FROM expenses'}
    for key,sql in queries.items():
        for day,currency,amount in db.execute(sql):
            b=bucket(day,currency)
            if b is not None:b[key]+=Decimal(amount)
    reviewed={x['reference']:reconciliation.approved(db,x) for x in reconciliation.conflicts(db)}
    for day,currency,amount,reference,oid in db.execute('''SELECT p.paid_on,r.currency,p.amount,p.reference,p.opportunity_id FROM partner_commission_payments p JOIN partner_referrals r ON r.opportunity_id=p.opportunity_id'''):
        b=bucket(day,currency)
        if b is not None:b['commission_paid']+=Decimal(amount)
        expense=db.execute('''SELECT e.paid_date,e.currency,e.amount,e.mission_id,m.opportunity_id FROM expenses e LEFT JOIN missions m ON m.id=e.mission_id WHERE e.reference=? COLLATE NOCASE''',(reference,)).fetchone()
        if expense:
            ed,ec,ea,mission,opportunity=expense
            if (ed,ec,Decimal(ea))==(day,currency,Decimal(amount)) and (not mission or opportunity==oid):
                if b is not None:b['commission_overlap']+=Decimal(amount)
            else:
                treatment=reviewed.get(reference)
                if treatment=='DOUBLON' and ed<=today and day<=today and b is not None:
                    b['commission_overlap']+=Decimal(amount)
                affected={(day[:7],currency),(ed[:7],ec)}
                for month,cur in affected:
                    if month.startswith(year+'-') and (month,cur) in groups:
                        key='reviewed_conflicts' if treatment=='DISTINCTS' or (treatment=='DOUBLON' and ed<=today and day<=today) else 'conflicts'
                        groups[(month,cur)][key]+=1
    annual=defaultdict(lambda:{k:Decimal(0) for k in FLOW_FIELDS})
    def row(period,currency,b):
        received=b['mission_received']+b['saas_received']
        out=b['expenses']+b['commission_paid']-b['commission_overlap']
        return {'period':period,'currency':currency,**{k:str(v) for k,v in b.items() if k not in ('conflicts','reviewed_conflicts')},
                'conflicts':int(b['conflicts']),'reviewed_conflicts':int(b['reviewed_conflicts']),'received':str(received),
                'outflows':None if b['conflicts'] else str(out),'net_flow':None if b['conflicts'] else str(received-out)}
    rows=[]
    for (month,currency),b in sorted(groups.items()):
        rows.append(row(month,currency,b))
        for k in FLOW_FIELDS:annual[currency][k]+=b[k]
    return rows,[row(year,c,b) for c,b in sorted(annual.items())]

def consolidation(h,connect):
    if not h.admin_authorized():return
    today=date.today().isoformat()
    try:
        q=parse_qs(urlsplit(h.path).query);year=q.get('year',[today[:4]])[0];page=int(q.get('page',['1'])[0]);search=q.get('q',[''])[0].strip().casefold();fmt=q.get('format',['json'])[0]
        if len(year)!=4 or not year.isascii() or not year.isdigit() or not 2000<=int(year)<=2099 or not 1<=page<=10000 or len(search)>120 or fmt not in ('json','csv'):raise ValueError()
    except ValueError:return h.json_response(400,{'error':'Filtre invalide.'})
    with connect() as db:
        db.execute('BEGIN');rows,annual=consolidated(db,year,today)
    rows=[r for r in rows if search in ' '.join(str(v) for v in r.values()).casefold()]
    if fmt=='json':return h.json_response(200,{'year':year,'as_of':today,'annual':annual,'items':rows[(page-1)*10:page*10],'total':len(rows),'page':page})
    output=io.StringIO();writer=csv.DictWriter(output,fieldnames=('period','currency',*FLOW_FIELDS,'received','outflows','net_flow'),delimiter=';');writer.writeheader();writer.writerows(rows)
    body=output.getvalue().encode('utf-8-sig');h.send_response(200);h.send_header('Content-Type','text/csv; charset=utf-8');h.send_header('Content-Disposition',f'attachment; filename="consolidation-{year}.csv"');h.send_header('Cache-Control','no-store');h.send_header('Content-Length',str(len(body)));h.end_headers();h.wfile.write(body)

def report(db,start,end):
    buckets=defaultdict(lambda:{k:Decimal(0) for k in NUMERIC})
    def bucket(day,currency):return buckets[(day[:7],currency)]
    # Aggregate by month and mission first: currency rounding follows mission rules.
    grouped=defaultdict(list); metadata={}
    for row in db.execute('''SELECT a.*,q.currency,q.mode,q.rate,q.daily_cost,q.days,q.expenses AS quote_expenses,q.fixed_price
        FROM activity a JOIN missions m ON m.id=a.mission_id JOIN quotes q ON q.id=m.quote_id
        WHERE a.status='VALIDE' AND a.work_date BETWEEN ? AND ?''',(start,end)):
        a=dict(row);key=(a['mission_id'],a['work_date'][:7]);grouped[key].append(a);metadata[key]={**a,'expenses':a['quote_expenses']}
    for key,entries in grouped.items():
        m=metadata[key];a=missions.amounts(m,entries);b=bucket(key[1],m['currency'])
        b['worked']+=Decimal(a['worked']);b['billable']+=Decimal(a['billable']);b['validated_cost']+=Decimal(a['actual_cost'])
        if a['billable_revenue'] is not None:b['validated_revenue']+=Decimal(a['billable_revenue'])
    # A fixed-price milestone is dated by the first recorded validation event.
    for r in db.execute('''SELECT q.currency,j.amount,date(min(e.created_at)) AS day FROM milestones j JOIN billing_events e ON e.entity_id=j.id AND e.event='JALON_VALIDE'
        JOIN missions m ON m.id=j.mission_id JOIN quotes q ON q.id=m.quote_id WHERE j.status='VALIDE' GROUP BY j.id HAVING day BETWEEN ? AND ?''',(start,end)):
        bucket(r['day'],r['currency'])['validated_revenue']+=Decimal(r['amount'])
    for key,sql in [('invoiced',"SELECT q.currency,i.amount,date(i.created_at) AS day FROM invoices i JOIN missions m ON m.id=i.mission_id JOIN quotes q ON q.id=m.quote_id WHERE date(i.created_at) BETWEEN ? AND ?"),('received',"SELECT q.currency,p.amount,p.paid_date AS day FROM payments p JOIN invoices i ON i.id=p.invoice_id JOIN missions m ON m.id=i.mission_id JOIN quotes q ON q.id=m.quote_id WHERE p.paid_date BETWEEN ? AND ?"),('outflows',"SELECT currency,amount,paid_date AS day FROM expenses WHERE paid_date BETWEEN ? AND ?")]:
        for r in db.execute(sql,(start,end)):bucket(r['day'],r['currency'])[key]+=Decimal(r['amount'])
    rows=[]
    for (period,currency),b in sorted(buckets.items()):
        b['margin']=b['validated_revenue']-b['validated_cost'];b['net_flow']=b['received']-b['outflows'];rows.append({'period':period,'currency':currency,**{k:str(v) for k,v in b.items()}})
    return rows

def handle(h,connect):
    if not h.admin_authorized():return
    if h.headers.get('Sec-Fetch-Site')=='cross-site' or (h.headers.get('Origin') and h.headers['Origin']!=h.expected_origin()):return h.json_response(403,{'error':'Origine non autorisée.'})
    try:
        q=parse_qs(urlsplit(h.path).query);start=q.get('start',[''])[0];end=q.get('end',[''])[0];format=q.get('format',['json'])[0]
        a,b=date.fromisoformat(start),date.fromisoformat(end)
        if a.isoformat()!=start or b.isoformat()!=end or not 0<=(b-a).days<=365 or format not in ('json','csv'):raise ValueError()
    except ValueError:return h.json_response(400,{'error':'Période invalide (366 jours maximum).'} )
    import sqlite3
    with connect() as db:
        db.row_factory=sqlite3.Row;db.execute('BEGIN');rows=report(db,start,end)
    if format=='json':return h.json_response(200,{'start':start,'end':end,'items':rows})
    output=io.StringIO();writer=csv.DictWriter(output,fieldnames=FIELDS,delimiter=';');writer.writeheader();writer.writerows(rows)
    body=output.getvalue().encode('utf-8-sig');h.send_response(200);h.send_header('Content-Type','text/csv; charset=utf-8');h.send_header('Content-Disposition',f'attachment; filename="reporting-{start}-{end}.csv"');h.send_header('Cache-Control','no-store');h.send_header('Content-Length',str(len(body)));h.end_headers();h.wfile.write(body)
