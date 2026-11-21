"""Commercial request workflow; separate from customer-visible status notifications."""
import datetime
import json

PRIORITIES = ('NORMALE', 'HAUTE', 'URGENTE')


def schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS request_workflow (
        request_id TEXT PRIMARY KEY REFERENCES requests(id), owner_id TEXT NOT NULL,
        priority TEXT NOT NULL, due_date TEXT NOT NULL, revision INTEGER NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS request_workflow_events (
        id INTEGER PRIMARY KEY, request_id TEXT NOT NULL REFERENCES requests(id),
        actor TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        owner_id TEXT NOT NULL, priority TEXT NOT NULL, due_date TEXT NOT NULL,
        note TEXT NOT NULL)""")


def owners(db):
    return [dict(id=r[0], username=r[1]) for r in db.execute(
        "SELECT id,username FROM accounts WHERE enabled=1 AND role='COMMERCIAL' ORDER BY username")]


def read(db, rid):
    row = db.execute("""SELECT w.owner_id,w.priority,w.due_date,w.revision,
        COALESCE(a.username,'') FROM request_workflow w LEFT JOIN accounts a ON a.id=w.owner_id
        WHERE w.request_id=?""", (rid,)).fetchone()
    result = dict(zip(('owner_id','priority','due_date','revision','owner'), row)) if row else dict(
        owner_id='',priority='NORMALE',due_date='',revision=0,owner='')
    result['history'] = [dict(zip(('actor','created_at','owner','priority','due_date','note'), r))
        for r in db.execute("""SELECT e.actor,e.created_at,COALESCE(a.username,''),e.priority,e.due_date,e.note
            FROM request_workflow_events e LEFT JOIN accounts a ON a.id=e.owner_id
            WHERE e.request_id=? ORDER BY e.id DESC LIMIT 20""",(rid,))]
    return result


def update(db, rid, payload, actor):
    if not isinstance(payload,dict) or set(payload) != {'owner_id','priority','due_date','revision','note'}:
        raise ValueError('Données de suivi invalides.')
    owner, priority, due, revision, note = (payload[k] for k in ('owner_id','priority','due_date','revision','note'))
    if (not all(isinstance(x,str) for x in (owner,priority,due,note)) or len(owner)>36
        or priority not in PRIORITIES or len(note)>1000 or not note.strip() or '\x00' in note
        or type(revision) is not int or revision<0):
        raise ValueError('Données de suivi invalides.')
    if due and (len(due)!=10 or datetime.date.fromisoformat(due).isoformat()!=due):
        raise ValueError('Échéance invalide.')
    if not db.execute('SELECT 1 FROM requests WHERE id=?',(rid,)).fetchone():
        raise LookupError('Demande introuvable.')
    if owner and not db.execute("SELECT 1 FROM accounts WHERE id=? AND role='COMMERCIAL' AND enabled=1",(owner,)).fetchone():
        raise ValueError('Commercial indisponible.')
    previous=read(db,rid)
    if previous['revision']!=revision:
        raise RuntimeError('La demande a changé. Actualisez la liste.')
    db.execute("""INSERT INTO request_workflow VALUES (?,?,?,?,?)
        ON CONFLICT(request_id) DO UPDATE SET owner_id=excluded.owner_id,priority=excluded.priority,
        due_date=excluded.due_date,revision=excluded.revision""",(rid,owner,priority,due,revision+1))
    db.execute("""INSERT INTO request_workflow_events(request_id,actor,owner_id,priority,due_date,note)
        VALUES (?,?,?,?,?,?)""",(rid,actor,owner,priority,due,note.strip()))
    return read(db,rid)


def handle(h, connect, rid):
    if not h.admin_authorized():
        return
    try:
        size=int(h.headers.get('Content-Length','0'))
        if not 0<size<=8192 or h.headers.get_content_type()!='application/json':
            raise ValueError('Données de suivi invalides.')
        payload=json.loads(h.rfile.read(size))
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            result=update(db,rid,payload,h.actor)
    except ValueError:
        return h.json_response(400,{'error':'Données de suivi invalides ou commercial indisponible.'})
    except LookupError:
        return h.json_response(404,{'error':'Demande introuvable.'})
    except RuntimeError:
        return h.json_response(409,{'error':'La demande a changé. Actualisez la liste.'})
    return h.json_response(200,result)
