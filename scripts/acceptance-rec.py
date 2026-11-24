#!/usr/bin/env python3
"""Automated REC business acceptance (V177): runs the main scenarios through the HTTP API.

Run by the operator ON THE VPS, never with real data:
    DSIG_ADMIN_TOKEN="$(docker exec dsig-rec-dsig-1 printenv DSIG_ADMIN_TOKEN)" \
        python3 scripts/acceptance-rec.py --base https://rec.dsig-consulting.com

What it does (fictitious data tagged RECETTE-AUTO, one public submission only):
  1. public form (type Formation, phone) -> request stored, automatic CRM prospect
  2. global search finds the organisation
  3. commercial task: create, postpone, complete
  4. quote -> PDF (client amounts only, no internal cost), weekly report JSON/CSV
  5. commercial email: template preview and history
  6. protected APIs refuse anonymous calls
  7. right to erasure on the fictitious request (cleans its personal-like data)
The output never contains the token. Exit code 0 only if every step passes.
Notes: the acknowledgement email of step 1 goes through the REC mail queue (test mailbox rules).
Nothing here authorises production.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import zlib
from datetime import date, timedelta


class Client:
    def __init__(self, base, token):
        self.base, self.token = base.rstrip('/'), token

    def call(self, method, path, payload=None, auth=True, origin=False, raw=False):
        headers = {'User-Agent': 'DSIG-REC-acceptance/1.0'}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
            headers['Content-Type'] = 'application/json'
        if auth:
            headers['Authorization'] = 'Bearer ' + self.token
        if origin:
            headers['Origin'] = self.base
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                body = response.read()
                status = response.status
        except urllib.error.HTTPError as error:
            body, status = error.read(), error.code
        if raw:
            return status, body
        try:
            return status, json.loads(body or b'null')
        except ValueError:
            return status, None


def pdf_text(pdf):
    return b'\n'.join(zlib.decompress(s) for s in re.findall(rb'stream\n(.*?)\nendstream', pdf, re.S)).decode('cp1252', 'replace')


def run(client, today=None):
    today = today or date.today()
    tag = 'RECETTE-AUTO ' + time.strftime('%Y%m%d%H%M%S')
    org, email = tag + ' Org', 'recette-auto-' + time.strftime('%Y%m%d%H%M%S') + '@example.invalid'
    results, state = [], {}

    def step(name, check):
        try:
            detail = check()
            results.append({'step': name, 'status': 'PASS', 'detail': detail})
            return True
        except Exception as error:  # report and continue: every failure is listed
            results.append({'step': name, 'status': 'FAIL', 'detail': str(error)[:200]})
            return False

    def expect(condition, message):
        if not condition:
            raise AssertionError(message)

    def form():
        status, body = client.call('POST', '/api/requests', {
            'nom': 'Contact ' + tag, 'org': org, 'email': email, 'telephone': '+224 620 00 00 00', 'besoin': 'Formation',
            'solution': '', 'message': 'Demande fictive de recette automatique.', 'consent': True, 'website': '', 'language': 'fr'},
            auth=False, origin=True)
        expect(status == 201, f'formulaire: HTTP {status}')
        state['request'] = body['id']
        status, listing = client.call('GET', '/api/admin/requests?q=' + urllib.request.quote(org))
        expect(status == 200, f'liste des demandes: HTTP {status}')
        item = next((x for x in listing['items'] if x['id'] == state['request']), None)
        expect(item and item['telephone'] == '+224 620 00 00 00' and item['besoin'] == 'Formation', 'demande ou téléphone introuvable')
        status, tasks = client.call('GET', '/api/admin/crm/tasks?view=team')
        expect(status == 200, f'opportunités: HTTP {status}')
        opp = next((o for o in tasks['opportunities'] if o['company'] == org), None)
        expect(opp, 'prospect CRM automatique introuvable')
        state['opportunity'] = opp['id']
        return 'demande + prospect automatique créés'

    def search():
        status, body = client.call('GET', '/api/admin/crm/search?q=' + urllib.request.quote(tag))
        expect(status == 200 and any(org in item['label'] for item in body['items']), 'organisation absente de la recherche')
        return f"{len(body['items'])} résultat(s)"

    def task():
        status, body = client.call('POST', '/api/admin/crm/tasks', {'title': 'Appeler ' + tag, 'kind': 'APPEL', 'due_date': today.isoformat(),
                                                                     'opportunity_id': state['opportunity'], 'owner_id': ''})
        expect(status == 201, f'création: HTTP {status}')
        tid = body['id']
        expect(client.call('PATCH', '/api/admin/crm/tasks/' + tid, {'due_date': (today + timedelta(days=1)).isoformat(), 'version': 1})[0] == 200, 'report')
        expect(client.call('PATCH', '/api/admin/crm/tasks/' + tid, {'status': 'FAIT', 'version': 2})[0] == 200, 'clôture')
        expect(client.call('PATCH', '/api/admin/crm/tasks/' + tid, {'status': 'FAIT', 'version': 2})[0] == 409, 'verrou de version')
        return 'créée, reportée, terminée, verrou OK'

    def quote_pdf():
        status, body = client.call('POST', '/api/admin/quotes', {
            'opportunity_id': state['opportunity'], 'title': 'Devis ' + tag, 'scope': 'Périmètre fictif.', 'mode': 'REGIE', 'currency': 'EUR',
            'days': '5', 'rate': '600', 'daily_cost': '377', 'expenses': '0', 'fixed_price': '0', 'status': 'BROUILLON'})
        expect(status == 201, f'devis: HTTP {status}')
        status, pdf = client.call('GET', f"/api/admin/quotes/{body['id']}/pdf", raw=True)
        expect(status == 200 and pdf.startswith(b'%PDF-1.4'), f'PDF: HTTP {status}')
        text = pdf_text(pdf)
        expect('3 000,00 EUR' in text and 'RECETTE' in text, 'montant ou filigrane absent du PDF')
        expect('377' not in text, 'coût interne présent dans le PDF')
        return f'PDF {len(pdf)} octets, sans coût interne'

    def report():
        status, body = client.call('GET', '/api/admin/direction/weekly-report')
        expect(status == 200 and 'pipeline' in body, f'rapport JSON: HTTP {status}')
        status, csv = client.call('GET', '/api/admin/direction/weekly-report?format=csv', raw=True)
        expect(status == 200 and csv.decode('utf-8-sig').startswith('Section;Indicateur;Valeur'), f'rapport CSV: HTTP {status}')
        return f"semaine {body['week']}"

    def emails():
        status, body = client.call('GET', '/api/admin/crm/email-templates')
        expect(status == 200 and body['items'], f'modèles: HTTP {status}')
        template = next(t for t in body['items'] if t['code'] == 'RELANCE' and t['language'] == 'fr')
        status, preview = client.call('POST', '/api/admin/crm/emails/preview', {'opportunity_id': state['opportunity'], 'template_id': template['id']})
        expect(status == 200 and preview['to'] == email, f'aperçu: HTTP {status}')
        status, _ = client.call('POST', '/api/admin/crm/emails', {'opportunity_id': state['opportunity'], 'template_id': template['id'],
                                                                 'subject': preview['subject'], 'body': preview['body']})
        expect(status == 201, f'enregistrement: HTTP {status}')
        status, history = client.call('GET', '/api/admin/crm/emails?opportunity_id=' + state['opportunity'])
        expect(status == 200 and len(history['items']) == 1, 'historique')
        return 'aperçu + historique OK (aucun envoi par la plateforme)'

    def permissions():
        paths = ('/api/admin/requests', '/api/admin/crm/tasks', '/api/admin/crm/email-templates', '/api/admin/direction/weekly-report', '/api/admin/crm/search?q=ab')
        refused = {p: client.call('GET', p, auth=False)[0] for p in paths}
        expect(all(code == 401 for code in refused.values()), f'accès anonyme: {refused}')
        return f'{len(paths)} API refusées sans authentification'

    def erasure():
        status, body = client.call('POST', f"/api/admin/requests/{state['request']}/erase", {})
        expect(status == 200 and body['status'] == 'ANONYMISEE', f'effacement: HTTP {status}')
        # Strict check: the request must be found as anonymised, and no longer findable by its email.
        status, listing = client.call('GET', '/api/admin/requests?page_size=50&besoin=Formation&q=' + urllib.request.quote('[supprimé]'))
        item = next((x for x in (listing or {}).get('items', []) if x['id'] == state['request']), None)
        expect(status == 200 and item is not None, 'demande anonymisée introuvable')
        expect(item['email'] == '' and item.get('telephone') == '' and item['nom'] == '[supprimé]', 'données personnelles encore présentes')
        status, listing = client.call('GET', '/api/admin/requests?q=' + urllib.request.quote(email))
        expect(status == 200 and not any(x['id'] == state['request'] for x in listing['items']), 'encore retrouvable par e-mail')
        expect(client.call('POST', f"/api/admin/requests/{state['request']}/erase", {})[1].get('status') == 'DEJA_ANONYMISEE', 'idempotence')
        return 'demande fictive anonymisée (idempotent)'

    if step('1. Formulaire → demande + prospect CRM', form):
        step('2. Recherche globale', search)
        step('3. Tâche commerciale', task)
        step('4a. Devis PDF sans coût interne', quote_pdf)
        step('5. E-mail commercial (modèle)', emails)
        step('7. Droit à l’effacement', erasure)
    step('4b. Rapport hebdomadaire JSON/CSV', report)
    step('6. Protection des API', permissions)
    status = 'PASS' if all(r['status'] == 'PASS' for r in results) else 'FAIL'
    return {'status': status, 'tag': tag, 'steps': results, 'production_authorized': False,
            'manual_checks': ['téléphone : menu, barre de raccourcis, écran d’accueil', 'connexion MFA DIRECTION (lecture seule)']}


def main(argv=None):
    parser = argparse.ArgumentParser(description='DSIG REC automated acceptance (fictitious data)')
    parser.add_argument('--base', default='https://rec.dsig-consulting.com')
    args = parser.parse_args(argv)
    token = os.environ.get('DSIG_ADMIN_TOKEN', '')
    if len(token) < 32:
        print('DSIG_ADMIN_TOKEN manquant (lu dans le conteneur REC, jamais affiché).', file=sys.stderr)
        return 2
    if not re.fullmatch(r'https://rec\.dsig-consulting\.com|http://127\.0\.0\.1:\d+', args.base):
        print('Base refusée : REC ou test local uniquement.', file=sys.stderr)
        return 2
    report = run(Client(args.base, token))
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
