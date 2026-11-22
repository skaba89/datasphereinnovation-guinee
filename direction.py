"""Read-only executive dashboard; no mixing currencies or alternative quotes."""
from collections import Counter, defaultdict
from decimal import Decimal
from datetime import date
import sqlite3
import quotes
import controlling
import billing

def snapshot(db):
    db.row_factory=sqlite3.Row
    counts={}
    for name,table,col in [('requests','requests','status'),('crm','opportunities','status'),('consultants','consultants','status'),('tenders','tenders','stage'),('quotes','quotes','status')]:
        counts[name]=dict(db.execute(f'SELECT {col},count(*) FROM {table} GROUP BY {col}').fetchall())
    today=date.today().isoformat()
    overdue=db.execute("SELECT count(*) FROM opportunities WHERE followup<>'' AND followup<? AND status NOT IN ('TERMINE','PERDU')",(today,)).fetchone()[0]
    accepted=defaultdict(list)
    for row in db.execute("SELECT * FROM quotes WHERE status='ACCEPTE'"):
        accepted[row['opportunity_id']].append(dict(row))
    totals=defaultdict(lambda: {'revenue':Decimal(0),'direct_cost':Decimal(0),'margin':Decimal(0),'count':0})
    conflicts=0
    for alternatives in accepted.values():
        if len(alternatives)!=1:
            conflicts+=1; continue
        row=alternatives[0]; result=quotes.calculate(row); bucket=totals[row['currency']]
        for key in ('revenue','direct_cost','margin'): bucket[key]+=Decimal(result[key])
        bucket['count']+=1
    financial=[]
    for currency,bucket in sorted(totals.items()):
        financial.append({'currency':currency,**{k:str(v) if isinstance(v,Decimal) else v for k,v in bucket.items()}})
    saas=billing.saas_receivables(db,date.fromisoformat(today),'','',1,1)['totals']
    profitability=billing.saas_profitability(db)
    return {'counts':counts,'overdue':overdue,'financial':financial,'ambiguous_opportunities':conflicts,'as_of':today,'controlling':controlling.snapshot(db,today),'saas_finance':saas,'saas_profitability':profitability['groups']}
