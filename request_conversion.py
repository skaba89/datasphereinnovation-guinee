"""Trace a qualified intake through the existing CRM, estimates and missions."""
import uuid
import crm
import accounts


def schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS request_opportunities (
        request_id TEXT PRIMARY KEY REFERENCES requests(id),
        opportunity_id TEXT NOT NULL UNIQUE REFERENCES opportunities(id),
        actor TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")


def read(db, rid):
    row = db.execute("""SELECT l.opportunity_id,o.title,o.status,
        (SELECT count(*) FROM quotes q WHERE q.opportunity_id=o.id),
        (SELECT count(*) FROM missions m WHERE m.opportunity_id=o.id)
        FROM request_opportunities l JOIN opportunities o ON o.id=l.opportunity_id
        WHERE l.request_id=?""",(rid,)).fetchone()
    return dict(zip(('opportunity_id','title','status','quotes','missions'),row)) if row else None


def convert(db, rid, actor):
    existing = read(db,rid)
    if existing:
        return existing, False
    row=db.execute("SELECT nom,org,email,besoin,solution,status FROM requests WHERE id=?",(rid,)).fetchone()
    if not row:
        raise LookupError()
    name,company,email,need,solution,status=row
    if status!='QUALIFIEE' or need=='Candidature spontanée':
        raise ValueError()
    values=crm.validate(dict(company=company,contact=name,email=email,
        title=(need+(' — '+solution if solution else ''))[:180],
        mode={'Mission en régie':'REGIE','Projet au forfait':'FORFAIT'}.get(need,'CONSEIL'),
        skills='',consultant_id='',next_action='Prendre contact et cadrer le besoin',
        followup='',notes='Demande source : '+rid,status='QUALIFIE'))
    oid=str(uuid.uuid4())
    db.execute("INSERT INTO opportunities(id,"+",".join(values)+") VALUES("+",".join("?" for _ in range(len(values)+1))+")",(oid,*values.values()))
    db.execute("INSERT INTO opportunity_events(opportunity_id,status,version) VALUES (?,?,1)",(oid,'QUALIFIE'))
    # Reuse exact normalized organization names; never overwrite existing records.
    key=' '.join(company.casefold().split())
    org=db.execute('SELECT id FROM organizations WHERE name_key=?',(key,)).fetchone()
    if org:
        org_id=org[0]
    else:
        org_id=str(uuid.uuid4())
        db.execute("INSERT INTO organizations(id,name,name_key,kind,country,notes) VALUES (?,?,?,'PROSPECT','','')",(org_id,company,key))
    db.execute("INSERT INTO organization_links VALUES (?,?)",(oid,org_id))
    db.execute("INSERT INTO request_opportunities(request_id,opportunity_id,actor) VALUES (?,?,?)",(rid,oid,actor))
    accounts.event(db,actor,'DEMANDE_CONVERTIE',rid)
    return read(db,rid), True


def handle(h,connect,rid):
    if not h.admin_authorized():
        return
    if h.role not in ('ADMIN','COMMERCIAL'):
        return h.json_response(403,{'error':'Permission insuffisante.'})
    try:
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            result,created=convert(db,rid,h.actor)
    except LookupError:
        return h.json_response(404,{'error':'Demande introuvable.'})
    except ValueError:
        return h.json_response(409,{'error':'Seule une demande commerciale qualifiée peut être convertie.'})
    return h.json_response(201 if created else 200,result)
