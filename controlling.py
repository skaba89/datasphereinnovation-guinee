"""Lifetime mission control: approved activity, budgets and receivables by currency."""
from collections import defaultdict
from decimal import Decimal
import missions
import quotes

KEYS=('budget_revenue','budget_cost','budget_margin','validated_revenue','validated_cost','validated_margin','cost_remaining','revenue_gap','invoiced','received','receivable','overdue','unbilled')

def sums():return {k:Decimal(0) for k in KEYS}

def stringify(values):return {k:str(v) if isinstance(v,Decimal) else v for k,v in values.items()}

def snapshot(db,today):
    totals=defaultdict(sums); clients=defaultdict(sums); rows=[]
    # A mission is tied to exactly one accepted quote, even if another quote exists.
    for row in db.execute('''SELECT q.*,m.id AS mission_id,m.status AS mission_status,o.company,
        coalesce(g.name,o.company) AS client_name,coalesce(l.organization_id,'') AS organization_id
        FROM missions m JOIN quotes q ON q.id=m.quote_id JOIN opportunities o ON o.id=m.opportunity_id
        LEFT JOIN organization_links l ON l.opportunity_id=o.id LEFT JOIN organizations g ON g.id=l.organization_id
        ORDER BY m.created_at DESC,m.id'''):
        m=dict(row);mid=m['mission_id'];budget=quotes.calculate(m)
        actual=missions.amounts(m,[dict(a) for a in db.execute('SELECT * FROM activity WHERE mission_id=?',(mid,))])
        revenue=Decimal(actual['billable_revenue']) if m['mode']=='REGIE' else sum((Decimal(x[0]) for x in db.execute("SELECT amount FROM milestones WHERE mission_id=? AND status='VALIDE'",(mid,))),Decimal(0))
        cost=Decimal(actual['actual_cost']);br=Decimal(budget['revenue']);bc=Decimal(budget['direct_cost'])
        billed=received=late=Decimal(0)
        for invoice in db.execute('SELECT id,amount,due_date FROM invoices WHERE mission_id=?',(mid,)):
            amount=Decimal(invoice['amount']);paid=sum((Decimal(x[0]) for x in db.execute('SELECT amount FROM payments WHERE invoice_id=?',(invoice['id'],))),Decimal(0))
            billed+=amount;received+=paid
            if invoice['due_date']<today:late+=amount-paid
        values=dict(budget_revenue=br,budget_cost=bc,budget_margin=br-bc,validated_revenue=revenue,validated_cost=cost,validated_margin=revenue-cost,cost_remaining=bc-cost,revenue_gap=revenue-br,invoiced=billed,received=received,receivable=billed-received,overdue=late,unbilled=revenue-billed)
        currency=m['currency'];client_key=('organization',m['organization_id']) if m['organization_id'] else ('legacy',m['company'])
        group=(currency,*client_key,m['client_name'])
        for key,value in values.items():totals[currency][key]+=value;clients[group][key]+=value
        rows.append({'mission_id':mid,'client':m['client_name'],'organization_id':m['organization_id'],'title':m['title'],'currency':currency,'mode':m['mode'],'status':m['mission_status'],**stringify(values)})
    return {'missions':rows,'currencies':[{'currency':c,**stringify(v)} for c,v in sorted(totals.items())], 'clients':[{'currency':g[0],'organization_id':g[2] if g[1]=='organization' else '', 'client':g[3],**stringify(v)} for g,v in sorted(clients.items())]}
