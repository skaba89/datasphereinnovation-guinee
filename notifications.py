"""Idempotent internal reminder runs; acknowledgements are scoped per actor."""
import sqlite3,uuid,json
from datetime import date
from urllib.parse import urlsplit,parse_qs
import alerts,accounts

def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS notifications(id TEXT PRIMARY KEY, kind TEXT NOT NULL, entity_id TEXT NOT NULL, due TEXT NOT NULL, priority TEXT NOT NULL, label TEXT NOT NULL, details TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(kind,entity_id,due,priority))''')
    db.execute('''CREATE TABLE IF NOT EXISTS notification_reads(notification_id TEXT NOT NULL, actor TEXT NOT NULL, read_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(notification_id,actor))''')

def run(db,today):
    with db:
        db.execute('BEGIN IMMEDIATE');items=alerts.snapshot(db,today);created=0
        db.execute('UPDATE notifications SET active=0 WHERE active=1')
        for x in items:
            key=(x['kind'],x['id'],x['due'],x['priority'])
            created+=db.execute('INSERT OR IGNORE INTO notifications(id,kind,entity_id,due,priority,label,details) VALUES(?,?,?,?,?,?,?)',(str(uuid.uuid4()),*key,x['label'],x['details'])).rowcount
            db.execute('UPDATE notifications SET active=1,label=?,details=? WHERE kind=? AND entity_id=? AND due=? AND priority=?',(x['label'],x['details'],*key))
        accounts.event(db,'scheduler','NOTIFICATIONS_REFRESH',f'{created} nouvelles')
    return created

def handle(h,connect,method):
    if not h.admin_authorized():return
    if h.headers.get('Sec-Fetch-Site')=='cross-site' or (h.headers.get('Origin') and h.headers['Origin']!='http://'+h.headers.get('Host','')):return h.json_response(403,{'error':'Origine non autorisée.'})
    if method=='GET':
        query=parse_qs(urlsplit(h.path).query)
        try:
            page=int(query.get('page',['1'])[0]);state=query.get('state',['active'])[0]
            if not 1<=page<=10000 or state not in ('active','all','unread'):raise ValueError()
        except ValueError:return h.json_response(400,{'error':'Filtre invalide.'})
        where={'active':' WHERE n.active=1','all':'','unread':' WHERE n.active=1 AND r.read_at IS NULL'}[state]
        with connect() as db:
            db.row_factory=sqlite3.Row
            join=' FROM notifications n LEFT JOIN notification_reads r ON r.notification_id=n.id AND r.actor=?'
            items=[dict(x) for x in db.execute('SELECT n.*,r.read_at'+join+where+' ORDER BY n.active DESC,n.due,n.id LIMIT 25 OFFSET ?',(h.actor,(page-1)*25))]
            return h.json_response(200,{'items':items,'total':db.execute('SELECT count(*)'+join+where,(h.actor,)).fetchone()[0],'unread':db.execute('SELECT count(*)'+join+' WHERE n.active=1 AND r.read_at IS NULL',(h.actor,)).fetchone()[0]})
    try:
        n=int(h.headers.get('Content-Length','0'))
        if not 0<n<=1000 or h.headers.get_content_type()!='application/json':raise ValueError()
        v=json.loads(h.rfile.read(n));oid=v['id']
        if set(v)!={'id'} or str(uuid.UUID(oid))!=oid:raise ValueError()
    except (ValueError,TypeError,KeyError,AttributeError):return h.json_response(400,{'error':'Notification invalide.'})
    with connect() as db:
        if not db.execute('SELECT 1 FROM notifications WHERE id=?',(oid,)).fetchone():return h.json_response(404,{'error':'Notification introuvable.'})
        if db.execute('INSERT OR IGNORE INTO notification_reads(notification_id,actor) VALUES(?,?)',(oid,h.actor)).rowcount:accounts.event(db,h.actor,'NOTIFICATION_LUE',oid)
    return h.json_response(200,{'status':'LUE'})
