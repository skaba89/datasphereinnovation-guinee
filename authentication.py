"""Local password activation and expiring bearer sessions."""
import hashlib,hmac,secrets,time,json,re,sqlite3,base64,struct,os
from cryptography.fernet import Fernet, InvalidToken
from threading import Lock
import accounts

LOCK=Lock();ATTEMPTS={};TTL=1800;ITERATIONS=600000
def mfa_cipher():
    return Fernet(os.environ.get('DSIG_MFA_KEY','').encode())

def encrypt_secret(secret):return 'fernet:'+mfa_cipher().encrypt(secret.encode()).decode()

def decrypt_secret(stored):
    cipher=mfa_cipher()
    if stored.startswith('fernet:'):return cipher.decrypt(stored[7:].encode()).decode()
    if re.fullmatch(r'[A-Z2-7]{32}',stored):return stored # V15/V16 migration after successful verification
    raise ValueError('Invalid MFA secret')

def recovery_codes(db,account_id):
    codes=[secrets.token_hex(16) for _ in range(8)]
    db.execute('DELETE FROM recovery_codes WHERE account_id=?',(account_id,))
    db.executemany('INSERT INTO recovery_codes VALUES(?,?)',[(account_id,accounts.digest(c)) for c in codes])
    return codes
def derive(password,salt):return hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),ITERATIONS).hex()

def totp(secret,step):
    raw=hmac.digest(base64.b32decode(secret),struct.pack('>Q',step),'sha1');offset=raw[-1]&15
    return str((int.from_bytes(raw[offset:offset+4],'big')&0x7fffffff)%1000000).zfill(6)

def verify_code(secret,code,last):
    now=int(time.time())//30
    if not re.fullmatch(r'\d{6}',code):return None
    for step in (now-1,now,now+1):
        if step>last and hmac.compare_digest(totp(secret,step),code):return step
    return None

def cookie(h,token='',ttl=0):
    h.session_cookie_header=f'dsig_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={ttl}'
    if h.secure_cookie():h.session_cookie_header+='; Secure'

def me(h,connect):
    if h.headers.get('Authorization')!='Bearer session' or h.headers.get('Sec-Fetch-Site')=='cross-site':return h.json_response(401,{'error':'Session invalide.'})
    with connect() as db:
        db.row_factory=sqlite3.Row
        row=db.execute('SELECT a.id,a.role,s.expires,COALESCE(m.enabled,0) AS mfa FROM sessions s JOIN accounts a ON a.id=s.account_id LEFT JOIN mfa m ON m.account_id=a.id WHERE s.token_hash=? AND s.expires>? AND a.enabled=1',(accounts.digest(accounts.session_cookie(h)),int(time.time()))).fetchone()
        if not row:return h.json_response(401,{'error':'Session invalide.'})
        count=db.execute('SELECT COUNT(*) FROM sessions WHERE account_id=? AND expires>?',(row['id'],int(time.time()))).fetchone()[0]
        return h.json_response(200,{'role':row['role'],'expires':row['expires'],'permissions':accounts.effective_permissions(row['role'],row['mfa']),'active_sessions':count,'mfa_enabled':bool(row['mfa']),'mfa_required':accounts.mfa_required(row['role'])})

def handle(h,connect):
    if (h.headers.get('Origin') and h.headers['Origin']!=h.expected_origin()) or h.headers.get('Sec-Fetch-Site')=='cross-site':return h.json_response(403,{'error':'Origine interdite.'})
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
        if token=='Bearer session':
            if h.headers.get('Origin')!=h.expected_origin():return h.json_response(403,{'error':'Origine interdite.'})
            token='Bearer '+accounts.session_cookie(h)
        if not re.fullmatch(r'Bearer dsig_[A-Za-z0-9_-]{43}',token):return h.json_response(401,{'error':'Session invalide.'})
        with connect() as db:
            row=db.execute('SELECT a.username FROM sessions s JOIN accounts a ON a.id=s.account_id WHERE s.token_hash=?',(accounts.digest(token[7:]),)).fetchone()
            db.execute('DELETE FROM sessions WHERE token_hash=?',(accounts.digest(token[7:]),))
            if row:accounts.event(db,row[0],'DECONNEXION','auth')
        cookie(h)
        return h.json_response(200,{'status':'ok'})
    now=time.monotonic()
    with LOCK:
        for ip in list(ATTEMPTS):
            ATTEMPTS[ip]=[x for x in ATTEMPTS[ip] if now-x<60]
            if not ATTEMPTS[ip]:del ATTEMPTS[ip]
        ip=h.client_address[0]
        if sum(map(len,ATTEMPTS.values()))>=120 or len(ATTEMPTS.get(ip,()))>=10:return h.json_response(429,{'error':'Réessayez dans une minute.'})
        ATTEMPTS.setdefault(ip,[]).append(now)
    if action=='revoke-others':
        if h.headers.get('Origin')!=h.expected_origin() or h.headers.get('Authorization')!='Bearer session':return h.json_response(403,{'error':'Origine interdite.'})
        if set(v)!={'password'}:return h.json_response(400,{'error':'Champs invalides.'})
        token_hash=accounts.digest(accounts.session_cookie(h))
        with connect() as db:
            db.row_factory=sqlite3.Row;db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT a.id,a.username,c.salt,c.verifier FROM sessions s JOIN accounts a ON a.id=s.account_id JOIN credentials c ON c.account_id=a.id WHERE s.token_hash=? AND s.expires>? AND a.enabled=1',(token_hash,int(time.time()))).fetchone()
            if not row:return h.json_response(401,{'error':'Session invalide.'})
            if not hmac.compare_digest(derive(v['password'],row['salt']),row['verifier']):
                accounts.event(db,row['username'],'REVOCATION_REFUSEE','auth');return h.json_response(401,{'error':'Mot de passe invalide.'})
            count=db.execute('DELETE FROM sessions WHERE account_id=? AND token_hash<>?',(row['id'],token_hash)).rowcount
            accounts.event(db,row['username'],'SESSIONS_REVOQUEES','auth')
            db.commit()
            return h.json_response(200,{'revoked':count})
    if action in ('mfa-setup','mfa-confirm'):
        if h.headers.get('Origin')!=h.expected_origin() or h.headers.get('Authorization')!='Bearer session':return h.json_response(403,{'error':'Origine interdite.'})
        if set(v)!=({'password'} if action=='mfa-setup' else {'code'}):return h.json_response(400,{'error':'Champs invalides.'})
        with connect() as db:
            db.row_factory=sqlite3.Row;db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT a.id,a.username,c.salt,c.verifier FROM sessions s JOIN accounts a ON a.id=s.account_id JOIN credentials c ON c.account_id=a.id WHERE s.token_hash=? AND s.expires>? AND a.enabled=1',(accounts.digest(accounts.session_cookie(h)),int(time.time()))).fetchone()
            if not row:return h.json_response(401,{'error':'Session invalide.'})
            m=db.execute('SELECT * FROM mfa WHERE account_id=?',(row['id'],)).fetchone()
            if m and m['enabled']:return h.json_response(409,{'error':'MFA déjà activée.'})
            if action=='mfa-setup':
                if not hmac.compare_digest(derive(v['password'],row['salt']),row['verifier']):return h.json_response(401,{'error':'Mot de passe invalide.'})
                secret=base64.b32encode(secrets.token_bytes(20)).decode()
                try: encrypted=encrypt_secret(secret)
                except (ValueError,TypeError):return h.json_response(503,{'error':'Configuration MFA indisponible.'})
                db.execute('INSERT OR REPLACE INTO mfa(account_id,secret) VALUES(?,?)',(row['id'],encrypted));db.commit();return h.json_response(200,{'secret':secret})
            try: plain=decrypt_secret(m['secret']) if m else None
            except (ValueError,TypeError,InvalidToken):return h.json_response(503,{'error':'Configuration MFA indisponible.'})
            step=verify_code(plain,v['code'],m['last_step']) if m else None
            if step is None:return h.json_response(401,{'error':'Code invalide.'})
            db.execute('UPDATE mfa SET enabled=1,last_step=?,secret=? WHERE account_id=?',(step,encrypt_secret(plain),row['id']));codes=recovery_codes(db,row['id']);db.execute('DELETE FROM sessions WHERE account_id=?',(row['id'],));accounts.event(db,row['username'],'MFA_ACTIVE','auth');db.commit();cookie(h);return h.json_response(200,{'status':'ok','recovery_codes':codes})
    if set(v) not in ([{'username','password','key'}] if action=='activate' else [{'username','password'},{'username','password','otp'}]) or not re.fullmatch(r'[A-Za-z0-9._-]{3,64}',v['username']) or not 12<=len(v['password'])<=128:return h.json_response(400,{'error':'Identifiant ou mot de passe invalide (12 caractères minimum).'})
    with connect() as db:
        db.row_factory=sqlite3.Row;db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT a.*,c.salt,c.verifier FROM accounts a LEFT JOIN credentials c ON c.account_id=a.id WHERE a.username=? AND a.enabled=1',(v['username'],)).fetchone()
        if action=='activate':
            if not row or row['salt'] or not hmac.compare_digest(row['key_hash'],accounts.digest(v['key'])):return h.json_response(401,{'error':'Activation refusée.'})
            salt=secrets.token_hex(16);verifier=derive(v['password'],salt)
            db.execute('INSERT INTO credentials VALUES(?,?,?)',(row['id'],salt,verifier));accounts.event(db,row['username'],'MOT_DE_PASSE_ACTIVE','auth')
            db.commit()
            return h.json_response(200,{'status':'ok'})
        actual=derive(v['password'],row['salt'] if row and row['salt'] else '00'*16)
        if not row or not row['verifier'] or not hmac.compare_digest(actual,row['verifier']):
            if row:accounts.event(db,row['username'],'CONNEXION_REFUSEE','auth')
            return h.json_response(401,{'error':'Identifiants invalides.'})
        m=db.execute('SELECT * FROM mfa WHERE account_id=? AND enabled=1',(row['id'],)).fetchone()
        if m:
            try: plain=decrypt_secret(m['secret'])
            except (ValueError,TypeError,InvalidToken):return h.json_response(503,{'error':'Configuration MFA indisponible.'})
            otp=v.get('otp','');step=verify_code(plain,otp,m['last_step'])
            if step is None:
                if not re.fullmatch(r'[a-f0-9]{32}',otp) or not db.execute('DELETE FROM recovery_codes WHERE account_id=? AND code_hash=?',(row['id'],accounts.digest(otp))).rowcount:return h.json_response(401,{'error':'Code MFA manquant, invalide ou déjà utilisé.'})
                db.execute('DELETE FROM sessions WHERE account_id=?',(row['id'],));accounts.event(db,row['username'],'CODE_SECOURS_UTILISE','auth')
            else:db.execute('UPDATE mfa SET last_step=? WHERE account_id=?',(step,row['id']))
            if not m['secret'].startswith('fernet:'):db.execute('UPDATE mfa SET secret=? WHERE account_id=?',(encrypt_secret(plain),row['id']))
        token='dsig_'+secrets.token_urlsafe(32);expires=int(time.time())+TTL
        db.execute('DELETE FROM sessions WHERE expires<=?',(int(time.time()),));db.execute('INSERT INTO sessions VALUES(?,?,?)',(accounts.digest(token),row['id'],expires));accounts.event(db,row['username'],'CONNEXION_REUSSIE','auth')
        # Publish the session only after SQLite commits the authentication state.
        db.commit()
        cookie(h,token,TTL)
        result={'expires':expires,'role':row['role'],'permissions':accounts.effective_permissions(row['role'],bool(m)),'mfa_required':accounts.mfa_required(row['role']),'mfa_enabled':bool(m)}
        if h.headers.get('X-DSIG-Session')!='cookie':result['token']=token
        return h.json_response(200,result)
