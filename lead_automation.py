"""Automatic CRM lead for every commercial web request (same transaction as the intake).

- Creates a PROSPECT opportunity with a 48 h follow-up, or links the request to an open
  opportunity of the same email (no duplicate).
- Assigns the request to the enabled COMMERCIAL account with the lightest open workload.
- Qualification stays human: request_conversion promotes the automatic lead to QUALIFIE.
Spontaneous applications never reach the CRM.
"""
import datetime
import uuid

import accounts
import crm

ACTOR = 'SYSTEME:site-web'
SLA_DAYS = 2
OPEN = ('PROSPECT', 'QUALIFIE', 'PROPOSITION', 'NEGOCIATION')
MODES = {'Mission en régie': 'REGIE', 'Projet au forfait': 'FORFAIT'}


def schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS request_leads (
        request_id TEXT PRIMARY KEY REFERENCES requests(id),
        opportunity_id TEXT NOT NULL REFERENCES opportunities(id),
        outcome TEXT NOT NULL CHECK (outcome IN ('CREATED','DUPLICATE')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")


def title(need, solution):
    return (need + (' — ' + solution if solution else ''))[:180]


def mode(need):
    return MODES.get(need, 'CONSEIL')


def read(db, rid):
    row = db.execute("""SELECT l.opportunity_id,l.outcome,o.title,o.status FROM request_leads l
        JOIN opportunities o ON o.id=l.opportunity_id WHERE l.request_id=?""", (rid,)).fetchone()
    return dict(zip(('opportunity_id', 'outcome', 'title', 'status'), row)) if row else None


def _owner(db):
    row = db.execute("""SELECT a.id FROM accounts a WHERE a.enabled=1 AND a.role='COMMERCIAL'
        ORDER BY (SELECT count(*) FROM request_workflow w JOIN requests r ON r.id=w.request_id
                  WHERE w.owner_id=a.id AND r.status NOT IN ('GAGNEE','PERDUE')), a.username LIMIT 1""").fetchone()
    return row[0] if row else ''


def on_request(db, rid, values, today=None):
    """Run inside the intake transaction. Returns the lead or None for applications."""
    if values['besoin'] == 'Candidature spontanée':
        return None
    today = today or datetime.date.today()
    due = (today + datetime.timedelta(days=SLA_DAYS)).isoformat()
    email = values['email'].strip().casefold()
    existing = db.execute("SELECT id FROM opportunities WHERE lower(trim(email))=? AND status IN (?,?,?,?) "
                          "ORDER BY rowid DESC LIMIT 1", (email, *OPEN)).fetchone()
    if existing:
        oid, outcome = existing[0], 'DUPLICATE'
    else:
        fields = crm.validate(dict(company=values['org'], contact=values['nom'], email=values['email'],
            title=title(values['besoin'], values['solution']), mode=mode(values['besoin']), skills='',
            consultant_id='', next_action='Qualifier la demande web sous 48 h', followup=due,
            notes='Créé automatiquement depuis la demande web ' + rid, status='PROSPECT'))
        oid, outcome = str(uuid.uuid4()), 'CREATED'
        db.execute("INSERT INTO opportunities(id," + ",".join(fields) + ") VALUES(" + ",".join("?" * (len(fields) + 1)) + ")",
                   (oid, *fields.values()))
        db.execute("INSERT INTO opportunity_events(opportunity_id,status,version) VALUES (?,?,1)", (oid, 'PROSPECT'))
    db.execute("INSERT INTO request_leads(request_id,opportunity_id,outcome) VALUES (?,?,?)", (rid, oid, outcome))
    owner = _owner(db)
    priority = 'HAUTE' if values['besoin'] == 'Demande de démonstration' else 'NORMALE'
    db.execute("INSERT INTO request_workflow VALUES (?,?,?,?,1)", (rid, owner, priority, due))
    note = 'Attribution automatique' + ('' if owner else ' : aucun commercial actif') + \
        ' ; prospect CRM ' + ('créé' if outcome == 'CREATED' else 'existant rattaché (même e-mail)')
    db.execute("""INSERT INTO request_workflow_events(request_id,actor,owner_id,priority,due_date,note)
        VALUES (?,?,?,?,?,?)""", (rid, ACTOR, owner, priority, due, note))
    accounts.event(db, ACTOR, 'PROSPECT_AUTO_' + outcome, rid)
    return read(db, rid)
