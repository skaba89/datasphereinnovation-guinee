"""Read-only executive dashboard; no mixing currencies or alternative quotes."""
from collections import Counter, defaultdict
from decimal import Decimal
from datetime import date
import sqlite3
import quotes
import controlling
import billing
import reporting
import alerts
import notifications


def strategic_snapshot(db,today,counts):
    """Decision indicators as of today, without creating notifications or cash flows."""
    now=today.isoformat()
    crm=counts['crm']; active=('PROSPECT','QUALIFIE','PROPOSITION','NEGOCIATION')
    pipeline=sum(crm.get(status,0) for status in active)
    won=sum(crm.get(status,0) for status in ('GAGNE','EN_MISSION','TERMINE'))
    lost=crm.get('PERDU',0)
    def count(sql,args=()):return db.execute(sql,args).fetchone()[0]
    reminders=alerts.snapshot(db,today)+notifications.commercial_reminders(db,today)+notifications.saas_reminders(db,today)
    urgent=Counter(x['kind'] for x in reminders if x['priority']=='URGENT')
    latest=db.execute('SELECT executed_at,status FROM notification_runs ORDER BY id DESC LIMIT 1').fetchone()
    _,annual=reporting.consolidated(db,now[:4],now)
    return {'pipeline_open':pipeline,'won':won,'lost':lost,
            'win_rate':str((Decimal(won)*100/Decimal(won+lost)).quantize(Decimal('0.1'))) if won+lost else None,
            'followup_missing':count("SELECT count(*) FROM opportunities WHERE status IN ('PROSPECT','QUALIFIE','PROPOSITION','NEGOCIATION') AND followup=''"),
            'active_missions':count("SELECT count(*) FROM missions WHERE status='ACTIVE' AND start_date<=? AND end_date>=?",(now,now)),
            'available_consultants':counts['consultants'].get('DISPONIBLE',0),
            'pending_cra':count("SELECT count(*) FROM activity WHERE status='SOUMIS' AND work_date<=?",(now,)),
            'urgent_by_kind':dict(sorted(urgent.items())), 'urgent_total':sum(urgent.values()),
            'last_notification_run':dict(latest) if latest else None,'cash_year':now[:4],'cash':annual}

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
    return {'counts':counts,'overdue':overdue,'financial':financial,'ambiguous_opportunities':conflicts,'as_of':today,'controlling':controlling.snapshot(db,today),'saas_finance':saas,'saas_profitability':profitability['groups'],'strategic':strategic_snapshot(db,date.fromisoformat(today),counts)}
