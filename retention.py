"""Retention and erasure of contact-request personal data (V172).

- Automatic purge: requests that never became a commercial relationship (no CRM qualification)
  and with no activity for DSIG_REQUEST_RETENTION_DAYS (default 1095 days, i.e. 3 years — to be
  confirmed by the legal review, see legal field `email_retention`) are anonymized.
- Erasure on request: ADMIN can anonymize one request immediately (right to erasure).

Anonymization keeps the non-personal facts used by statistics (id, date, type of need, status)
and removes names, organisation, email, message and free-text notes, plus the copies held in the
auto-created CRM prospect while it is still an unworked prospect. Every action is audited
without personal data. Dry-run by default on the command line.
"""
import os
import re
from datetime import date, timedelta

import accounts

ERASED = '[supprimé]'
DEFAULT_DAYS = 1095
OPEN_LEAD = ('PROSPECT',)


def retention_days():
    raw = os.environ.get('DSIG_REQUEST_RETENTION_DAYS', str(DEFAULT_DAYS))
    if not raw.isdigit() or not 30 <= int(raw) <= 3650:
        raise ValueError('DSIG_REQUEST_RETENTION_DAYS must be between 30 and 3650')
    return int(raw)


def candidates(db, today, days):
    """Requests eligible for automatic anonymization (not qualified into the CRM, inactive)."""
    limit = (today - timedelta(days=days)).isoformat()
    return [r[0] for r in db.execute(f'''SELECT r.id FROM requests r
        WHERE r.email<>'' AND NOT EXISTS(SELECT 1 FROM request_opportunities o WHERE o.request_id=r.id)
          AND date(max(r.created_at,
              COALESCE((SELECT max(e.created_at) FROM request_events e WHERE e.request_id=r.id),''),
              COALESCE((SELECT max(w.created_at) FROM request_workflow_events w WHERE w.request_id=r.id),'')))<?
        ORDER BY r.created_at''', (limit,))]


def anonymize(db, rid, actor, reason):
    """Remove personal data of one request. Returns False if already anonymized or absent."""
    if not db.execute("SELECT 1 FROM requests WHERE id=? AND email<>''", (rid,)).fetchone():
        return False
    db.execute("UPDATE requests SET nom=?,org=?,email='',message=?,solution='' WHERE id=?", (ERASED, ERASED, ERASED, rid))
    db.execute("UPDATE request_workflow_events SET note=? WHERE request_id=? AND note<>''", (ERASED, rid))
    db.execute('DELETE FROM contact_mail_recipient WHERE request_id=?', (rid,))
    db.execute("UPDATE contact_mail SET state='FAILED' WHERE request_id=? AND state='PENDING'", (rid,))
    # Auto-created prospect still untouched: drop the copied contact details too.
    for (oid,) in db.execute(f'''SELECT l.opportunity_id FROM request_leads l JOIN opportunities o ON o.id=l.opportunity_id
            WHERE l.request_id=? AND l.outcome='CREATED' AND o.status IN ({','.join('?' * len(OPEN_LEAD))})''',
                             (rid, *OPEN_LEAD)).fetchall():
        db.execute("UPDATE opportunities SET contact='',email='',notes='' WHERE id=?", (oid,))
    accounts.event(db, actor, 'DEMANDE_ANONYMISEE', f'{rid} ({reason})')
    return True


def purge(db, today=None, apply=False, days=None):
    """Anonymize eligible requests. Dry run unless apply=True. Returns a count summary."""
    days = days or retention_days()
    ids = candidates(db, today or date.today(), days)
    done = 0
    if apply:
        for rid in ids:
            done += anonymize(db, rid, 'SYSTEME:conservation', f'inactivité > {days} j')
    return {'retention_days': days, 'eligible': len(ids), 'anonymized': done, 'applied': apply}


def handle_erasure(h, connect, rid):
    """DELETE /api/admin/requests/<id>/personal-data — ADMIN only, immediate anonymization."""
    if not h.admin_authorized():
        return
    if h.role != 'ADMIN':
        return h.json_response(403, {'error': 'Suppression réservée aux administrateurs.'})
    if not re.fullmatch(r'[0-9a-f-]{36}', rid):
        return h.json_response(404, {'error': 'Demande introuvable.'})
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM requests WHERE id=?', (rid,)).fetchone():
            return h.json_response(404, {'error': 'Demande introuvable.'})
        done = anonymize(db, rid, h.actor, 'demande de suppression')
    return h.json_response(200, {'status': 'ANONYMISEE' if done else 'DEJA_ANONYMISEE'})
