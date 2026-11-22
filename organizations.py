"""Internal organization directory, accessible through the CRM permission."""
import json
import sqlite3
import uuid
import accounts
from urllib.parse import parse_qs, urlsplit

FIELDS = {'name': 180, 'kind': 20, 'country': 100, 'notes': 1000}
KINDS = ('PROSPECT', 'CLIENT', 'PARTENAIRE')


def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS organizations (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, name_key TEXT NOT NULL UNIQUE,
        kind TEXT NOT NULL, country TEXT NOT NULL, notes TEXT NOT NULL,
        version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    db.execute('''CREATE TABLE IF NOT EXISTS organization_links (
        opportunity_id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id))''')
    db.execute('CREATE INDEX IF NOT EXISTS organization_links_org ON organization_links(organization_id)')
    db.execute('''CREATE TABLE IF NOT EXISTS organization_conversions (
        id INTEGER PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id),
        opportunity_id TEXT NOT NULL, version INTEGER NOT NULL, actor TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')


def handle(h, connect, method):
    if not h.admin_authorized(): return
    if h.headers.get('Sec-Fetch-Site') == 'cross-site' or (h.headers.get('Origin') and h.headers['Origin'] != h.expected_origin()):
        return h.json_response(403, {'error': 'Origine non autorisée.'})
    if method == 'GET':
        query = parse_qs(urlsplit(h.path).query)
        q = query.get('q', [''])[0][:180].casefold()
        try:
            page = max(1, min(10000, int(query.get('page', ['1'])[0])))
        except ValueError:
            return h.json_response(400, {'error': 'Page invalide.'})
        with connect() as db:
            db.row_factory = sqlite3.Row
            total = db.execute('SELECT count(*) FROM organizations WHERE instr(name_key,?)>0', (q,)).fetchone()[0]
            items = [dict(r) for r in db.execute('''SELECT id,name,kind,country,notes,version,
                (SELECT count(*) FROM organization_links l WHERE l.organization_id=o.id) AS opportunities,
                (SELECT count(*) FROM organization_links l JOIN opportunities p ON p.id=l.opportunity_id
                    WHERE l.organization_id=o.id AND p.status IN ('GAGNE','EN_MISSION','TERMINE')) AS won_opportunities
                FROM organizations o WHERE instr(name_key,?)>0 ORDER BY name_key,id LIMIT 25 OFFSET ?''', (q,(page-1)*25))]
        return h.json_response(200, {'items':items,'total':total,'page':page})
    try:
        length = int(h.headers.get('Content-Length','0'))
        if not 0 < length <= 8000 or h.headers.get_content_type() != 'application/json': raise ValueError()
        data = json.loads(h.rfile.read(length))
        if not isinstance(data,dict): raise ValueError()
        version = data.pop('version',None)
        if set(data) != set(FIELDS) or any(not isinstance(data[k],str) or len(data[k])>limit or '\x00' in data[k] for k,limit in FIELDS.items()): raise ValueError()
        name,kind,country,notes = (data[k].strip() for k in FIELDS)
        if not name or kind not in KINDS: raise ValueError()
        if method == 'PATCH' and (type(version) is not int or version < 1): raise ValueError()
        if method == 'POST' and version is not None: raise ValueError()
    except (ValueError,TypeError,UnicodeError):
        return h.json_response(400, {'error':'Champs invalides.'})
    key = ' '.join(name.casefold().split())
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        oid = str(uuid.uuid4()) if method == 'POST' else h.path.rsplit('/',1)[-1]
        if method == 'PATCH':
            row = db.execute('SELECT version,kind FROM organizations WHERE id=?',(oid,)).fetchone()
            if not row: return h.json_response(404,{'error':'Organisation introuvable.'})
            if row[0] != version: return h.json_response(409,{'error':'Dossier modifié. Actualisez.'})
            if row[1] == 'PROSPECT' and kind == 'CLIENT':
                return h.json_response(409,{'error':'Utilisez l’action Convertir en client.'})
        if db.execute('SELECT 1 FROM organizations WHERE name_key=? AND id<>?',(key,oid)).fetchone():
            return h.json_response(409,{'error':'Organisation déjà enregistrée.'})
        if method == 'POST':
            version = 1
            db.execute('INSERT INTO organizations(id,name,name_key,kind,country,notes) VALUES(?,?,?,?,?,?)',(oid,name,key,kind,country,notes))
        else:
            version += 1
            db.execute('UPDATE organizations SET name=?,name_key=?,kind=?,country=?,notes=?,version=? WHERE id=?',(name,key,kind,country,notes,version,oid))
    return h.json_response(201 if method=='POST' else 200,{'id':oid,'version':version})


def convert(h, connect, oid):
    """Explicit promotion of an existing prospect; no duplicate client or contract."""
    if not h.admin_authorized(): return
    if h.headers.get('Sec-Fetch-Site') == 'cross-site' or (h.headers.get('Origin') and h.headers['Origin'] != h.expected_origin()):
        return h.json_response(403, {'error':'Origine non autorisée.'})
    try:
        length = int(h.headers.get('Content-Length','0'))
        if not 0 < length <= 1000 or h.headers.get_content_type() != 'application/json': raise ValueError()
        data = json.loads(h.rfile.read(length))
        if not isinstance(data,dict) or set(data) != {'version'} or type(data['version']) is not int or data['version'] < 1: raise ValueError()
    except (ValueError,TypeError,UnicodeError):
        return h.json_response(400, {'error':'Version invalide.'})
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT kind,version FROM organizations WHERE id=?',(oid,)).fetchone()
        if not row: return h.json_response(404, {'error':'Organisation introuvable.'})
        if row[1] != data['version']: return h.json_response(409, {'error':'Dossier modifié. Actualisez.'})
        if row[0] != 'PROSPECT': return h.json_response(409, {'error':'Seul un prospect peut être converti.'})
        won = db.execute('''SELECT p.id FROM organization_links l JOIN opportunities p ON p.id=l.opportunity_id
            WHERE l.organization_id=? AND p.status IN ('GAGNE','EN_MISSION','TERMINE') ORDER BY p.id LIMIT 1''',(oid,)).fetchone()
        if not won: return h.json_response(409, {'error':'Une opportunité gagnée associée est requise.'})
        version = row[1]+1
        db.execute("UPDATE organizations SET kind='CLIENT',version=? WHERE id=?",(version,oid))
        db.execute('INSERT INTO organization_conversions(organization_id,opportunity_id,version,actor) VALUES(?,?,?,?)',(oid,won[0],version,h.actor))
        accounts.event(db,h.actor,'PROSPECT_CONVERTI',oid)
    return h.json_response(200, {'id':oid,'kind':'CLIENT','version':version})
