"""Private encrypted PDF vault for local acceptance testing."""
import base64,binascii,hashlib,json,os,sqlite3,uuid
from urllib.parse import urlsplit,parse_qs
from cryptography.fernet import Fernet,InvalidToken
import accounts

MAX_FILE=1024*1024
MAX_TOTAL=20*1024*1024
TARGETS={'CONTRAT':'missions','CV':'consultants','DEVIS':'quotes','JUSTIFICATIF':'expenses'}

def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, category TEXT NOT NULL, entity_id TEXT NOT NULL, title TEXT NOT NULL, size INTEGER NOT NULL, sha256 TEXT NOT NULL, ciphertext BLOB NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(category,entity_id,sha256))''')

def cipher():return Fernet(os.environ.get('DSIG_DOCUMENT_KEY','').encode())

def handle(h,connect,method):
    if not h.admin_authorized():return
    if h.headers.get('Sec-Fetch-Site')=='cross-site' or (h.headers.get('Origin') and h.headers['Origin']!='http://'+h.headers.get('Host','')):return h.json_response(403,{'error':'Origine non autorisée.'})
    path=urlsplit(h.path).path
    if method=='GET' and path=='/api/admin/documents':
        try:page=max(1,min(10000,int(parse_qs(urlsplit(h.path).query).get('page',['1'])[0])))
        except ValueError:return h.json_response(400,{'error':'Page invalide.'})
        with connect() as db:
            db.row_factory=sqlite3.Row
            rows=[dict(r) for r in db.execute('SELECT id,category,entity_id,title,size,sha256,actor,created_at FROM documents ORDER BY created_at DESC,id LIMIT 25 OFFSET ?',((page-1)*25,))]
            return h.json_response(200,{'items':rows,'total':db.execute('SELECT count(*) FROM documents').fetchone()[0]})
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
            accounts.event(db,h.actor,'DOCUMENT_TELECHARGE',oid)
        h.send_response(200);h.send_header('Content-Type','application/octet-stream');h.send_header('Content-Disposition',f'attachment; filename="{oid}.pdf"');h.send_header('Cache-Control','no-store');h.send_header('Content-Length',str(len(data)));h.end_headers();h.wfile.write(data);return
    try:
        n=int(h.headers.get('Content-Length','0'))
        if not 0<n<=MAX_FILE*4//3+4096 or h.headers.get_content_type()!='application/json':raise ValueError()
        v=json.loads(h.rfile.read(n))
        if not isinstance(v,dict) or set(v)!={'category','entity_id','title','content'} or any(not isinstance(x,str) for x in v.values()):raise ValueError()
        category=v['category'];entity=v['entity_id'];title=v['title'].strip()
        if category not in TARGETS or str(uuid.UUID(entity))!=entity or not 0<len(title)<=180 or any(ord(c)<32 for c in title):raise ValueError()
        data=base64.b64decode(v['content'],validate=True)
        if not 0<len(data)<=MAX_FILE or not data.startswith(b'%PDF-') or not data.rstrip().endswith(b'%%EOF'):raise ValueError()
        digest=hashlib.sha256(data).hexdigest()
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM '+TARGETS[category]+' WHERE id=?',(entity,)).fetchone():raise ValueError()
            if db.execute('SELECT coalesce(sum(size),0) FROM documents').fetchone()[0]+len(data)>MAX_TOTAL:return h.json_response(409,{'error':'Quota documentaire atteint.'})
            oid=str(uuid.uuid4());db.execute('INSERT INTO documents(id,category,entity_id,title,size,sha256,ciphertext,actor) VALUES(?,?,?,?,?,?,?,?)',(oid,category,entity,title,len(data),digest,key.encrypt(data),h.actor));accounts.event(db,h.actor,'DOCUMENT_DEPOSE',oid)
        return h.json_response(201,{'id':oid,'sha256':digest})
    except (ValueError,TypeError,UnicodeError,binascii.Error):return h.json_response(400,{'error':'Document invalide (PDF, 1 Mio maximum, dossier existant).'} )
    except sqlite3.IntegrityError:return h.json_response(409,{'error':'Document identique déjà enregistré.'})
