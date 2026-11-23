"""Global search for the professional space (CRM permission, read-only).

Organizations and opportunities are always searched; requests and quotes only when the
role may already read those modules. Results are short labels with a module link.
"""
import sqlite3
import unicodedata
from urllib.parse import parse_qs, urlsplit

import accounts

PER_KIND = 5


def fold(value):
    text = unicodedata.normalize('NFKD', value or '')
    return ' '.join(''.join(c for c in text if not unicodedata.combining(c)).casefold().split())


def search(db, q, can):
    db.row_factory = sqlite3.Row
    # SQLite lower() is ASCII-only: fold case and accents in Python so "ENERGIE" finds "Énergie".
    db.create_function('fold', 1, fold, deterministic=True)
    needle = fold(q)
    results = []
    for r in db.execute('''SELECT id,name,kind FROM organizations WHERE instr(fold(name_key),?)>0
            ORDER BY name_key LIMIT ?''', (needle, PER_KIND)):
        results.append({'kind': 'ORGANISATION', 'label': r['name'], 'detail': r['kind'], 'url': 'client.html?id=' + r['id']})
    for r in db.execute('''SELECT o.id,o.company,o.title,o.status,l.organization_id FROM opportunities o
            LEFT JOIN organization_links l ON l.opportunity_id=o.id
            WHERE instr(fold(o.company),?)>0 OR instr(fold(o.title),?)>0 OR instr(fold(o.email),?)>0 OR instr(fold(o.contact),?)>0
            ORDER BY o.rowid DESC LIMIT ?''', (needle, needle, needle, needle, PER_KIND)):
        url = 'client.html?id=' + r['organization_id'] if r['organization_id'] else 'crm.html#kanban'
        results.append({'kind': 'OPPORTUNITE', 'label': r['company'] + ' · ' + r['title'], 'detail': r['status'], 'url': url})
    if can['requests']:
        for r in db.execute('''SELECT org,besoin,status,created_at FROM requests
                WHERE instr(fold(org),?)>0 OR instr(fold(nom),?)>0 OR instr(fold(email),?)>0
                ORDER BY created_at DESC LIMIT ?''', (needle, needle, needle, PER_KIND)):
            results.append({'kind': 'DEMANDE', 'label': r['org'] + ' · ' + r['besoin'],
                            'detail': r['status'] + ' · ' + r['created_at'][:10], 'url': 'admin.html'})
    if can['quotes']:
        for r in db.execute('''SELECT q.title,q.status,o.company FROM quotes q JOIN opportunities o ON o.id=q.opportunity_id
                WHERE instr(fold(q.title),?)>0 OR instr(fold(o.company),?)>0 ORDER BY q.rowid DESC LIMIT ?''',
                            (needle, needle, PER_KIND)):
            results.append({'kind': 'DEVIS', 'label': r['company'] + ' · ' + r['title'], 'detail': r['status'], 'url': 'quotes.html'})
    return results


def handle(h, connect):
    if not h.admin_authorized():
        return
    query = parse_qs(urlsplit(h.path).query)
    q = ' '.join(query.get('q', [''])[0].split())
    if len(q) < 2 or len(q) > 80 or '\x00' in q:
        return h.json_response(400, {'error': 'Saisissez entre 2 et 80 caractères.'})
    can = {r: accounts.allowed(h.role, r, 'GET') for r in ('requests', 'quotes')}
    with connect() as db:
        results = search(db, q, can)
    return h.json_response(200, {'query': q, 'items': results})
