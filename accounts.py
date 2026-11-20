"""Local named accounts with hashed random access keys and server-side RBAC."""
import hashlib, secrets, json, re, sqlite3, uuid, time
from urllib.parse import urlsplit

ROLES={
 'ADMIN': {'*':'RW'},
 'DIRECTION': {'direction':'R','billing':'R','missions':'R','quotes':'R','crm':'R','tenders':'R'},
 'COMMERCIAL': {'requests':'RW','crm':'RW','quotes':'RW','tenders':'RW','consultants':'R'},
 'RH': {'consultants':'RW','requests':'R'},
 'PROJET': {'missions':'RW','consultants':'R','quotes':'R'},
 'CONTROLE': {'direction':'R','missions':'R','billing':'R','quotes':'R'},
 'COMPTABLE': {'billing':'RW','missions':'R'},
 'AUDITEUR': {'direction':'R','audit':'R'},
 'CONSULTANT': {'my-activity':'RW'},
}

def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE, role TEXT NOT NULL, key_hash TEXT NOT NULL UNIQUE, consultant_id TEXT NOT NULL DEFAULT '', enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    db.execute('''CREATE TABLE IF NOT EXISTS access_events(id INTEGER PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL, resource TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    db.execute('''CREATE TABLE IF NOT EXISTS credentials(account_id TEXT PRIMARY KEY, salt TEXT NOT NULL, verifier TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, account_id TEXT NOT NULL, expires INTEGER NOT NULL)''')

def digest(token):return hashlib.sha256(token.encode()).hexdigest()
def event(db,actor,action,resource):db.execute('INSERT INTO access_events(actor,action,resource) VALUES(?,?,?)',(actor,action,resource))
def allowed(role,resource,method):
    mode=ROLES.get(role,{}).get(resource,ROLES.get(role,{}).get('*',''))
    return ('R' if method=='GET' else 'W') in mode

def authorize(h,connect,bootstrap):
    import hmac
    header=h.headers.get('Authorization','');resource=urlsplit(h.path).path.split('/')[3]
    if len(bootstrap)>=32 and hmac.compare_digest(header.encode(),('Bearer '+bootstrap).encode()):
        h.actor='bootstrap';h.role='ADMIN';h.consultant_id=''
        with connect() as db:event(db,h.actor,'AUTORISE',h.command+' '+resource)
        return True
    if not header.startswith('Bearer ') or not re.fullmatch(r'dsig_[A-Za-z0-9_-]{43}',header[7:]):
        h.json_response(503 if len(bootstrap)<32 and not header else 401,{'error':'Accès non autorisé.'});return False
    with connect() as db:
        db.row_factory=sqlite3.Row
        row=db.execute('SELECT id,username,role,consultant_id FROM accounts WHERE key_hash=? AND enabled=1 AND NOT EXISTS(SELECT 1 FROM credentials WHERE account_id=accounts.id)',(digest(header[7:]),)).fetchone()
        if not row:
            row=db.execute('SELECT a.id,a.username,a.role,a.consultant_id FROM sessions s JOIN accounts a ON a.id=s.account_id WHERE s.token_hash=? AND s.expires>? AND a.enabled=1',(digest(header[7:]),int(time.time()))).fetchone()
        if not row:
            h.json_response(401,{'error':'Accès non autorisé.'});return False
        h.actor=row['username'];h.role=row['role'];h.consultant_id=row['consultant_id']
        permit=allowed(h.role,resource,h.command)
        event(db,h.actor,'AUTORISE' if permit else 'REFUSE',h.command+' '+resource)
    if not permit:h.json_response(403,{'error':'Permission insuffisante.'});return False
    return True

def handle(h,connect,method):
    if not h.admin_authorized():return
    if (h.headers.get('Origin') and h.headers['Origin']!='http://'+h.headers.get('Host','')) or h.headers.get('Sec-Fetch-Site')=='cross-site':return h.json_response(403,{'error':'Origine non autorisée.'})
    path=urlsplit(h.path).path
    if method=='GET':
        with connect() as db:
            db.row_factory=sqlite3.Row
            if path.endswith('/audit'):
                items=[dict(r) for r in db.execute('SELECT * FROM access_events ORDER BY id DESC LIMIT 100')]
            else:items=[dict(r) for r in db.execute('SELECT id,username,role,consultant_id,enabled,created_at FROM accounts ORDER BY username')]
        return h.json_response(200,{'items':items})
    try:
        size=int(h.headers.get('Content-Length','0'))
        if not 0<size<=4000 or h.headers.get_content_type()!='application/json':raise ValueError()
        v=json.loads(h.rfile.read(size))
        if not isinstance(v,dict):raise ValueError()
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if method=='POST':
                if set(v)!={'username','role','consultant_id'} or not all(isinstance(x,str) for x in v.values()) or not re.fullmatch(r'[A-Za-z0-9._-]{3,64}',v['username']) or v['role'] not in ROLES:raise ValueError()
                if v['role']=='CONSULTANT':
                    if not db.execute('SELECT 1 FROM consultants WHERE id=?',(v['consultant_id'],)).fetchone():raise ValueError()
                elif v['consultant_id']:raise ValueError()
                oid=str(uuid.uuid4());key='dsig_'+secrets.token_urlsafe(32)
                db.execute('INSERT INTO accounts(id,username,role,key_hash,consultant_id) VALUES(?,?,?,?,?)',(oid,v['username'],v['role'],digest(key),v['consultant_id']));event(db,h.actor,'COMPTE_CREE',v['username'])
                result={'id':oid,'key':key}
            else:
                if v not in ({'action':'DISABLE'},{'action':'ROTATE'}):raise ValueError()
                oid=path.rsplit('/',1)[-1];row=db.execute('SELECT username FROM accounts WHERE id=?',(oid,)).fetchone()
                if not row:return h.json_response(404,{'error':'Compte introuvable.'})
                if row[0]==h.actor:return h.json_response(409,{'error':'Impossible de modifier son propre compte.'})
                if v['action']=='DISABLE':db.execute('UPDATE accounts SET enabled=0 WHERE id=?',(oid,));result={'id':oid}
                else:
                    key='dsig_'+secrets.token_urlsafe(32);db.execute('UPDATE accounts SET enabled=1,key_hash=? WHERE id=?',(digest(key),oid));result={'id':oid,'key':key}
                    db.execute('DELETE FROM credentials WHERE account_id=?',(oid,))
                db.execute('DELETE FROM sessions WHERE account_id=?',(oid,))
                event(db,h.actor,v['action'],row[0])
        return h.json_response(201 if method=='POST' else 200,result)
    except (ValueError,TypeError,UnicodeError):return h.json_response(400,{'error':'Champs invalides.'})
    except sqlite3.IntegrityError:return h.json_response(409,{'error':'Compte déjà existant.'})
