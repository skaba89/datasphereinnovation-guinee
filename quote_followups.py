"""One automatic, polite follow-up email per transmitted quote version (REC queue).

Conditions: quote still PROPOSE, transmitted at least DELAY_DAYS ago, still valid,
opportunity still open, linked to a web request that already received an
acknowledgement. The email goes through the existing contact_mail queue, so REC
recipient rules apply (test mailbox or explicitly allowed test addresses only).
"""
import time
from datetime import timedelta
from html import escape

import accounts

DELAY_DAYS = 7
ACTOR = 'SYSTEME:relances'
OPEN = ('PROSPECT', 'QUALIFIE', 'PROPOSITION', 'NEGOCIATION')


def kind(quote_id, version):
    return f'followup-{quote_id}-v{version}'


def schedule(db, today):
    """Queue missing follow-ups; idempotent. Returns the number queued."""
    limit = (today - timedelta(days=DELAY_DAYS)).isoformat()
    rows = db.execute(f'''SELECT q.id,q.version,q.title,
            (SELECT r.id FROM requests r
              WHERE r.besoin<>'Candidature spontanée' AND r.id IN (
                SELECT request_id FROM request_opportunities WHERE opportunity_id=q.opportunity_id
                UNION SELECT request_id FROM request_leads WHERE opportunity_id=q.opportunity_id)
              ORDER BY r.created_at DESC LIMIT 1) AS rid
        FROM quotes q
        JOIN quote_transmissions t ON t.quote_id=q.id AND t.version=q.version
        JOIN opportunities o ON o.id=q.opportunity_id
        LEFT JOIN quote_proposal_terms p ON p.quote_id=q.id
        WHERE q.status='PROPOSE' AND date(t.created_at)<=?
          AND (p.valid_until IS NULL OR p.valid_until='' OR p.valid_until>=?)
          AND o.status IN ({','.join('?' * len(OPEN))})''', (limit, today.isoformat(), *OPEN)).fetchall()
    queued = 0
    now = time.time()
    for qid, version, title, rid in rows:
        if not rid:
            continue
        ack = db.execute("SELECT language FROM contact_mail WHERE request_id=? AND kind='ack'", (rid,)).fetchone()
        if not ack:
            continue
        added = db.execute('INSERT OR IGNORE INTO contact_mail(request_id,kind,language,created,next_attempt) VALUES (?,?,?,?,?)',
                           (rid, kind(qid, version), ack[0], now, now)).rowcount
        if not added:
            continue
        queued += 1
        accounts.event(db, ACTOR, 'RELANCE_DEVIS_PLANIFIEE', qid)
        workflow = db.execute('SELECT owner_id,priority,due_date FROM request_workflow WHERE request_id=?', (rid,)).fetchone()
        if workflow:
            db.execute('''INSERT INTO request_workflow_events(request_id,actor,owner_id,priority,due_date,note)
                VALUES (?,?,?,?,?,?)''', (rid, ACTOR, *workflow, f'Relance automatique planifiée : devis « {title} » (version {version}) sans décision depuis {DELAY_DAYS} jours'))
    return queued


def render(reference, language):
    en = language == 'en'
    if en:
        subject = '[REC TEST] DSIG — Following up on our proposal'
        lines = ['Hello,', '',
                 'We are following up on the proposal we sent you. Do you have any questions, or would you like to adjust the scope or schedule?',
                 'Simply reply to this email and your contact will get back to you.', '',
                 f'Reference: {reference}', '',
                 'If you would rather not receive further follow-ups about this proposal, just let us know in your reply.',
                 'DataSphere Innovation Guinée | DSIG Consulting', 'TEST — no commercial commitment.']
    else:
        subject = '[REC TEST] DSIG — Suivi de notre proposition'
        lines = ['Bonjour,', '',
                 'Nous revenons vers vous au sujet de la proposition que nous vous avons transmise. Avez-vous des questions, ou souhaitez-vous ajuster le périmètre ou le calendrier ?',
                 'Il vous suffit de répondre à cet e-mail : votre interlocuteur reviendra vers vous.', '',
                 f'Référence : {reference}', '',
                 'Si vous ne souhaitez plus être relancé au sujet de cette proposition, indiquez-le simplement en réponse.',
                 'DataSphere Innovation Guinée | DSIG Consulting', 'RECETTE — aucun engagement commercial.']
    plain = '\n'.join(lines)
    markup = (f'<html lang="{language}"><body style="font-family:Arial,sans-serif;color:#201038">'
              '<div style="background:#35104e;color:white;padding:20px;font-size:22px">DSIG | Consulting</div>'
              + ''.join(f'<p>{escape(line)}</p>' for line in lines if line) + '</body></html>')
    return subject, plain, markup
