"""Weekly management report (internal email), computed from the REC database.

Aggregates only, plus company/title of overdue follow-ups: no contact names, emails
or message contents. One send per ISO week (idempotent), via the existing Resend config.
"""
import html
import json
import re
import urllib.request
from datetime import date, timedelta
from decimal import Decimal

import contact_mail

STAGES = (('PROSPECT', 'Prospect'), ('QUALIFIE', 'Qualifié'), ('PROPOSITION', 'Proposition'),
          ('NEGOCIATION', 'Négociation'), ('GAGNE', 'Gagné'), ('EN_MISSION', 'En mission'),
          ('TERMINE', 'Terminé'), ('PERDU', 'Perdu'))
OPEN = ('PROSPECT', 'QUALIFIE', 'PROPOSITION', 'NEGOCIATION')
ADDRESS = r'[A-Za-z0-9.!+_-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'


def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS weekly_reports (
        week TEXT PRIMARY KEY, state TEXT NOT NULL, provider_id TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')


def week_of(today):
    year, week, _ = today.isocalendar()
    return f'{year}-W{week:02d}'


def compute(db, today):
    start, end = (today - timedelta(days=7)).isoformat(), today.isoformat()
    one = lambda sql, args=(): db.execute(sql, args).fetchone()[0] or 0
    period = (start, end)
    report = {'week': week_of(today), 'start': start, 'end': end}
    report['requests'] = one("SELECT count(*) FROM requests WHERE date(created_at)>=? AND date(created_at)<?", period)
    report['requests_by_need'] = db.execute("""SELECT besoin,count(*) FROM requests WHERE date(created_at)>=? AND date(created_at)<?
        GROUP BY besoin ORDER BY count(*) DESC,besoin""", period).fetchall()
    report['auto_leads'] = one("SELECT count(*) FROM request_leads WHERE outcome='CREATED' AND date(created_at)>=? AND date(created_at)<?", period)
    report['duplicates'] = one("SELECT count(*) FROM request_leads WHERE outcome='DUPLICATE' AND date(created_at)>=? AND date(created_at)<?", period)
    report['qualified'] = one("SELECT count(*) FROM request_opportunities WHERE date(created_at)>=? AND date(created_at)<?", period)
    report['pipeline'] = dict(db.execute('SELECT status,count(*) FROM opportunities GROUP BY status').fetchall())
    report['won'] = one("""SELECT count(DISTINCT opportunity_id) FROM opportunity_events
        WHERE status='GAGNE' AND date(created_at)>=? AND date(created_at)<?""", period)
    report['lost'] = one("""SELECT count(DISTINCT opportunity_id) FROM opportunity_events
        WHERE status='PERDU' AND date(created_at)>=? AND date(created_at)<?""", period)
    report['quotes_sent'] = one("SELECT count(*) FROM quote_transmissions WHERE date(created_at)>=? AND date(created_at)<?", period)
    report['untreated_48h'] = one("""SELECT count(*) FROM requests r WHERE r.status='NOUVELLE'
        AND datetime(r.created_at,'+2 days')<=datetime(?) AND NOT EXISTS(SELECT 1 FROM request_events e WHERE e.request_id=r.id)""", (end,))
    report['overdue_followups'] = [list(r) for r in db.execute(f"""SELECT company,title,followup FROM opportunities
        WHERE status IN ({','.join('?' * len(OPEN))}) AND followup<>'' AND followup<? ORDER BY followup LIMIT 10""", (*OPEN, end))]
    report['overdue_followups_total'] = one(f"""SELECT count(*) FROM opportunities WHERE status IN ({','.join('?' * len(OPEN))})
        AND followup<>'' AND followup<?""", (*OPEN, end))
    receivables = {}
    for iid, amount, currency in db.execute('''SELECT i.id,i.amount,q.currency FROM invoices i JOIN missions m ON m.id=i.mission_id
            JOIN quotes q ON q.id=m.quote_id WHERE i.due_date<?''', (end,)):
        paid = sum((Decimal(p[0]) for p in db.execute('SELECT amount FROM payments WHERE invoice_id=?', (iid,))), Decimal(0))
        balance = Decimal(amount) - paid
        if balance > 0:
            receivables[currency] = receivables.get(currency, Decimal(0)) + balance
    report['overdue_receivables'] = {c: str(v) for c, v in sorted(receivables.items())}
    return report


def render(r):
    open_total = sum(r['pipeline'].get(k, 0) for k in OPEN)
    lines = [
        f"Rapport hebdomadaire DSIG — semaine {r['week']} ({r['start']} → {r['end']}, fin exclue)", '',
        'ACTIVITÉ COMMERCIALE',
        f"- Demandes reçues : {r['requests']}" + (' (' + ', '.join(f'{n} {k}' for k, n in r['requests_by_need']) + ')' if r['requests_by_need'] else ''),
        f"- Prospects CRM créés automatiquement : {r['auto_leads']} (rattachés à un prospect existant : {r['duplicates']})",
        f"- Demandes qualifiées en opportunité : {r['qualified']}",
        f"- Devis transmis : {r['quotes_sent']}",
        f"- Opportunités gagnées : {r['won']} · perdues : {r['lost']}", '',
        f'PIPELINE ACTUEL ({open_total} ouvertes)',
        *[f'- {label} : {r["pipeline"].get(key, 0)}' for key, label in STAGES], '',
        'POINTS D’ATTENTION',
        f"- Demandes sans traitement depuis plus de 48 h : {r['untreated_48h']}",
        f"- Relances commerciales en retard : {r['overdue_followups_total']}",
        *[f'  · {company} — {title} (relance prévue le {day})' for company, title, day in r['overdue_followups']],
        '- Créances échues non encaissées : ' + (', '.join(f'{v} {c}' for c, v in r['overdue_receivables'].items()) or 'aucune'),
        '', 'Indicateurs opérationnels calculés sur la base de recette ; ils ne constituent pas un état comptable.',
    ]
    text = '\n'.join(lines)
    subject = f"[DSIG] Rapport hebdomadaire {r['week']}"
    body = '<pre style="font-family:Arial,sans-serif;white-space:pre-wrap">' + html.escape(text) + '</pre>'
    return subject, text, body


def recipients(cfg):
    extra = cfg.get('report_recipients', [])
    if not isinstance(extra, list) or len(extra) > 10 or not all(isinstance(x, str) and re.fullmatch(ADDRESS, x) for x in extra):
        raise ValueError('Invalid report recipients')
    return extra or [cfg['test_recipient']]


def deliver(cfg, week, subject, text, body):
    message = {'from': cfg['sender'], 'to': recipients(cfg), 'subject': subject, 'text': text, 'html': body}
    req = urllib.request.Request('https://api.resend.com/emails', data=json.dumps(message).encode(),
        headers={'Authorization': 'Bearer ' + cfg['api_key'], 'Content-Type': 'application/json', 'User-Agent': 'DSIG-REC/1.0',
                 'Idempotency-Key': 'dsig-rec/weekly-report/' + week}, method='POST')
    with urllib.request.build_opener(contact_mail.NoRedirect).open(req, timeout=15) as response:
        identifier = json.loads(response.read(4096))['id']
    if not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9-]{1,100}', identifier):
        raise ValueError('Invalid provider response')
    return identifier


def send(connect, raw_cfg, today=None, deliver=deliver):
    """Send at most one report per ISO week. Returns 'SENT' or 'ALREADY_SENT'."""
    cfg = contact_mail.config({k: v for k, v in raw_cfg.items() if k != 'report_recipients'}) | (
        {'report_recipients': raw_cfg['report_recipients']} if 'report_recipients' in raw_cfg else {})
    recipients(cfg)
    today = today or date.today()
    week = week_of(today)
    with connect() as db:
        schema(db)
        if db.execute("SELECT 1 FROM weekly_reports WHERE week=? AND state='ACCEPTED'", (week,)).fetchone():
            return 'ALREADY_SENT'
        subject, text, body = render(compute(db, today))
    identifier = deliver(cfg, week, subject, text, body)
    with connect() as db:
        db.execute("""INSERT INTO weekly_reports(week,state,provider_id) VALUES (?,'ACCEPTED',?)
            ON CONFLICT(week) DO UPDATE SET state='ACCEPTED',provider_id=excluded.provider_id""", (week, identifier))
    return 'SENT'
