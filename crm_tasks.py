"""Commercial tasks (calls, emails, follow-ups, meetings) with a personal daily list.

Read: any role with CRM read. Write: CRM write roles. A commercial may only change
tasks assigned to them (or unassigned); ADMIN may change any task. Optimistic locking
by version. Overdue open tasks feed the internal notification centre.
"""
import json
import sqlite3
import uuid
from datetime import date, timedelta
from urllib.parse import parse_qs, urlsplit

import accounts

KINDS = ('APPEL', 'EMAIL', 'RELANCE', 'RENDEZ_VOUS', 'AUTRE')
STATES = ('A_FAIRE', 'FAIT', 'ANNULEE')
OWNER_ROLES = ('COMMERCIAL', 'ADMIN')
OPEN_OPPORTUNITIES = ('PROSPECT', 'QUALIFIE', 'PROPOSITION', 'NEGOCIATION')


def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS crm_tasks (
        id TEXT PRIMARY KEY, title TEXT NOT NULL, kind TEXT NOT NULL, due_date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'A_FAIRE', opportunity_id TEXT NOT NULL DEFAULT '',
        owner_id TEXT NOT NULL DEFAULT '', created_by TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, closed_at TEXT)''')
    db.execute('CREATE INDEX IF NOT EXISTS crm_tasks_owner ON crm_tasks(owner_id,status,due_date)')
    db.execute('CREATE INDEX IF NOT EXISTS crm_tasks_opportunity ON crm_tasks(opportunity_id)')


def _text(value, limit=180):
    if not isinstance(value, str) or not 0 < len(value.strip()) <= limit or any(ord(c) < 32 for c in value):
        raise ValueError()
    return value.strip()


def _day(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value or not '2000' <= value[:4] <= '2099':
        raise ValueError()
    return value


def _owner(db, owner_id):
    if owner_id == '':
        return ''
    if not isinstance(owner_id, str) or not db.execute(
            f"SELECT 1 FROM accounts WHERE id=? AND enabled=1 AND role IN ({','.join('?' * len(OWNER_ROLES))})",
            (owner_id, *OWNER_ROLES)).fetchone():
        raise ValueError()
    return owner_id


def create(db, v, actor, actor_id):
    if not isinstance(v, dict) or set(v) != {'title', 'kind', 'due_date', 'opportunity_id', 'owner_id'} or v['kind'] not in KINDS:
        raise ValueError()
    opportunity = v['opportunity_id']
    if opportunity != '' and (not isinstance(opportunity, str) or not db.execute('SELECT 1 FROM opportunities WHERE id=?', (opportunity,)).fetchone()):
        raise ValueError()
    owner = _owner(db, (actor_id or '') if v['owner_id'] == 'me' else v['owner_id'])
    tid = str(uuid.uuid4())
    db.execute('INSERT INTO crm_tasks(id,title,kind,due_date,opportunity_id,owner_id,created_by) VALUES (?,?,?,?,?,?,?)',
               (tid, _text(v['title']), v['kind'], _day(v['due_date']), opportunity, owner, actor))
    accounts.event(db, actor, 'TACHE_CREEE', tid)
    return tid


def update(db, tid, v, actor, actor_id, role):
    if not isinstance(v, dict) or type(v.get('version')) is not int:
        raise ValueError()
    task = db.execute('SELECT owner_id,status FROM crm_tasks WHERE id=?', (tid,)).fetchone()
    if not task:
        raise LookupError()
    if role != 'ADMIN' and task[0] not in ('', actor_id):
        raise PermissionError()
    if task[1] != 'A_FAIRE':
        raise sqlite3.IntegrityError('closed')
    if set(v) == {'status', 'version'} and v['status'] in ('FAIT', 'ANNULEE'):
        sql, args, action = "status=?,closed_at=CURRENT_TIMESTAMP", (v['status'],), 'TACHE_' + ('TERMINEE' if v['status'] == 'FAIT' else 'ANNULEE')
    elif set(v) == {'due_date', 'version'}:
        sql, args, action = 'due_date=?', (_day(v['due_date']),), 'TACHE_REPORTEE'
    else:
        raise ValueError()
    if db.execute(f"UPDATE crm_tasks SET {sql},version=version+1 WHERE id=? AND version=? AND status='A_FAIRE'",
                  (*args, tid, v['version'])).rowcount != 1:
        raise sqlite3.IntegrityError('version')
    accounts.event(db, actor, action, tid)


def listing(db, view, state, actor_id, today):
    db.row_factory = sqlite3.Row
    where, args = ['t.status=?' if state == 'done' else "t.status='A_FAIRE'"], (['FAIT'] if state == 'done' else [])
    if view == 'mine':
        where.append('t.owner_id=?')
        args.append(actor_id or '')
    order = 't.closed_at DESC' if state == 'done' else 't.due_date,t.created_at'
    rows = db.execute(f'''SELECT t.id,t.title,t.kind,t.due_date,t.status,t.version,t.owner_id,t.opportunity_id,t.closed_at,
            COALESCE(a.username,'') AS owner, COALESCE(o.company,'') AS company, COALESCE(o.title,'') AS opportunity_title,
            COALESCE(l.organization_id,'') AS organization_id
        FROM crm_tasks t LEFT JOIN accounts a ON a.id=t.owner_id LEFT JOIN opportunities o ON o.id=t.opportunity_id
        LEFT JOIN organization_links l ON l.opportunity_id=t.opportunity_id
        WHERE {' AND '.join(where)} ORDER BY {order} LIMIT 200''', args)
    items = [dict(r) for r in rows]
    now = today.isoformat()
    for item in items:
        item['bucket'] = 'done' if item['status'] != 'A_FAIRE' else 'late' if item['due_date'] < now else 'today' if item['due_date'] == now else 'upcoming'
    return items


def reminders(db, today):
    """Overdue open tasks for the notification centre (no customer contact data)."""
    return [dict(kind='TACHE_EN_RETARD', id=tid, due=due, priority='URGENT', label=title,
                 details='Tâche commerciale en retard' + (f' · {owner}' if owner else ' · non attribuée'))
            for tid, title, due, owner in db.execute('''SELECT t.id,t.title,t.due_date,COALESCE(a.username,'') FROM crm_tasks t
                LEFT JOIN accounts a ON a.id=t.owner_id WHERE t.status='A_FAIRE' AND t.due_date<?''', (today.isoformat(),))]


def handle(h, connect, method):
    if not h.admin_authorized():
        return
    if method == 'GET':
        query = parse_qs(urlsplit(h.path).query)
        view, state = query.get('view', ['mine'])[0], query.get('state', ['open'])[0]
        if set(query) - {'view', 'state'} or view not in ('mine', 'team') or state not in ('open', 'done'):
            return h.json_response(400, {'error': 'Filtre invalide.'})
        can_write = accounts.allowed(h.role, 'crm', 'POST')
        with connect() as db:
            today = date.today()
            items = listing(db, view, state, h.actor_id, today)
            mine = db.execute("SELECT due_date FROM crm_tasks WHERE status='A_FAIRE' AND owner_id=?", (h.actor_id or '',)).fetchall()
            counts = {'late': sum(d[0] < today.isoformat() for d in mine), 'today': sum(d[0] == today.isoformat() for d in mine),
                      'week': sum(today.isoformat() < d[0] <= (today + timedelta(days=7)).isoformat() for d in mine)}
            owners = [dict(r) for r in db.execute(f"""SELECT id,username FROM accounts WHERE enabled=1
                AND role IN ({','.join('?' * len(OWNER_ROLES))}) ORDER BY username""", OWNER_ROLES)] if can_write else []
            opportunities = [dict(r) for r in db.execute(f"""SELECT id,company,title FROM opportunities
                WHERE status IN ({','.join('?' * len(OPEN_OPPORTUNITIES))}) ORDER BY company,title LIMIT 300""", OPEN_OPPORTUNITIES)] if can_write else []
        return h.json_response(200, {'items': items, 'counts': counts, 'today': today.isoformat(), 'can_write': can_write, 'manage_all': can_write and h.role == 'ADMIN',
                                     'me': h.actor_id or '', 'owners': owners, 'opportunities': opportunities})
    try:
        n = int(h.headers.get('Content-Length', '0'))
        if not 0 < n <= 4096 or h.headers.get_content_type() != 'application/json':
            raise ValueError()
        v = json.loads(h.rfile.read(n))
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if method == 'POST':
                tid = create(db, v, h.actor, h.actor_id)
            else:
                tid = urlsplit(h.path).path.rsplit('/', 1)[-1]
                update(db, tid, v, h.actor, h.actor_id, h.role)
        return h.json_response(201 if method == 'POST' else 200, {'id': tid})
    except (ValueError, TypeError, UnicodeError):
        return h.json_response(400, {'error': 'Tâche invalide.'})
    except LookupError:
        return h.json_response(404, {'error': 'Tâche introuvable.'})
    except PermissionError:
        return h.json_response(403, {'error': 'Tâche attribuée à un autre commercial.'})
    except sqlite3.IntegrityError:
        return h.json_response(409, {'error': 'Tâche déjà modifiée ou clôturée. Actualisez la liste.'})
