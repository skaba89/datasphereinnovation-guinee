"""Commercial email templates and prepared emails (logged in the client history).

Emails are not sent by the platform: the commercial opens the prepared message in their
own mailbox (mailto link). Templates use a fixed set of placeholders; unknown placeholders
are rejected when a template is saved. Templates are managed by ADMIN only.
"""
import json
import re
import sqlite3
import uuid
from urllib.parse import parse_qs, urlsplit

import accounts

FIELDS = ('contact', 'societe', 'opportunite', 'commercial')
PLACEHOLDER = re.compile(r'\{([a-z]+)\}')
LANGUAGES = ('fr', 'en')

DEFAULTS = (
    ('PRESENTATION', 'fr', 'Présentation DSIG', 'DSIG — Présentation de nos expertises pour {societe}',
     'Bonjour {contact},\n\nSuite à notre échange, je vous présente brièvement DataSphere Innovation Guinée : conseil en data, intelligence artificielle, BI, cybersécurité et transformation digitale.\n\nSeriez-vous disponible pour un échange de 30 minutes afin de préciser vos besoins concernant « {opportunite} » ?\n\nBien cordialement,\n{commercial}\nDSIG Consulting'),
    ('PRESENTATION', 'en', 'DSIG introduction', 'DSIG — Our expertise for {societe}',
     'Hello {contact},\n\nFollowing our conversation, here is a short introduction to DataSphere Innovation Guinée: data, artificial intelligence, BI, cybersecurity and digital transformation consulting.\n\nWould you be available for a 30-minute call to clarify your needs regarding "{opportunite}"?\n\nBest regards,\n{commercial}\nDSIG Consulting'),
    ('ENVOI_DEVIS', 'fr', 'Envoi de proposition', 'DSIG — Notre proposition : {opportunite}',
     'Bonjour {contact},\n\nVeuillez trouver ci-joint notre proposition pour « {opportunite} ».\n\nJe reste à votre disposition pour en parler et l’ajuster si nécessaire.\n\nBien cordialement,\n{commercial}\nDSIG Consulting'),
    ('ENVOI_DEVIS', 'en', 'Proposal', 'DSIG — Our proposal: {opportunite}',
     'Hello {contact},\n\nPlease find attached our proposal for "{opportunite}".\n\nI remain available to discuss it and adjust it if needed.\n\nBest regards,\n{commercial}\nDSIG Consulting'),
    ('RELANCE', 'fr', 'Relance', 'DSIG — Suite à notre échange : {opportunite}',
     'Bonjour {contact},\n\nJe me permets de revenir vers vous au sujet de « {opportunite} ». Avez-vous pu avancer sur ce sujet ? Je peux vous proposer un court point téléphonique si cela vous aide.\n\nBien cordialement,\n{commercial}\nDSIG Consulting'),
    ('RELANCE', 'en', 'Follow-up', 'DSIG — Following up: {opportunite}',
     'Hello {contact},\n\nI am following up regarding "{opportunite}". Have you been able to move forward? I would be happy to arrange a short call if that helps.\n\nBest regards,\n{commercial}\nDSIG Consulting'),
)


def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS email_templates (
        id TEXT PRIMARY KEY, code TEXT NOT NULL, language TEXT NOT NULL, name TEXT NOT NULL,
        subject TEXT NOT NULL, body TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
        version INTEGER NOT NULL DEFAULT 1, updated_by TEXT NOT NULL DEFAULT 'systeme',
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    db.execute('''CREATE TABLE IF NOT EXISTS crm_email_log (
        id TEXT PRIMARY KEY, opportunity_id TEXT NOT NULL, template_id TEXT NOT NULL,
        recipient TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL, actor TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    db.execute('CREATE INDEX IF NOT EXISTS crm_email_log_opportunity ON crm_email_log(opportunity_id,created_at)')
    if not db.execute('SELECT 1 FROM email_templates LIMIT 1').fetchone():
        db.executemany('INSERT INTO email_templates(id,code,language,name,subject,body) VALUES (?,?,?,?,?,?)',
                       [(str(uuid.uuid4()), *t) for t in DEFAULTS])


def _text(value, limit, multiline=False):
    if not isinstance(value, str) or not 0 < len(value.strip()) <= limit or '\x00' in value:
        raise ValueError()
    if any(ord(c) < 32 and not (multiline and c in '\n\r\t') for c in value):
        raise ValueError()
    return value.strip().replace('\r\n', '\n')


def check_placeholders(text):
    unknown = set(PLACEHOLDER.findall(text)) - set(FIELDS)
    if unknown or text.count('{') != text.count('}'):
        raise ValueError()
    return text


def render(text, values):
    return PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), text)


def _template_values(v):
    if set(v) - {'name', 'subject', 'body', 'language', 'active', 'version', 'code'}:
        raise ValueError()
    out = {'name': _text(v['name'], 120), 'subject': check_placeholders(_text(v['subject'], 200)),
           'body': check_placeholders(_text(v['body'], 4000, True))}
    if v.get('language') not in LANGUAGES or type(v.get('active', True)) is not bool:
        raise ValueError()
    out['language'], out['active'] = v['language'], int(v.get('active', True))
    return out


def _context(db, opportunity_id, actor):
    o = db.execute('SELECT company,contact,email,title FROM opportunities WHERE id=?', (opportunity_id,)).fetchone()
    if not o:
        raise LookupError()
    return o[2], {'contact': o[1] or o[0], 'societe': o[0], 'opportunite': o[3], 'commercial': actor}


def history(db, opportunity_ids):
    if not opportunity_ids:
        return []
    marks = ','.join('?' * len(opportunity_ids))
    db.row_factory = sqlite3.Row
    return [dict(r) for r in db.execute(f'''SELECT l.id,l.opportunity_id,l.subject,l.recipient,l.actor,l.created_at,t.name AS template
        FROM crm_email_log l LEFT JOIN email_templates t ON t.id=l.template_id
        WHERE l.opportunity_id IN ({marks}) ORDER BY l.created_at DESC,l.rowid DESC LIMIT 50''', opportunity_ids)]


def _body(h, limit=12000):
    n = int(h.headers.get('Content-Length', '0'))
    if not 0 < n <= limit or h.headers.get_content_type() != 'application/json':
        raise ValueError()
    v = json.loads(h.rfile.read(n))
    if not isinstance(v, dict):
        raise ValueError()
    return v


def handle(h, connect, method):
    """Routes under /api/admin/crm/email-templates[/<id>] and /api/admin/crm/emails[/preview]."""
    if not h.admin_authorized():
        return
    path = urlsplit(h.path).path
    templates = path.startswith('/api/admin/crm/email-templates')
    try:
        if method == 'GET' and templates:
            manage = h.role == 'ADMIN'
            with connect() as db:
                db.row_factory = sqlite3.Row
                rows = [dict(r) for r in db.execute('SELECT id,code,language,name,subject,body,active,version,updated_by,updated_at FROM email_templates'
                                                    + ('' if manage else ' WHERE active=1') + ' ORDER BY code,language,name')]
            return h.json_response(200, {'items': rows, 'fields': FIELDS, 'can_manage': manage,
                                         'can_compose': accounts.allowed(h.role, 'crm', 'POST')})
        if method == 'GET':
            query = parse_qs(urlsplit(h.path).query)
            oid = query.get('opportunity_id', [''])[0]
            if set(query) != {'opportunity_id'} or not re.fullmatch(r'[0-9a-f-]{36}', oid):
                raise ValueError()
            with connect() as db:
                return h.json_response(200, {'items': history(db, [oid])})
        if templates:
            if h.role != 'ADMIN':
                return h.json_response(403, {'error': 'Gestion des modèles réservée aux administrateurs.'})
            v = _body(h)
            with connect() as db:
                db.execute('BEGIN IMMEDIATE')
                if method == 'POST':
                    values = _template_values(v)
                    code = v.get('code', 'PERSONNALISE')
                    if not isinstance(code, str) or not re.fullmatch(r'[A-Z_]{2,30}', code):
                        raise ValueError()
                    tid = str(uuid.uuid4())
                    db.execute('INSERT INTO email_templates(id,code,language,name,subject,body,active,updated_by) VALUES (?,?,?,?,?,?,?,?)',
                               (tid, code, values['language'], values['name'], values['subject'], values['body'], values['active'], h.actor))
                    accounts.event(db, h.actor, 'MODELE_EMAIL_CREE', tid)
                else:
                    tid = path.rsplit('/', 1)[-1]
                    if type(v.get('version')) is not int or 'code' in v:
                        raise ValueError()
                    values = _template_values(v)
                    if not db.execute('SELECT 1 FROM email_templates WHERE id=?', (tid,)).fetchone():
                        raise LookupError()
                    if db.execute('''UPDATE email_templates SET name=?,subject=?,body=?,language=?,active=?,updated_by=?,
                            updated_at=CURRENT_TIMESTAMP,version=version+1 WHERE id=? AND version=?''',
                                  (values['name'], values['subject'], values['body'], values['language'], values['active'],
                                   h.actor, tid, v['version'])).rowcount != 1:
                        raise sqlite3.IntegrityError()
                    accounts.event(db, h.actor, 'MODELE_EMAIL_MODIFIE', tid)
            return h.json_response(201 if method == 'POST' else 200, {'id': tid})
        # Compose: preview (no log) or record a prepared email.
        v = _body(h)
        preview = path.endswith('/preview')
        expected = {'opportunity_id', 'template_id'} | (set() if preview else {'subject', 'body'})
        if set(v) != expected or not all(isinstance(v[k], str) for k in expected):
            raise ValueError()
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            template = db.execute('SELECT subject,body FROM email_templates WHERE id=? AND active=1', (v['template_id'],)).fetchone()
            if not template:
                raise ValueError()
            recipient, values = _context(db, v['opportunity_id'], h.actor)
            if not recipient:
                return h.json_response(409, {'error': 'Aucune adresse e-mail sur cette opportunité.'})
            if preview:
                return h.json_response(200, {'to': recipient, 'subject': render(template[0], values), 'body': render(template[1], values)})
            subject, body = _text(v['subject'], 200), _text(v['body'], 4000, True)
            lid = str(uuid.uuid4())
            db.execute('INSERT INTO crm_email_log(id,opportunity_id,template_id,recipient,subject,body,actor) VALUES (?,?,?,?,?,?,?)',
                       (lid, v['opportunity_id'], v['template_id'], recipient, subject, body, h.actor))
            accounts.event(db, h.actor, 'EMAIL_COMMERCIAL_PREPARE', v['opportunity_id'])
        return h.json_response(201, {'id': lid, 'to': recipient, 'subject': subject, 'body': body})
    except (ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError):
        return h.json_response(400, {'error': 'Modèle ou message invalide.'})
    except LookupError:
        return h.json_response(404, {'error': 'Élément introuvable.'})
    except sqlite3.IntegrityError:
        return h.json_response(409, {'error': 'Modèle modifié entre-temps. Actualisez.'})
