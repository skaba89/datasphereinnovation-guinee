"""Lifetime mission control: approved activity, budgets and receivables by currency."""
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
import missions
import quotes
import treasury

KEYS=('budget_revenue','budget_cost','budget_margin','validated_revenue','validated_cost','validated_margin','cost_remaining','revenue_gap','invoiced','received','receivable','overdue','unbilled','margin_gap','allocated_outflows','allocated_cash_flow')

def sums():return {k:Decimal(0) for k in KEYS}

def ratio(numerator,denominator):
    if numerator is None or denominator is None or Decimal(denominator)==0:return None
    return str((Decimal(numerator)*100/Decimal(denominator)).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP))

def indicators(values):
    return dict(margin_rate=ratio(values['validated_margin'],values['validated_revenue']),
                budget_cost_used_rate=ratio(values['validated_cost'],values['budget_cost']),
                collection_rate=ratio(values['received'],values['invoiced']))

def stringify(values):return {k:str(v) if isinstance(v,Decimal) else v for k,v in values.items()}

def snapshot(db,today):
    totals=defaultdict(sums); clients=defaultdict(sums); contracts=defaultdict(sums); rows=[]; consultant_rows=[]
    # A mission is tied to exactly one accepted quote, even if another quote exists.
    for row in db.execute('''SELECT q.*,m.id AS mission_id,m.contract_ref,m.status AS mission_status,o.company,
        coalesce(g.name,o.company) AS client_name,coalesce(l.organization_id,'') AS organization_id
        FROM missions m JOIN quotes q ON q.id=m.quote_id JOIN opportunities o ON o.id=m.opportunity_id
        LEFT JOIN organization_links l ON l.opportunity_id=o.id LEFT JOIN organizations g ON g.id=l.organization_id
        ORDER BY m.created_at DESC,m.id'''):
        m=dict(row);mid=m['mission_id'];budget=quotes.calculate(m)
        entries=[dict(a) for a in db.execute('SELECT * FROM activity WHERE mission_id=?',(mid,))]
        actual=missions.amounts(m,entries)
        for c in db.execute('SELECT id,name FROM consultants WHERE id IN (SELECT consultant_id FROM missions WHERE id=? UNION SELECT consultant_id FROM mission_members WHERE mission_id=?) ORDER BY name,id',(mid,mid)):
            individual=missions.amounts(m,[a for a in entries if a['consultant_id']==c['id']])
            consultant_rows.append({'consultant_id':c['id'],'consultant':c['name'],'mission_id':mid,'title':m['title'],'currency':m['currency'],'mode':m['mode'],'worked':individual['worked'],'billable':individual['billable'],'cost':individual['actual_cost'],'revenue':individual['billable_revenue'],'margin':individual['actual_margin'],'billable_rate':ratio(individual['billable'],individual['worked']) if m['mode']=='REGIE' else None,'margin_rate':ratio(individual['actual_margin'],individual['billable_revenue'])})
        revenue=Decimal(actual['billable_revenue']) if m['mode']=='REGIE' else sum((Decimal(x[0]) for x in db.execute("SELECT amount FROM milestones WHERE mission_id=? AND status='VALIDE'",(mid,))),Decimal(0))
        cost=Decimal(actual['actual_cost']);br=Decimal(budget['revenue']);bc=Decimal(budget['direct_cost'])
        billed=received=late=Decimal(0)
        for invoice in db.execute('SELECT id,amount,due_date FROM invoices WHERE mission_id=?',(mid,)):
            amount=Decimal(invoice['amount']);paid=sum((Decimal(x[0]) for x in db.execute('SELECT amount FROM payments WHERE invoice_id=?',(invoice['id'],))),Decimal(0))
            billed+=amount;received+=paid
            if invoice['due_date']<today:late+=amount-paid
        outflows=sum((Decimal(x[0]) for x in db.execute('SELECT amount FROM expenses WHERE mission_id=? AND currency=?',(mid,m['currency']))),Decimal(0))
        values=dict(budget_revenue=br,budget_cost=bc,budget_margin=br-bc,validated_revenue=revenue,validated_cost=cost,validated_margin=revenue-cost,cost_remaining=bc-cost,revenue_gap=revenue-br,invoiced=billed,received=received,receivable=billed-received,overdue=late,unbilled=revenue-billed,margin_gap=(revenue-cost)-(br-bc),allocated_outflows=outflows,allocated_cash_flow=received-outflows)
        currency=m['currency'];client_key=('organization',m['organization_id']) if m['organization_id'] else ('legacy',m['company'])
        group=(currency,*client_key,m['client_name'])
        contract_group=(*group,m['contract_ref'])
        for key,value in values.items():totals[currency][key]+=value;clients[group][key]+=value;contracts[contract_group][key]+=value
        rows.append({'mission_id':mid,'client':m['client_name'],'organization_id':m['organization_id'],'title':m['title'],'contract_ref':m['contract_ref'],'currency':currency,'mode':m['mode'],'status':m['mission_status'],**stringify(values),**indicators(values)})
    return {'missions':rows,'currencies':[{'currency':c,**stringify(v),**indicators(v)} for c,v in sorted(totals.items())], 'clients':[{'currency':g[0],'organization_id':g[2] if g[1]=='organization' else '', 'client':g[3],**stringify(v),**indicators(v)} for g,v in sorted(clients.items())],'contracts':[{'currency':g[0],'organization_id':g[2] if g[1]=='organization' else '', 'client':g[3],'contract_ref':g[4],**stringify(v),**indicators(v)} for g,v in sorted(contracts.items())],'consultants':consultant_rows,'cash':treasury.cash(db)}
