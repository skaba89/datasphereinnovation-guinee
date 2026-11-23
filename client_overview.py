"""Read-only 360° view of one organization (CRM permission), with sections filtered by role.

Requests, quotes, missions and invoices are included only when the caller's role may
already read those modules; no new data is exposed.
"""
import re
import sqlite3
from decimal import Decimal

import accounts
import crm_emails
import quotes

TIMELINE_LIMIT = 60
ORDER = ('DEMANDE', 'OPPORTUNITE', 'RENDEZ_VOUS', 'EMAIL', 'DEVIS', 'MISSION', 'FACTURE', 'PAIEMENT')


def _rows(db, sql, args=()):
    return [dict(r) for r in db.execute(sql, args)]


def overview(db, oid, can):
    db.row_factory = sqlite3.Row
    org = db.execute('SELECT id,name,kind,country,notes,version,created_at FROM organizations WHERE id=?', (oid,)).fetchone()
    if not org:
        return None
    result = {'organization': dict(org), 'sections': sorted(k for k, v in can.items() if v)}
    opps = _rows(db, '''SELECT o.id,o.title,o.status,o.mode,o.contact,o.email,o.followup,o.next_action,o.version
        FROM organization_links l JOIN opportunities o ON o.id=l.opportunity_id
        WHERE l.organization_id=? ORDER BY o.rowid DESC''', (oid,))
    ids = [o['id'] for o in opps]
    marks = ','.join('?' * len(ids)) or "''"
    result['opportunities'] = opps
    timeline = []
    for e in _rows(db, f'''SELECT e.id,e.created_at,e.status,o.title FROM opportunity_events e
            JOIN opportunities o ON o.id=e.opportunity_id WHERE e.opportunity_id IN ({marks})''', ids):
        timeline.append({'at': e['created_at'], 'kind': 'OPPORTUNITE', 'label': e['title'] + ' → ' + e['status'], 'seq': e['id']})
    appointments = _rows(db, f'''SELECT a.title,a.starts,a.status FROM appointments a
        WHERE a.opportunity_id IN ({marks}) ORDER BY a.starts DESC''', ids)
    result['appointments'] = appointments
    emails = crm_emails.history(db, ids)
    db.row_factory = sqlite3.Row
    result['emails'] = emails
    for m in emails:
        timeline.append({'at': m['created_at'], 'kind': 'EMAIL', 'label': 'E-mail préparé : ' + m['subject'] + ' (' + m['actor'] + ')'})
    for a in appointments:
        timeline.append({'at': a['starts'], 'kind': 'RENDEZ_VOUS', 'label': a['title'] + ' · ' + a['status']})
    if can['requests']:
        reqs = _rows(db, f'''SELECT DISTINCT r.id,r.created_at,r.nom,r.besoin,r.status FROM requests r
            LEFT JOIN request_leads l ON l.request_id=r.id LEFT JOIN request_opportunities c ON c.request_id=r.id
            WHERE l.opportunity_id IN ({marks}) OR c.opportunity_id IN ({marks}) ORDER BY r.created_at DESC''', ids + ids)
        result['requests'] = reqs
        for r in reqs:
            timeline.append({'at': r['created_at'], 'kind': 'DEMANDE', 'label': 'Demande web : ' + r['besoin'] + ' (' + r['nom'] + ')'})
    if can['quotes']:
        rows = _rows(db, f'SELECT * FROM quotes WHERE opportunity_id IN ({marks}) ORDER BY rowid DESC', ids)
        result['quotes'] = [{'id': q['id'], 'title': q['title'], 'status': q['status'], 'currency': q['currency'],
                             'mode': q['mode'], 'revenue': quotes.calculate(q)['revenue']} for q in rows]
        for e in _rows(db, f'''SELECT e.created_at,e.version,q.title FROM quote_events e JOIN quotes q ON q.id=e.quote_id
                WHERE q.opportunity_id IN ({marks})''', ids):
            timeline.append({'at': e['created_at'], 'kind': 'DEVIS', 'label': 'Devis ' + e['title'] + ' · version ' + str(e['version'])})
    missions = _rows(db, f'''SELECT id,contract_ref,start_date,end_date,status,created_at FROM missions
        WHERE opportunity_id IN ({marks}) ORDER BY start_date DESC''', ids) if (can['missions'] or can['billing']) else []
    if can['missions']:
        result['missions'] = [{k: m[k] for k in ('contract_ref', 'start_date', 'end_date', 'status')} for m in missions]
        for m in missions:
            timeline.append({'at': m['created_at'], 'kind': 'MISSION', 'label': 'Mission ' + m['contract_ref'] + ' créée'})
    if can['billing']:
        mids = [m['id'] for m in missions]
        mmarks = ','.join('?' * len(mids)) or "''"
        invoices = []
        totals = {}
        for i in _rows(db, f'''SELECT i.id,i.reference,i.amount,i.due_date,i.created_at,q.currency FROM invoices i
                JOIN missions m ON m.id=i.mission_id JOIN quotes q ON q.id=m.quote_id
                WHERE i.mission_id IN ({mmarks}) ORDER BY i.due_date DESC''', mids):
            payments = _rows(db, 'SELECT reference,amount,paid_date FROM payments WHERE invoice_id=?', (i['id'],))
            paid = sum((Decimal(p['amount']) for p in payments), Decimal(0))
            balance = Decimal(i['amount']) - paid
            invoices.append({'reference': i['reference'], 'amount': i['amount'], 'currency': i['currency'],
                             'due_date': i['due_date'], 'balance': str(balance)})
            t = totals.setdefault(i['currency'], {'invoiced': Decimal(0), 'balance': Decimal(0)})
            t['invoiced'] += Decimal(i['amount'])
            t['balance'] += balance
            timeline.append({'at': i['created_at'], 'kind': 'FACTURE', 'label': 'Facture ' + i['reference'] + ' · ' + i['amount'] + ' ' + i['currency']})
            for p in payments:
                timeline.append({'at': p['paid_date'], 'kind': 'PAIEMENT', 'label': 'Encaissement ' + p['reference'] + ' · ' + p['amount'] + ' ' + i['currency']})
        result['invoices'] = invoices
        result['billing_totals'] = {c: {k: str(v) for k, v in t.items()} for c, t in totals.items()}
    # Same-second events follow the business order (request, then CRM, then delivery and cash).
    timeline.sort(key=lambda x: (x['at'] or '', ORDER.index(x['kind']), x.pop('seq', 0)), reverse=True)
    result['timeline'] = timeline[:TIMELINE_LIMIT]
    return result


def handle(h, connect, oid):
    if not h.admin_authorized():
        return
    if not re.fullmatch(r'[0-9a-f-]{36}', oid):
        return h.json_response(404, {'error': 'Organisation introuvable.'})
    can = {r: accounts.allowed(h.role, r, 'GET') for r in ('requests', 'quotes', 'missions', 'billing')}
    with connect() as db:
        data = overview(db, oid, can)
    if data is None:
        return h.json_response(404, {'error': 'Organisation introuvable.'})
    return h.json_response(200, data)
