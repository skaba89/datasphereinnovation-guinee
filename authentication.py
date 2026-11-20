"""Local password activation and expiring bearer sessions."""
import hashlib,hmac,secrets,time,json,re,sqlite3
from threading import Lock
import accounts

LOCK=Lock();ATTEMPTS=[];TTL=1800;ITERATIONS=600000
def derive(password,salt):return hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),ITERATIONS).hex()

def handle(h,connect):
    if (h.headers.get('Origin') and h.headers['Origin']!='http://'+h.headers.get('Host','')) or h.headers.get('Sec-Fetch-Site')=='cross-site':return h.json_response(403,{'error':'Origine interdite.'})
    try:
        n=int(h.headers.get('Content-Length','0'))
        if not 0<n<=4000 or h.headers.get_content_type()!='application/json':raise ValueError()
        v=json.loads(h.rfile.read(n))
        if not isinstance(v,dict) or any(not isinstance(x,str) or len(x)>256 for x in v.values()):raise ValueError()
    except (ValueError,TypeError,UnicodeError):return h.json_response(400,{'error':'Champs invalides.'})
    action=h.path.rsplit('/',1)[-1]
    if action=='logout':
        if v!={}:return h.json_response(400,{'error':'Champs invalides.'})
        token=h.headers.get('Authorization','')
        if not re.fullmatch(r'Bearer dsig_[A-Za-z0-9_-]{43}',token):return h.json_response(401,{'error':'Session invalide.'})
        with connect() as db:db.execute('DELETE FROM sessions WHERE token_hash=?',(accounts.digest(token[7:]),))
        return h.json_response(200,{'status':'ok'})
    now=time.monotonic()
    with LOCK:
        ATTEMPTS[:]=[x for x in ATTEMPTS if now-x<60]
        if len(ATTEMPTS)>=10:return h.json_response(429,{'error':'Réessayez dans une minute.'})
        ATTEMPTS.append(now)
    if set(v)!=({'username','password','key'} if action=='activate' else {'username','password'}) or not re.fullmatch(r'[A-Za-z0-9._-]{3,64}',v['username']) or not 12<=len(v['password'])<=128:return h.json_response(400,{'error':'Identifiant ou mot de passe invalide (12 caractères minimum).'})
    with connect() as db:
        db.row_factory=sqlite3.Row;db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT a.*,c.salt,c.verifier FROM accounts a LEFT JOIN credentials c ON c.account_id=a.id WHERE a.username=? AND a.enabled=1',(v['username'],)).fetchone()
        if action=='activate':
            if not row or row['salt'] or not hmac.compare_digest(row['key_hash'],accounts.digest(v['key'])):return h.json_response(401,{'error':'Activation refusée.'})
            salt=secrets.token_hex(16);verifier=derive(v['password'],salt)
            db.execute('INSERT INTO credentials VALUES(?,?,?)',(row['id'],salt,verifier));accounts.event(db,row['username'],'MOT_DE_PASSE_ACTIVE','auth')
            return h.json_response(200,{'status':'ok'})
        actual=derive(v['password'],row['salt'] if row and row['salt'] else '00'*16)
        if not row or not row['verifier'] or not hmac.compare_digest(actual,row['verifier']):
            if row:accounts.event(db,row['username'],'CONNEXION_REFUSEE','auth')
            return h.json_response(401,{'error':'Identifiants invalides.'})
        token='dsig_'+secrets.token_urlsafe(32);expires=int(time.time())+TTL
        db.execute('DELETE FROM sessions WHERE expires<=?',(int(time.time()),));db.execute('INSERT INTO sessions VALUES(?,?,?)',(accounts.digest(token),row['id'],expires));accounts.event(db,row['username'],'CONNEXION_REUSSIE','auth')
        return h.json_response(200,{'token':token,'expires':expires,'role':row['role'],'permissions':accounts.ROLES[row['role']]})
