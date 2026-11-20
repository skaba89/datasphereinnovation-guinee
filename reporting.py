"""Period-based operational reports; no statutory accounting or historical reconstruction."""
import csv,io
from collections import defaultdict
from datetime import date
from decimal import Decimal
from urllib.parse import parse_qs,urlsplit
import missions

FIELDS=('period','currency','worked','billable','validated_revenue','validated_cost','margin','invoiced','received','outflows','net_flow')
NUMERIC=FIELDS[2:]

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
