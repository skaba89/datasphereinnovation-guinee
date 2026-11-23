"""Billing automation (REC): internal "to invoice" reminders and automatic dunning emails.

- ECHEANCE_A_FACTURER: planned schedule line (PREVU, not reconciled) due within 7 days or late.
- JALON_A_FACTURER: fixed-price mission whose validated milestones exceed what was invoiced.
- Dunning: at most two polite emails per overdue invoice (J+7, then J+21 and 14 days after the
  first), only for missions coming from a web request that already received an acknowledgement,
  never if a manual reminder was logged in the last 7 days. Emails go through the contact_mail
  queue, so REC recipient rules apply. No amount in the email: reference and due date only.
"""
import time
from datetime import date, timedelta
from decimal import Decimal
from html import escape

import accounts

ACTOR = 'SYSTEME:recouvrement'
LEVELS = ((1, 7), (2, 21))  # (level, minimum days overdue)
GAP_DAYS = 14               # minimum spacing between two automatic emails
MANUAL_QUIET_DAYS = 7
AUTO_NOTE = 'Relance automatique n°'


def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS billing_dunning (
        kind TEXT PRIMARY KEY, invoice_id TEXT NOT NULL, request_id TEXT NOT NULL,
        level INTEGER NOT NULL, reference TEXT NOT NULL, due_date TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')


def kind(invoice_id, level):
    return f'dunning-{invoice_id}-n{level}'


def _balance(db, invoice_id, amount):
    paid = sum((Decimal(r[0]) for r in db.execute('SELECT amount FROM payments WHERE invoice_id=?', (invoice_id,))), Decimal(0))
    return Decimal(amount) - paid


def reminders(db, today):
    """Internal notification items (no customer contact data)."""
    now, horizon = today.isoformat(), (today + timedelta(days=7)).isoformat()
    items = []
    for sid, label, amount, due, currency, contract in db.execute('''SELECT s.id,s.label,s.amount,s.due_date,q.currency,m.contract_ref
            FROM billing_schedule s JOIN missions m ON m.id=s.mission_id JOIN quotes q ON q.id=m.quote_id
            WHERE s.state='PREVU' AND s.invoice_id IS NULL AND s.due_date<=?''', (horizon,)):
        items.append(dict(kind='ECHEANCE_A_FACTURER', id=sid, due=due, priority='URGENT' if due < now else 'A_TRAITER',
                          label=f'{contract} · {label}', details=f'{amount} {currency} à facturer'))
    for mid, contract, currency, validated, last in db.execute('''SELECT m.id,m.contract_ref,q.currency,
            (SELECT group_concat(j.amount,'|') FROM milestones j WHERE j.mission_id=m.id AND j.status='VALIDE'),
            (SELECT max(date(e.created_at)) FROM billing_events e JOIN milestones j ON j.id=e.entity_id
               WHERE j.mission_id=m.id AND e.event='JALON_VALIDE')
            FROM missions m JOIN quotes q ON q.id=m.quote_id WHERE q.mode='FORFAIT' '''):
        if not validated:
            continue
        invoiced = sum((Decimal(r[0]) for r in db.execute('SELECT amount FROM invoices WHERE mission_id=?', (mid,))), Decimal(0))
        remaining = sum((Decimal(x) for x in validated.split('|')), Decimal(0)) - invoiced
        if remaining > 0:
            # Stable key: the last validation date, so a new notification appears only after a new validation.
            items.append(dict(kind='JALON_A_FACTURER', id=mid, due=last or now, priority='A_TRAITER',
                              label=contract, details=f'{remaining} {currency} validés non facturés'))
    return items


def _request_for(db, opportunity_id):
    row = db.execute('''SELECT r.id FROM requests r WHERE r.besoin<>'Candidature spontanée' AND r.id IN (
            SELECT request_id FROM request_opportunities WHERE opportunity_id=?
            UNION SELECT request_id FROM request_leads WHERE opportunity_id=?)
        ORDER BY r.created_at DESC LIMIT 1''', (opportunity_id, opportunity_id)).fetchone()
    return row[0] if row else None


def schedule(db, today):
    """Queue at most one missing dunning email per overdue invoice; idempotent. Returns the count."""
    schema(db)
    queued, now = 0, time.time()
    quiet = (today - timedelta(days=MANUAL_QUIET_DAYS)).isoformat()
    for iid, reference, amount, due, opportunity in db.execute('''SELECT i.id,i.reference,i.amount,i.due_date,m.opportunity_id
            FROM invoices i JOIN missions m ON m.id=i.mission_id WHERE i.due_date<? ORDER BY i.due_date,i.id''',
                                                               (today.isoformat(),)).fetchall():
        if _balance(db, iid, amount) <= 0:
            continue
        if db.execute("SELECT 1 FROM billing_reminders WHERE invoice_id=? AND date(created_at)>=? AND note NOT LIKE ?",
                      (iid, quiet, AUTO_NOTE + '%')).fetchone():
            continue
        late = (today - date.fromisoformat(due)).days
        done = dict(db.execute('SELECT level,created FROM contact_mail c JOIN billing_dunning d ON d.kind=c.kind WHERE d.invoice_id=?', (iid,)).fetchall())
        level = next((lvl for lvl, days in LEVELS if lvl not in done and late >= days), None)
        if level is None or (level > 1 and (level - 1 not in done or now - done[level - 1] < GAP_DAYS * 86400)):
            continue
        rid = _request_for(db, opportunity)
        if not rid:
            continue
        ack = db.execute("SELECT language FROM contact_mail WHERE request_id=? AND kind='ack'", (rid,)).fetchone()
        if not ack:
            continue
        mail_kind = kind(iid, level)
        if not db.execute('INSERT OR IGNORE INTO contact_mail(request_id,kind,language,created,next_attempt) VALUES (?,?,?,?,?)',
                          (rid, mail_kind, ack[0], now, now)).rowcount:
            continue
        db.execute('INSERT INTO billing_dunning(kind,invoice_id,request_id,level,reference,due_date) VALUES (?,?,?,?,?,?)',
                   (mail_kind, iid, rid, level, reference, due))
        db.execute("INSERT INTO billing_reminders(id,invoice_id,channel,note) VALUES (?,?,'EMAIL',?)",
                   (mail_kind, iid, f'{AUTO_NOTE}{level} planifiée (file e-mail REC)'))
        accounts.event(db, ACTOR, 'RELANCE_FACTURE_PLANIFIEE', iid)
        queued += 1
    return queued


def details(db, mail_kind):
    row = db.execute('SELECT reference,due_date,level FROM billing_dunning WHERE kind=?', (mail_kind,)).fetchone()
    return tuple(row) if row else None


def render(reference, language, invoice_reference, due_date, level):
    en = language == 'en'
    if en:
        subject = '[REC TEST] DSIG — Payment reminder' + (' (second notice)' if level > 1 else '')
        lines = ['Hello,', '',
                 f'According to our records, invoice {invoice_reference} (due on {due_date}) has not been fully settled yet.',
                 'If the payment has already been made, please disregard this message, and thank you.',
                 'Otherwise, simply reply to this email with the expected payment date or any question.', '',
                 f'Reference: {reference}',
                 'DataSphere Innovation Guinée | DSIG Consulting', 'TEST — no real invoice.']
    else:
        subject = '[REC TEST] DSIG — Rappel de règlement' + (' (second rappel)' if level > 1 else '')
        lines = ['Bonjour,', '',
                 f'Sauf erreur de notre part, la facture {invoice_reference} (échéance du {due_date}) n’est pas encore entièrement réglée.',
                 'Si le règlement a déjà été effectué, merci de ne pas tenir compte de ce message.',
                 'Dans le cas contraire, il vous suffit de répondre à cet e-mail en indiquant la date de règlement prévue ou vos questions.', '',
                 f'Référence : {reference}',
                 'DataSphere Innovation Guinée | DSIG Consulting', 'RECETTE — aucune facture réelle.']
    plain = '\n'.join(lines)
    markup = (f'<html lang="{"en" if en else "fr"}"><body style="font-family:Arial,sans-serif;color:#201038">'
              '<div style="background:#35104e;color:white;padding:20px;font-size:22px">DSIG | Consulting</div>'
              + ''.join(f'<p>{escape(line)}</p>' for line in lines if line) + '</body></html>')
    return subject, plain, markup
