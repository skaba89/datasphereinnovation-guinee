"""Local named accounts with hashed random access keys and server-side RBAC."""
import contact_mail
import hashlib, secrets, json, re, sqlite3, uuid, time, os
from urllib.parse import urlsplit

ROLES={
 'ADMIN': {'*':'RW','my-activity':'','client-portal':''},
 'DIRECTION': {'direction':'R','billing':'R','missions':'R','quotes':'R','crm':'R','tenders':'R','alerts':'R','notifications':'RW'},
 'COMMERCIAL': {'requests':'RW','crm':'RW','quotes':'RW','tenders':'RW','consultants':'R'},
 'RH': {'consultants':'RW','requests':'R','recruitment':'RW'},
 'PROJET': {'missions':'RW','consultants':'R','quotes':'R'},
 'CONTROLE': {'direction':'R','missions':'R','billing':'R','quotes':'R'},
 'COMPTABLE': {'billing':'RW','missions':'R'},
 'AUDITEUR': {'direction':'R','audit':'R'},
 'CONSULTANT': {'my-activity':'RW'},
 'CLIENT': {'client-portal':'RW'},
}

RESOURCES=frozenset({'requests','crm','quotes','tenders','consultants','missions','billing','direction','accounts','audit','documents','alerts','notifications','my-activity','recruitment','client-portal'})
def mfa_required(role):
    return role in ('ADMIN','CLIENT') or role in {x.strip() for x in os.environ.get('DSIG_MFA_REQUIRED_ROLES','DIRECTION,CONTROLE,COMPTABLE,AUDITEUR').split(',')}

def effective_permissions(role,mfa_enabled):
    return {} if mfa_required(role) and not mfa_enabled else ROLES.get(role,{})

def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE, role TEXT NOT NULL, key_hash TEXT NOT NULL UNIQUE, consultant_id TEXT NOT NULL DEFAULT '', enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    db.execute('''CREATE TABLE IF NOT EXISTS access_events(id INTEGER PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL, resource TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    db.execute('''CREATE TABLE IF NOT EXISTS credentials(account_id TEXT PRIMARY KEY, salt TEXT NOT NULL, verifier TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, account_id TEXT NOT NULL, expires INTEGER NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS mfa(account_id TEXT PRIMARY KEY, secret TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0, last_step INTEGER NOT NULL DEFAULT -1)''')
    db.execute('''CREATE TABLE IF NOT EXISTS recovery_codes(account_id TEXT NOT NULL, code_hash TEXT NOT NULL, PRIMARY KEY(account_id,code_hash))''')
    db.execute('''CREATE TABLE IF NOT EXISTS archived_accounts(account_id TEXT PRIMARY KEY, archived_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    db.execute('''CREATE TRIGGER IF NOT EXISTS archived_account_no_reactivation BEFORE UPDATE OF enabled ON accounts WHEN NEW.enabled=1 AND EXISTS(SELECT 1 FROM archived_accounts WHERE account_id=OLD.id) BEGIN SELECT RAISE(ABORT,'Archived account'); END''')

def unused(db,oid,username,consultant_id):
    # Conservative: retain any linked consultant, invitation or recorded use.
    if consultant_id:return False
    if db.execute('SELECT 1 FROM client_accounts WHERE account_id=?',(oid,)).fetchone():return False
    if db.execute('SELECT 1 FROM access_events WHERE actor=? COLLATE NOCASE LIMIT 1',(username,)).fetchone():return False
    for table,column in (('credentials','account_id'),('mfa','account_id'),('sessions','account_id'),('recovery_codes','account_id'),('account_invitation','request_id'),('request_workflow','owner_id'),('request_workflow_events','owner_id')):
        if db.execute(f'SELECT 1 FROM {table} WHERE {column}=? LIMIT 1',(oid,)).fetchone():return False
    return True

def admin_protected(db,oid):
    # Keep at least one enabled administrator, and never remove the last usable MFA admin.
    row=db.execute("SELECT enabled,role FROM accounts WHERE id=?",(oid,)).fetchone()
    if not row or row[1]!='ADMIN' or not row[0]:return False
    if not db.execute("SELECT 1 FROM accounts WHERE role='ADMIN' AND enabled=1 AND id<>?",(oid,)).fetchone():return True
    usable="SELECT 1 FROM accounts a JOIN credentials c ON c.account_id=a.id JOIN mfa m ON m.account_id=a.id AND m.enabled=1 WHERE a.role='ADMIN' AND a.enabled=1 AND a.id"
    return bool(db.execute(usable+'=?',(oid,)).fetchone() and not db.execute(usable+'<>?',(oid,)).fetchone())

def digest(token):return hashlib.sha256(token.encode()).hexdigest()
def event(db,actor,action,resource):db.execute('INSERT INTO access_events(actor,action,resource) VALUES(?,?,?)',(actor,action,resource))
def allowed(role,resource,method):
    if resource not in RESOURCES or method not in ('GET','POST','PATCH','DELETE'):return False
    mode=ROLES.get(role,{}).get(resource,ROLES.get(role,{}).get('*',''))
    return ('R' if method=='GET' else 'W') in mode

def session_cookie(h):
    from http.cookies import SimpleCookie, CookieError
    try:
        cookie=SimpleCookie();cookie.load(h.headers.get('Cookie',''));value=cookie['dsig_session'].value
        return value if re.fullmatch(r'dsig_[A-Za-z0-9_-]{43}',value) else ''
    except (CookieError,KeyError):return ''

def authorize(h,connect,bootstrap):
    import hmac
    header=h.headers.get('Authorization','');resource=urlsplit(h.path).path.split('/')[3]
    cookie_mode=header=='Bearer session'
    if cookie_mode:
        if h.headers.get('Sec-Fetch-Site')=='cross-site':
            h.json_response(403,{'error':'Origine non autorisée.'});return False
        if h.command!='GET' and h.headers.get('Origin')!=h.expected_origin():
            h.json_response(403,{'error':'Origine non autorisée.'});return False
        header='Bearer '+session_cookie(h)
    if not cookie_mode and len(bootstrap)>=32 and hmac.compare_digest(header.encode(),('Bearer '+bootstrap).encode()):
        h.actor_id=None;h.actor='bootstrap';h.role='ADMIN';h.consultant_id=''
        with connect() as db:event(db,h.actor,'AUTORISE',h.command+' '+resource)
        return True
    if not header.startswith('Bearer ') or not re.fullmatch(r'dsig_[A-Za-z0-9_-]{43}',header[7:]):
        h.json_response(503 if len(bootstrap)<32 and not header else 401,{'error':'Accès non autorisé.'});return False
    with connect() as db:
        db.row_factory=sqlite3.Row
        row=None if cookie_mode else db.execute('SELECT id,username,role,consultant_id FROM accounts WHERE key_hash=? AND enabled=1 AND NOT EXISTS(SELECT 1 FROM credentials WHERE account_id=accounts.id)',(digest(header[7:]),)).fetchone()
        if not row:
            row=db.execute('SELECT a.id,a.username,a.role,a.consultant_id FROM sessions s JOIN accounts a ON a.id=s.account_id WHERE s.token_hash=? AND s.expires>? AND a.enabled=1',(digest(header[7:]),int(time.time()))).fetchone()
        if not row:
            h.json_response(401,{'error':'Accès non autorisé.'});return False
        h.actor_id=row['id'];h.actor=row['username'];h.role=row['role'];h.consultant_id=row['consultant_id']
        if mfa_required(h.role) and not db.execute('SELECT 1 FROM mfa WHERE account_id=? AND enabled=1',(row['id'],)).fetchone():
            event(db,h.actor,'MFA_REQUISE',h.command+' '+resource)
            h.json_response(403,{'error':'Activation MFA obligatoire avant accès aux modules.'});return False
        permit=allowed(h.role,resource,h.command)
        event(db,h.actor,'AUTORISE' if permit else 'REFUSE',h.command+' '+resource)
    if not permit:h.json_response(403,{'error':'Permission insuffisante.'});return False
    return True

def handle(h,connect,method):
    if not h.admin_authorized():return
    if (h.headers.get('Origin') and h.headers['Origin']!=h.expected_origin()) or h.headers.get('Sec-Fetch-Site')=='cross-site':return h.json_response(403,{'error':'Origine non autorisée.'})
    path=urlsplit(h.path).path
    if method=='GET':
        with connect() as db:
            db.row_factory=sqlite3.Row
            if path.endswith('/audit'):
                items=[dict(r) for r in db.execute('SELECT * FROM access_events ORDER BY id DESC LIMIT 100')]
            else:
                items=[dict(r) for r in db.execute('SELECT a.id,a.username,a.role,a.consultant_id,a.enabled,a.created_at,EXISTS(SELECT 1 FROM credentials c WHERE c.account_id=a.id) AS activated,EXISTS(SELECT 1 FROM mfa m WHERE m.account_id=a.id AND m.enabled=1) AS mfa_enabled FROM accounts a ORDER BY a.username')]
                for item in items:
                    org=db.execute('SELECT o.id,o.name FROM client_accounts c JOIN organizations o ON o.id=c.organization_id WHERE c.account_id=?',(item['id'],)).fetchone()
                    item['organization_id']=org[0] if org else ''
                    item['organization_name']=org[1] if org else ''
                    item['self']=item['id']==getattr(h,'actor_id',None)
                    item['archived']=bool(db.execute('SELECT 1 FROM archived_accounts WHERE account_id=?',(item['id'],)).fetchone())
                    item['protected']=admin_protected(db,item['id'])
                    item['deletable']=not item['archived'] and not item['self'] and not item['protected'] and unused(db,item['id'],item['username'],item['consultant_id'])
                    invitation=db.execute('SELECT state FROM account_invitation WHERE request_id=?',(item['id'],)).fetchone()
                    item['invitation_state']=invitation[0] if invitation else 'NONE'
        return h.json_response(200,{'items':items})
    try:
        size=int(h.headers.get('Content-Length','0'))
        if not 0<size<=4000 or h.headers.get_content_type()!='application/json':raise ValueError()
        v=json.loads(h.rfile.read(size))
        if not isinstance(v,dict):raise ValueError()
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if method=='POST':
                organization_id=v.pop('organization_id','')
                if not isinstance(organization_id,str):raise ValueError()
                if set(v)!={'username','role','consultant_id'} or not all(isinstance(x,str) for x in v.values()) or not re.fullmatch(r'[A-Za-z0-9._-]{3,64}',v['username']) or v['role'] not in ROLES:raise ValueError()
                if v['role']=='CLIENT':
                    if not db.execute("SELECT 1 FROM organizations WHERE id=? AND kind='CLIENT'",(organization_id,)).fetchone():raise ValueError()
                elif organization_id:raise ValueError()
                if v['role']=='CONSULTANT':
                    if not db.execute('SELECT 1 FROM consultants WHERE id=?',(v['consultant_id'],)).fetchone():raise ValueError()
                elif v['consultant_id']:raise ValueError()
                if db.execute("SELECT 1 FROM access_events WHERE action='COMPTE_SUPPRIME' AND resource=? COLLATE NOCASE",(v['username'],)).fetchone():return h.json_response(409,{'error':'Identifiant réservé par le journal d’audit.'})
                oid=str(uuid.uuid4());key='dsig_'+secrets.token_urlsafe(32)
                db.execute('INSERT INTO accounts(id,username,role,key_hash,consultant_id) VALUES(?,?,?,?,?)',(oid,v['username'],v['role'],digest(key),v['consultant_id']));event(db,h.actor,'COMPTE_CREE',v['username'])
                if v['role']=='CLIENT':db.execute('INSERT INTO client_accounts VALUES(?,?)',(oid,organization_id))
                result={'id':oid,'key':key}
            else:
                if v not in ({'action':'DISABLE'},{'action':'ROTATE'},{'action':'INVITE'},{'action':'ARCHIVE'},{'action':'DELETE'}):raise ValueError()
                oid=path.rsplit('/',1)[-1];row=db.execute('SELECT username,enabled,consultant_id FROM accounts WHERE id=?',(oid,)).fetchone()
                if not row:return h.json_response(404,{'error':'Compte introuvable.'})
                if oid==getattr(h,'actor_id',None):return h.json_response(409,{'error':'Impossible de modifier son propre compte.'})
                if db.execute('SELECT 1 FROM archived_accounts WHERE account_id=?',(oid,)).fetchone():return h.json_response(409,{'error':'Compte archivé : modification interdite.'})
                if v['action']!='INVITE' and admin_protected(db,oid):return h.json_response(409,{'error':'Dernier administrateur actif ou opérationnel protégé.'})
                if v['action']=='DELETE':
                    if not unused(db,oid,row[0],row[2]):return h.json_response(409,{'error':'Compte avec historique ou lien métier : archivez-le.'})
                    db.execute('DELETE FROM accounts WHERE id=?',(oid,));event(db,h.actor,'COMPTE_SUPPRIME',row[0])
                    db.commit();return h.json_response(200,{'id':oid})
                if v['action']=='ARCHIVE':
                    db.execute('UPDATE accounts SET enabled=0 WHERE id=?',(oid,))
                    db.execute('INSERT INTO archived_accounts(account_id) VALUES(?)',(oid,))
                    for table in ('sessions','credentials','mfa','recovery_codes'):
                        db.execute(f'DELETE FROM {table} WHERE account_id=?',(oid,))
                    db.execute("UPDATE account_invitation SET state='CANCELLED' WHERE request_id=? AND state='PENDING'",(oid,))
                    event(db,h.actor,'COMPTE_ARCHIVE',row[0]);db.commit();return h.json_response(200,{'id':oid})
                if v['action']=='INVITE':
                    if os.environ.get('DSIG_ENV','REC')!='REC':return h.json_response(403,{'error':'Invitations de test REC uniquement.'})
                    if not row[1] or db.execute('SELECT 1 FROM credentials WHERE account_id=?',(oid,)).fetchone():return h.json_response(409,{'error':'Compte non éligible à une invitation.'})
                    if not contact_mail.enqueue_invitation(db,oid):return h.json_response(409,{'error':'Invitation déjà planifiée.'})
                    event(db,h.actor,'INVITATION_REC',row[0]);db.commit()
                    return h.json_response(200,{'id':oid,'invitation_state':'PENDING'})
                if v['action']=='DISABLE':db.execute('UPDATE accounts SET enabled=0 WHERE id=?',(oid,));result={'id':oid}
                else:
                    key='dsig_'+secrets.token_urlsafe(32);db.execute('UPDATE accounts SET enabled=1,key_hash=? WHERE id=?',(digest(key),oid));result={'id':oid,'key':key}
                    db.execute('DELETE FROM credentials WHERE account_id=?',(oid,))
                    db.execute('DELETE FROM mfa WHERE account_id=?',(oid,))
                    db.execute('DELETE FROM recovery_codes WHERE account_id=?',(oid,))
                db.execute('DELETE FROM sessions WHERE account_id=?',(oid,))
                event(db,h.actor,v['action'],row[0])
        return h.json_response(201 if method=='POST' else 200,result)
    except (ValueError,TypeError,UnicodeError):return h.json_response(400,{'error':'Champs invalides.'})
    except sqlite3.IntegrityError:return h.json_response(409,{'error':'Compte déjà existant.'})

