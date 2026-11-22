"""Private encrypted PDF vault for local acceptance testing."""
import base64,binascii,hashlib,json,os,sqlite3,uuid
from urllib.parse import urlsplit,parse_qs
from cryptography.fernet import Fernet,InvalidToken,MultiFernet
from datetime import date
import accounts
import antivirus

MAX_FILE=1024*1024
MAX_TOTAL=20*1024*1024
TARGETS={'CONTRAT':'missions','CV':'consultants','DEVIS':'quotes','JUSTIFICATIF':'expenses'}

def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, category TEXT NOT NULL, entity_id TEXT NOT NULL, title TEXT NOT NULL, size INTEGER NOT NULL, sha256 TEXT NOT NULL, ciphertext BLOB NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(category,entity_id,sha256))''')
    db.execute('''CREATE TABLE IF NOT EXISTS document_history(document_id TEXT PRIMARY KEY, previous_id TEXT UNIQUE, version INTEGER NOT NULL, review_date TEXT NOT NULL DEFAULT '')''')

def cipher():
    current=Fernet(os.environ.get('DSIG_DOCUMENT_KEY','').encode())
    previous=os.environ.get('DSIG_DOCUMENT_PREVIOUS_KEY','')
    return MultiFernet([current,Fernet(previous.encode())]) if previous else MultiFernet([current])

def rotate(db):
    """Rotate atomically; integrity failure rolls back all document changes."""
    if not os.environ.get('DSIG_DOCUMENT_PREVIOUS_KEY'):raise ValueError('Ancienne clé obligatoire.')
    key=cipher();current=Fernet(os.environ['DSIG_DOCUMENT_KEY'].encode())
    with db:
        db.execute('BEGIN IMMEDIATE')
        rows=db.execute('SELECT id,ciphertext,sha256,size FROM documents').fetchall()
        for oid,encrypted,digest,size in rows:
            data=key.decrypt(encrypted)
            if len(data)!=size or hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Intégrité documentaire invalide.')
            db.execute('UPDATE documents SET ciphertext=? WHERE id=?',(current.encrypt(data),oid))
        accounts.event(db,'maintenance','DOCUMENT_ROTATION','documents')
    return len(rows)

def safe_scan(h,connect,data,resource):
    try:antivirus.scan(data);return True
    except (antivirus.Infected,antivirus.Unavailable) as exc:
        infected=isinstance(exc,antivirus.Infected)
        with connect() as db:accounts.event(db,h.actor,'DOCUMENT_SCAN_REJETE' if infected else 'DOCUMENT_SCAN_INDISPONIBLE',resource)
        h.json_response(422 if infected else 503,{'error':'Document refusé par le contrôle antivirus.' if infected else 'Contrôle antivirus indisponible. Réessayez ultérieurement.'})
        return False

def handle(h,connect,method):
    if not h.admin_authorized():return
    if h.headers.get('Sec-Fetch-Site')=='cross-site' or (h.headers.get('Origin') and h.headers['Origin']!=h.expected_origin()):return h.json_response(403,{'error':'Origine non autorisée.'})
    path=urlsplit(h.path).path
    if method=='GET' and path=='/api/admin/documents':
        query=parse_qs(urlsplit(h.path).query)
        try:
            page=max(1,min(10000,int(query.get('page',['1'])[0])))
            size=int(query.get('page_size',['25'])[0])
            if size not in (10,25,50):raise ValueError()
        except ValueError:return h.json_response(400,{'error':'Page invalide.'})
        with connect() as db:
            db.row_factory=sqlite3.Row
            search=query.get('q',[''])[0].strip()[:120]
            source=' FROM documents d LEFT JOIN document_history h ON h.document_id=d.id WHERE instr(lower(d.title),lower(?))>0 OR instr(lower(d.category),lower(?))>0 OR instr(lower(d.entity_id),lower(?))>0 OR instr(lower(d.id),lower(?))>0'
            args=(search,)*4
            rows=[dict(r) for r in db.execute('''SELECT d.id,d.category,d.entity_id,d.title,d.size,d.sha256,d.actor,d.created_at,coalesce(h.version,1) AS version,coalesce(h.previous_id,'') AS previous_id,coalesce(h.review_date,'') AS review_date,NOT EXISTS(SELECT 1 FROM document_history n WHERE n.previous_id=d.id) AS current'''+source+' ORDER BY d.created_at DESC,d.id LIMIT ? OFFSET ?',(*args,size,(page-1)*size))]
            for r in rows:r['review_due']=bool(r['review_date'] and r['review_date']<=date.today().isoformat())
            return h.json_response(200,{'items':rows,'total':db.execute('SELECT count(*)'+source,args).fetchone()[0]})
    try:key=cipher()
    except (ValueError,TypeError):return h.json_response(503,{'error':'Clé documentaire non configurée.'})
    if method=='GET':
        oid=path.split('/')[-1]
        with connect() as db:
            db.row_factory=sqlite3.Row;r=db.execute('SELECT * FROM documents WHERE id=?',(oid,)).fetchone()
            if not r:return h.json_response(404,{'error':'Document introuvable.'})
            try:data=key.decrypt(r['ciphertext'])
            except InvalidToken:return h.json_response(503,{'error':'Document illisible.'})
            if hashlib.sha256(data).hexdigest()!=r['sha256'] or len(data)!=r['size']:return h.json_response(503,{'error':'Intégrité documentaire invalide.'})
        if not safe_scan(h,connect,data,oid):return
        with connect() as db:accounts.event(db,h.actor,'DOCUMENT_TELECHARGE',oid)
        h.send_response(200);h.send_header('Content-Type','application/octet-stream');h.send_header('Content-Disposition',f'attachment; filename="{oid}.pdf"');h.send_header('Cache-Control','no-store');h.send_header('Content-Length',str(len(data)));h.end_headers();h.wfile.write(data);return
    try:
        n=int(h.headers.get('Content-Length','0'))
        if not 0<n<=MAX_FILE*4//3+4096 or h.headers.get_content_type()!='application/json':raise ValueError()
        v=json.loads(h.rfile.read(n))
        required={'category','entity_id','title','content'}
        if not isinstance(v,dict) or not required<=set(v) or set(v)-required-{'previous_id','review_date'} or any(not isinstance(x,str) for x in v.values()):raise ValueError()
        category=v['category'];entity=v['entity_id'];title=v['title'].strip()
        previous=v.get('previous_id','');review=v.get('review_date','')
        if previous and str(uuid.UUID(previous))!=previous:raise ValueError()
        if review and date.fromisoformat(review).isoformat()!=review:raise ValueError()
        if category not in TARGETS or str(uuid.UUID(entity))!=entity or not 0<len(title)<=180 or any(ord(c)<32 for c in title):raise ValueError()
        data=base64.b64decode(v['content'],validate=True)
        if not 0<len(data)<=MAX_FILE or not data.startswith(b'%PDF-') or not data.rstrip().endswith(b'%%EOF'):raise ValueError()
        digest=hashlib.sha256(data).hexdigest()
        if not safe_scan(h,connect,data,category):return
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM '+TARGETS[category]+' WHERE id=?',(entity,)).fetchone():raise ValueError()
            version=1
            if previous:
                prior=db.execute('SELECT d.category,d.entity_id,coalesce(h.version,1) FROM documents d LEFT JOIN document_history h ON h.document_id=d.id WHERE d.id=?',(previous,)).fetchone()
                if not prior or prior[:2]!=(category,entity):raise ValueError()
                if db.execute('SELECT 1 FROM document_history WHERE previous_id=?',(previous,)).fetchone():return h.json_response(409,{'error':'Version déjà remplacée.'})
                version=prior[2]+1
            if db.execute('SELECT coalesce(sum(size),0) FROM documents').fetchone()[0]+len(data)>MAX_TOTAL:return h.json_response(409,{'error':'Quota documentaire atteint.'})
            oid=str(uuid.uuid4());db.execute('INSERT INTO documents(id,category,entity_id,title,size,sha256,ciphertext,actor) VALUES(?,?,?,?,?,?,?,?)',(oid,category,entity,title,len(data),digest,key.encrypt(data),h.actor));accounts.event(db,h.actor,'DOCUMENT_DEPOSE',oid)
            db.execute('INSERT INTO document_history(document_id,previous_id,version,review_date) VALUES(?,?,?,?)',(oid,previous or None,version,review))
            if previous:accounts.event(db,h.actor,'DOCUMENT_VERSION',oid)
        return h.json_response(201,{'id':oid,'sha256':digest,'version':version})
    except (ValueError,TypeError,UnicodeError,binascii.Error):return h.json_response(400,{'error':'Document invalide (PDF, 1 Mio maximum, dossier existant).'} )
    except sqlite3.IntegrityError:return h.json_response(409,{'error':'Document identique déjà enregistré.'})
