"""Browser acceptance tests: isolated loopback server and fictitious records."""
import json
import os
import re
import tempfile
import threading
import time
import unittest
import subprocess
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from playwright.sync_api import sync_playwright, expect
import server


class PublicExportBrowserTests(unittest.TestCase):
    def test_export_styles_and_deferred_menu(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / 'public'
            subprocess.run(['node', 'scripts/build-public-site.mjs', str(site),
                            'contact@dsig-consulting.com'], check=True,
                           cwd=Path(__file__).resolve().parent)
            # Serve the export with the exact CSP of the public image (deploy/public/Caddyfile).
            caddyfile = (Path(__file__).resolve().parent / 'deploy' / 'public' / 'Caddyfile').read_text(encoding='utf-8')
            policy = re.search(r'Content-Security-Policy "([^"]+)"', caddyfile).group(1)
            class PublicHandler(SimpleHTTPRequestHandler):
                def end_headers(self):
                    self.send_header('Content-Security-Policy', policy)
                    super().end_headers()
            http = ThreadingHTTPServer(('127.0.0.1', 0), partial(PublicHandler, directory=site))
            thread = threading.Thread(target=http.serve_forever, daemon=True)
            thread.start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    page = browser.new_page(viewport={'width':390,'height':844})
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    violations = []
                    page.on('console', lambda message: violations.append(message.text) if 'Content Security Policy' in message.text else None)
                    for route in ('/', '/en.html', '/secteurs-mines.html', '/blog.html', '/expertise-data-engineering.html'):
                        with self.subTest(route=route):
                            response = page.goto(f'http://127.0.0.1:{http.server_port}{route}')
                            self.assertEqual(response.status, 200)
                            expect(page.locator('h1')).to_be_visible()
                            self.assertEqual(page.evaluate('document.styleSheets.length'), 1)
                            self.assertGreater(page.evaluate('document.styleSheets[0].cssRules.length'), 0)
                            if route in ('/', '/en.html'):
                                expect(page.locator('[data-icon] svg').first).to_be_attached()
                                page.locator('#menu').click()
                                expect(page.locator('#menu')).to_have_attribute('aria-expanded', 'true')
                                page.keyboard.press('Escape')
                                expect(page.locator('#menu')).to_have_attribute('aria-expanded', 'false')
                    # V161: legal and privacy notices reachable from the footer, responsive, explicit pending state.
                    for home, label, route in (('/', 'Mentions légales', '/mentions-legales.html'), ('/en.html', 'Legal notice', '/legal-en.html'),
                                               ('/', 'Confidentialité', '/confidentialite.html'), ('/en.html', 'Privacy notice', '/privacy-en.html')):
                        with self.subTest(route=route):
                            page.goto(f'http://127.0.0.1:{http.server_port}{home}')
                            page.locator('footer').get_by_role('link', name=label, exact=True).click()
                            page.wait_for_url(f'**{route}')
                            expect(page.locator('h1')).to_have_count(1)
                            expect(page.locator('[role=note]')).to_be_visible()
                            self.assertEqual(page.locator('meta[name=robots]').get_attribute('content'), 'noindex,nofollow')
                            self.assertEqual(page.evaluate('document.styleSheets.length'), 1)
                            for width in (360, 768, 1280):
                                page.set_viewport_size({'width':width,'height':900})
                                self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), f'{route} overflow at {width}px')
                            page.set_viewport_size({'width':390,'height':844})
                    self.assertEqual(errors, [])
                    self.assertEqual(violations, [])
                    browser.close()
            finally:
                http.shutdown()
                thread.join()
                http.server_close()


class PublicContactFormBrowserTests(unittest.TestCase):
    """V175: public form (built with test-only validated legal data) against a mocked /api/contact."""
    def test_public_form_submission_states(self):
        root = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / 'public'
            helper = Path(tmp) / 'build-form.mjs'
            helper.write_text('\n'.join((
                "import {build} from " + json.dumps((root / 'scripts' / 'build-public-site.mjs').as_uri()) + ";",
                "import {legalFields} from " + json.dumps((root / 'scripts' / 'legal-content.mjs').as_uri()) + ";",
                "const fields=legalFields.map(f=>({...f,value:'Valeur validée '+f.id,confirmed:true,source:'Pièce de recette',validatedBy:'Validateur de recette'}));",
                "build(process.argv[2],'contact@dsig-consulting.com',{form:true,fields});",
            )), encoding='utf-8')
            subprocess.run(['node', str(helper), str(site)], check=True, cwd=root)
            caddy = subprocess.run(['node', 'scripts/public-caddyfile.mjs', 'deploy/public/Caddyfile', 'enabled'], check=True, cwd=root,
                                   capture_output=True, text=True).stdout
            policy = re.search(r'Content-Security-Policy "([^"]+)"', caddy).group(1)
            class PublicHandler(SimpleHTTPRequestHandler):
                def end_headers(self):
                    self.send_header('Content-Security-Policy', policy)
                    super().end_headers()
            http = ThreadingHTTPServer(('127.0.0.1', 0), partial(PublicHandler, directory=site))
            thread = threading.Thread(target=http.serve_forever, daemon=True)
            thread.start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    page = browser.new_page(viewport={'width':390,'height':844})
                    errors, violations, calls = [], [], []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.on('console', lambda m: violations.append(m.text) if 'Content Security Policy' in m.text else None)
                    replies = []
                    def api(route):
                        calls.append(json.loads(route.request.post_data))
                        status, body = replies.pop(0)
                        route.fulfill(status=status, content_type='application/json', body=json.dumps(body))
                    page.route('**/api/contact', api)
                    page.goto(f'http://127.0.0.1:{http.server_port}/')
                    form = page.locator('#request')
                    status = page.locator('#request-status')
                    # Client-side validation: nothing is sent.
                    form.locator('[type=submit]').click()
                    expect(status).to_have_text('Vérifiez les champs signalés.')
                    self.assertEqual(calls, [])
                    for name, value in {'nom':'Visiteur fictif','org':'Org fictive','email':'visiteur@example.invalid','telephone':'+224 620 00 00 00','message':'Demande fictive'}.items():
                        form.locator(f'[name={name}]').fill(value)
                    form.locator('[name=besoin]').select_option('Formation')
                    form.locator('[name=consent]').check()
                    replies.append((201, {'id':'ref-1', 'message':'Votre demande a bien été reçue. Référence : ref-1'}))
                    # Double click in the same tick: only one request leaves the browser.
                    page.evaluate("() => { const b = document.querySelector('#request [type=submit]'); b.click(); b.click(); }")
                    expect(status).to_have_text('Votre demande a bien été reçue. Référence : ref-1')
                    self.assertEqual(len(calls), 1)
                    self.assertEqual({k: calls[0][k] for k in ('besoin','telephone','consent','language','website')},
                                     {'besoin':'Formation','telephone':'+224 620 00 00 00','consent':True,'language':'fr','website':''})
                    expect(form.locator('[name=nom]')).to_have_value('')  # reset after success
                    # Server-side refusal and outage: explicit messages, email fallback.
                    for name, value in {'nom':'Visiteur','org':'Org','email':'v@example.invalid','message':'Encore'}.items():
                        form.locator(f'[name={name}]').fill(value)
                    form.locator('[name=consent]').check()
                    replies.append((400, {'error':'Adresse e-mail invalide.'}))
                    form.locator('[type=submit]').click()
                    expect(status).to_have_text('Adresse e-mail invalide.')
                    replies.append((503, {'error':'Le formulaire n’est pas encore ouvert.'}))
                    form.locator('[type=submit]').click()
                    expect(status).to_contain_text('contact@dsig-consulting.com')
                    expect(form.locator('[type=submit]')).to_be_enabled()
                    self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'))
                    page.goto(f'http://127.0.0.1:{http.server_port}/en.html')
                    expect(page.locator('#request [type=submit]')).to_have_text('Send my request')
                    self.assertEqual(errors, [])
                    self.assertEqual(violations, [])
                    browser.close()
            finally:
                http.shutdown()
                http.server_close()
                thread.join()


class BrowserTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {'DSIG_MFA_KEY': Fernet.generate_key().decode(), 'DSIG_MFA_REQUIRED_ROLES': 'DIRECTION,CONTROLE,COMPTABLE,AUDITEUR'})
        env.start(); self.addCleanup(env.stop)
        original = (server.DB, server.ADMIN_TOKEN)
        self.addCleanup(lambda: (setattr(server, 'DB', original[0]), setattr(server, 'ADMIN_TOKEN', original[1])))
        server.DB = Path(self.tmp.name) / 'test.sqlite3'
        server.ADMIN_TOKEN = 'fictional-browser-test-bootstrap-' + 'x'*32
        server.RATE.clear(); server.authentication.ATTEMPTS.clear()
        self.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        thread = threading.Thread(target=self.http.serve_forever, daemon=True); thread.start()
        self.addCleanup(self.http.server_close); self.addCleanup(thread.join); self.addCleanup(self.http.shutdown)
        self.url = f'http://127.0.0.1:{self.http.server_address[1]}'
        self.pw = sync_playwright().start(); self.addCleanup(self.pw.stop)
        executable = os.environ.get('DSIG_TEST_CHROMIUM')
        self.browser = self.pw.chromium.launch(**({'executable_path': executable} if executable else {}))
        self.addCleanup(self.browser.close)
        self.context = self.browser.new_context(base_url=self.url); self.addCleanup(self.context.close)
        self.page = self.context.new_page(); self.errors = []
        self.page.on('pageerror', lambda e: self.errors.append(str(e)))
        self.password = 'fictional-browser-password-123'

    def seed(self, path, payload):
        response = self.context.request.post(path, data=payload, headers={'Authorization': 'Bearer '+server.ADMIN_TOKEN})
        self.assertEqual(response.status, 201, response.text())
        return response.json()

    def activate(self, username, role, consultant_id=''):
        account = self.seed('/api/admin/accounts', {'username': username, 'role': role, 'consultant_id': consultant_id})
        self.page.goto('/connexion.html')
        for name, value in {'username': username, 'key': account['key'], 'password': self.password}.items():
            self.page.locator(f'#activate [name={name}]').fill(value)
        self.page.locator('#activate button').click()
        expect(self.page.locator('#notice')).to_contain_text('Activation effectuée')
        self.login(username)

    def login(self, username, otp=''):
        for name, value in {'username': username, 'password': self.password, 'otp': otp}.items():
            self.page.locator(f'#signin [name={name}]').fill(value)
        self.page.locator('#signin button').click()
        expect(self.page.locator('#workspace')).to_be_visible()

    def assert_responsive(self, page_name):
        for width in (360, 768, 1280):
            with self.subTest(page=page_name, width=width):
                self.page.set_viewport_size({'width':width,'height':900})
                self.page.evaluate('document.fonts.ready')
                self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'),
                                f'{page_name}: horizontal overflow at {width}px')
        self.page.set_viewport_size({'width':1280,'height':900})

    def test_public_pages_responsive(self):
        for path in ('/', '/en.html', '/expertise.html?id=logistique-transport', '/expertise-en.html?id=logistique-transport', '/confidentialite.html', '/privacy-en.html', '/mentions-legales.html', '/legal-en.html', '/connexion.html'):
            with self.subTest(path=path):
                response = self.page.goto(path)
                self.assertEqual(response.status, 200)
                expect(self.page.locator('h1')).to_be_visible()
                self.assert_responsive(path)
        self.assertEqual(self.errors, [])

    def test_public_intake_and_catalogue(self):
        self.page.goto('/')
        expect(self.page.locator('h1')).to_be_visible()
        self.assertNotIn('MineFleet360', self.page.content())
        self.assertNotIn('Guinée Logistique', self.page.content())
        self.assertEqual(self.context.request.get('/api/admin/crm/catalogue').status,401)
        self.assertEqual(self.context.request.get('/catalogue.js').status, 404)
        for name,value in {'nom':'Client fictif','org':'Entreprise fictive','email':'qa@example.invalid','message':'Demande de recette navigateur'}.items():
            self.page.locator(f'#request [name={name}]').fill(value)
        # Issue #156: optional phone / WhatsApp (native validation) and the new request types.
        options=self.page.locator('#need option').evaluate_all('(nodes) => nodes.map(o => o.value)')
        self.assertTrue({'Demande de devis','Formation','Autre demande'} <= set(options), options)
        phone=self.page.locator('#request [name=telephone]')
        expect(phone).to_have_attribute('type','tel')
        phone.fill('abc')
        self.assertFalse(phone.evaluate('el => el.checkValidity()'))
        phone.fill('+224 620 00 00 00')
        self.assertTrue(phone.evaluate('el => el.checkValidity()'))
        self.page.locator('#need').select_option(label='Formation')
        self.page.locator('#request [name=consent]').check()
        self.page.locator('#request [type=submit]').click()
        expect(self.page.locator('#request-status')).to_contain_text('Demande enregistrée localement')
        self.page.goto('/admin.html')
        self.page.locator('#token').fill(server.ADMIN_TOKEN)
        self.page.locator('#login-form button').click()
        expect(self.page.locator('#dashboard')).to_be_visible()
        expect(self.page.locator('#rows')).to_contain_text('+224 620 00 00 00')
        expect(self.page.locator('#rows')).to_contain_text('Accusé de réception')
        expect(self.page.locator('#rows')).to_contain_text('Notification interne')
        expect(self.page.locator('#mail-summary')).to_contain_text('En attente : 2')
        self.assertEqual(self.errors, [])

    def test_browser_prospect_to_paid_contract(self):
        profile = self.seed('/api/admin/consultants', {'name':'Consultant V81 fictif','email':'v81@example.invalid','role':'Data Engineer','skills':'Python','location':'Guinée','experience':'5','availability':'Immédiate','notes':'','status':'DISPONIBLE'})
        def fill(form, values):
            for name, value in values.items():
                self.page.locator(f'{form} [name={name}]').fill(value)
        def module(name, workspace='#workspace'):
            self.page.locator(f'#modules a[href="{name}.html"]').click()
            expect(self.page.locator(workspace)).to_be_visible()
        def logout():
            self.page.goto('/connexion.html')
            expect(self.page.locator('#workspace')).to_be_visible()
            self.page.locator('#logout').click()
            expect(self.page.locator('#login')).to_be_visible()
            server.authentication.ATTEMPTS.clear()

        self.page.goto('/')
        fill('#request', {'nom':'Prospect V81','org':'Client V81 fictif','email':'prospect81@example.invalid','message':'Audit data fictif'})
        self.page.locator('#need').select_option(label='Mission en régie')
        self.page.locator('#request [name=consent]').check()
        self.page.locator('#request [type=submit]').click()
        expect(self.page.locator('#request-status')).to_contain_text('Demande enregistrée localement')
        self.activate('commercial.v81','COMMERCIAL')
        module('admin','#dashboard')
        lead = self.page.locator('#rows tr').filter(has_text='Client V81 fictif')
        expect(lead.get_by_role('button',name='Créer une opportunité CRM')).to_have_count(0)
        expect(lead.get_by_role('button',name='Qualifier le prospect CRM')).to_have_count(0)
        # The web request already created an automatic CRM prospect with a 48 h follow-up.
        expect(lead.get_by_role('link',name='Prospect CRM automatique : Mission en régie')).to_be_visible()
        lead.get_by_label('Nouveau statut pour Client V81 fictif').select_option('QUALIFIEE')
        lead.get_by_role('button',name='Enregistrer',exact=True).click()
        expect(self.page.locator('#notice')).to_contain_text('Statut enregistré')
        lead.get_by_role('button',name='Qualifier le prospect CRM').click()
        expect(lead.get_by_role('link',name='Opportunité CRM',exact=False)).to_be_visible()
        lead.get_by_role('link',name='Opportunité CRM',exact=False).click()
        expect(self.page.locator('#rows')).to_contain_text('Client V81 fictif')
        self.page.locator('.app-sidebar a[href="quotes.html"]').click()
        expect(self.page.locator('#workspace')).to_be_visible()
        self.page.locator('#lookup').fill('Client V81 fictif')
        self.page.locator('#find').click()
        expect(self.page.locator('#opportunity option')).to_have_count(2)
        self.page.locator('#opportunity').select_option(index=1)
        fill('#editor', {'title':'Audit navigateur V81','scope':'Diagnostic fictif','days':'10','rate':'600','daily_cost':'400','valid_until':'2099-01-01','terms':'Recette fictive'})
        self.page.locator('#editor [name=currency]').select_option('EUR')
        self.page.locator('#editor [name=status]').select_option('PROPOSE')
        self.page.locator('#save').click()
        quote = self.page.locator('#rows tr').filter(has_text='Audit navigateur V81')
        expect(quote).to_contain_text('PROPOSE')
        expect(quote.locator('.row-actions')).not_to_have_attribute('open','')
        quote.locator('.row-actions summary').click()
        expect(quote.get_by_role('button',name='Aperçu PDF')).to_be_visible()
        quote.locator('.row-actions summary').press('Escape')
        expect(quote.locator('.row-actions')).not_to_have_attribute('open','')
        quote.locator('.row-actions summary').click()
        quote.get_by_role('button',name='Aperçu PDF').click()
        expect(self.page.locator('#proposal-document')).to_contain_text('Audit navigateur V81')
        self.page.locator('#close-proposal').click()
        if quote.locator('.row-actions').get_attribute('open') is None:
            quote.locator('.row-actions summary').click()
        with self.page.expect_download() as download:
            quote.get_by_role('button',name='Télécharger le PDF',exact=True).click()
        self.assertRegex(download.value.suggested_filename, r'^DSIG-\d{4}-[0-9A-F]{8}-v1\.pdf$')
        self.assertTrue(Path(download.value.path()).read_bytes().startswith(b'%PDF-1.4'))
        expect(self.page.locator('#notice')).to_contain_text('téléchargé')
        if quote.locator('.row-actions').get_attribute('open') is not None:
            quote.locator('.row-actions summary').click()
        quote.get_by_label('Preuve de transmission ou décision').fill('Transmission fictive V81')
        quote.get_by_role('button',name='Enregistrer le suivi').click()
        expect(self.page.locator('#notice')).to_contain_text('Suivi enregistré')
        expect(quote).to_contain_text('Transmission enregistrée')
        quote.locator('.row-actions summary').click()
        expect(quote.get_by_role('button',name='Modifier')).to_be_disabled()
        quote.locator('form select').select_option('ACCEPTE')
        quote.get_by_label('Preuve de transmission ou décision').fill('Acceptation fictive V81')
        quote.get_by_role('button',name='Enregistrer le suivi').click()
        expect(quote).to_contain_text('Contrat signé non enregistré')
        quote.get_by_label('Référence contrat').fill('V81-CONTRAT')
        quote.get_by_label('Date de signature').fill('2020-01-01')
        quote.get_by_label('Preuve de signature').fill('Signature fictive V81')
        quote.get_by_role('button',name='Enregistrer le contrat signé').click()
        expect(quote).to_contain_text('Contrat signé enregistré : V81-CONTRAT')
        logout()

        self.activate('projet.v81','PROJET')
        module('missions')
        expect(self.page.locator('#quote option')).to_have_count(2)
        self.page.locator('#quote').select_option(index=1)
        expect(self.page.locator('#mission [name=contract_ref]')).to_have_value('V81-CONTRAT')
        self.page.locator('#consultant').select_option(profile['id'])
        fill('#mission', {'start_date':'2020-01-01','end_date':'2020-01-31'})
        self.page.locator('#mission button[type=submit], #mission button:not([type])').click()
        expect(self.page.locator('#rows')).to_contain_text('Audit navigateur V81')
        logout()

        self.activate('consultant.v81','CONSULTANT',profile['id'])
        module('my-activity')
        self.page.locator('#mission').select_option(label='Audit navigateur V81 (REGIE)')
        fill('#cra', {'work_date':'2020-01-08','worked':'1','billable':'1','expenses':'25','description':'CRA fictif V81'})
        self.page.locator('#cra button').click()
        expect(self.page.locator('#rows')).to_contain_text('SOUMIS')
        logout()

        self.login('projet.v81')
        module('missions')
        mission_row=self.page.locator('#rows tr').filter(has_text='Audit navigateur V81')
        mission_row.locator('.row-actions summary').click()
        mission_row.get_by_role('button',name='CRA',exact=True).click()
        activity = self.page.locator('#entries tr').filter(has_text='CRA fictif V81')
        activity.get_by_role('button',name='VALIDE',exact=True).click()
        expect(activity).to_contain_text('VALIDE')
        expect(self.page.locator('#notice')).to_contain_text('CRA traité')
        expect(self.page.locator('#rows')).to_contain_text('425')
        logout()

        # The same mission now flows through finance and management.
        from decimal import Decimal
        def activate_mfa(username, role):
            self.activate(username, role)
            expect(self.page.locator('#modules a')).to_have_count(0)
            self.page.locator('#mfa-setup [name=password]').fill(self.password)
            self.page.locator('#mfa-setup button').click()
            expect(self.page.locator('#mfa-pending')).to_be_visible()
            secret = self.page.locator('#secret').input_value()
            self.page.locator('#mfa-confirm [name=code]').fill(server.authentication.totp(secret, int(time.time())//30))
            self.page.locator('#mfa-confirm button').click()
            expect(self.page.locator('#recovery')).to_be_visible()
            code = self.page.locator('#recovery-codes').inner_text().splitlines()[0]
            self.page.locator('#dismiss-recovery').click()
            self.login(username, code)

        def amounts(row, expected):
            for index, value in expected.items():
                cell = row.locator('td').nth(index)
                expect(cell).to_be_visible()
                self.assertEqual(Decimal(cell.inner_text()), Decimal(value))

        activate_mfa('comptable.v82','COMPTABLE')
        module('billing')
        self.page.locator('#invoice-mission').select_option(label='Client V81 fictif / Audit navigateur V81 (EUR)')
        fill('#invoice', {'reference':'V82-CREANCE','amount':'601','due_date':'2020-02-01'})
        self.page.locator('#invoice button').click()
        expect(self.page.locator('#notice')).to_contain_text('Montant supérieur au disponible facturable validé')
        expect(self.page.locator('#rows tr')).to_have_count(0)
        fill('#invoice', {'amount':'600'})
        self.page.locator('#invoice button').click()
        invoice = self.page.locator('#rows tr').filter(has_text='V82-CREANCE')
        expect(invoice).to_contain_text('600')
        expect(invoice).to_contain_text('En retard')
        totals = self.page.locator('#totals tr').filter(has_text='EUR')
        amounts(totals,{1:'600',2:'0',3:'600'})
        self.page.get_by_role('searchbox',name='Rechercher une créance',exact=True).fill('inexistante')
        self.page.get_by_role('form',name='Filtres des créances').get_by_role('button',name='Rechercher').click()
        expect(self.page.locator('#rows tr')).to_have_count(0)
        amounts(totals,{1:'600',2:'0',3:'600'})
        self.page.get_by_role('searchbox',name='Rechercher une créance',exact=True).fill('v82-creance')
        self.page.get_by_label('Statut des créances').select_option('')
        self.page.get_by_role('form',name='Filtres des créances').get_by_role('button',name='Rechercher').click()
        expect(invoice).to_be_visible()
        payment_choice = self.page.locator('#payment-invoice')
        payment_choice.select_option(index=1)
        selected_invoice = payment_choice.input_value()
        with self.page.expect_response(lambda r: '/api/admin/billing?' in r.url and r.status==200):
            self.page.get_by_role('form',name='Filtres des créances').get_by_role('button',name='Rechercher').click()
        expect(invoice).to_be_visible()
        expect(payment_choice).to_have_value(selected_invoice)

        def payment(reference, amount):
            self.page.locator('#payment-invoice').select_option(index=1)
            fill('#payment', {'reference':reference,'amount':amount,'paid_date':'2020-02-01'})
            self.page.locator('#payment button').click()

        payment('V82-PAY1','200')
        expect(invoice.locator('td').nth(2)).to_contain_text('200')
        amounts(totals,{1:'600',2:'200',3:'400'})
        payment('V82-OVERPAY','401')
        expect(self.page.locator('#notice')).to_contain_text('Paiement supérieur au solde')
        amounts(totals,{2:'200',3:'400'})
        payment('V82-PAY2','400')
        expect(invoice).to_contain_text('Soldée')
        amounts(totals,{1:'600',2:'600',3:'0'})
        expect(self.page.locator('#payment-invoice option')).to_have_count(1)
        self.page.locator('#expense [name=currency]').select_option('EUR')
        self.page.locator('#expense-mission').select_option(label='Client V81 fictif / Audit navigateur V81 (EUR)')
        fill('#expense', {'reference':'V82-DEP','amount':'425','paid_date':'2020-02-01','description':'Décaissement consultant fictif'})
        self.page.locator('#expense button').click()
        expect(self.page.locator('#expense-rows')).to_contain_text('V82-DEP')
        cash = self.page.locator('#cash-rows tr').filter(has_text='EUR')
        amounts(cash,{1:'600',2:'425',3:'175'})
        expense_search=self.page.get_by_role('searchbox',name='Rechercher un décaissement',exact=True)
        expense_search.fill('introuvable-v114')
        expect(self.page.locator('#expense-rows tr')).to_have_count(0)
        amounts(cash,{1:'600',2:'425',3:'175'})
        expense_search.fill('v82-dep')
        expect(self.page.locator('#expense-rows')).to_contain_text('V82-DEP')
        expense_search.fill('')
        logout()

        activate_mfa('direction.v82','DIRECTION')
        module('direction')
        self.page.locator('#control-currency').select_option('EUR')
        self.page.locator('#control-search').fill('Client V81 fictif')
        client = self.page.get_by_role('region',name='Rentabilité par client',exact=True).locator('tbody tr').filter(has_text='Client V81 fictif')
        expect(client).to_have_count(1)
        # Two identifier columns then the published metrics in their documented order.
        amounts(client,{4:'600',5:'425',6:'175',11:'600',12:'0',16:'175'})
        self.page.locator('#control-export-table').select_option('1')
        with self.page.expect_download() as download:
            self.page.locator('#control-export').click()
        self.assertEqual(download.value.suggested_filename,'dsig-pilotage-clients.csv')
        self.assertIn('Client V81 fictif',Path(download.value.path()).read_text(encoding='utf-8-sig'))
        logout()
        self.assertEqual(self.errors, [])

    def test_fixed_price_milestones_and_budget_reconciliation(self):
        from datetime import date, timedelta
        from decimal import Decimal
        profile = self.seed('/api/admin/consultants', {'name':'Consultant V83 fictif','email':'v83@example.invalid','role':'Data Engineer','skills':'Python','location':'Guinée','experience':'5','availability':'Immédiate','notes':'','status':'DISPONIBLE'})
        opportunity = self.seed('/api/admin/crm', {'company':'Client V83 fictif','contact':'Contact fictif','email':'client83@example.invalid','title':'Forfait V83','mode':'FORFAIT','skills':'Python','consultant_id':'','next_action':'','followup':'','notes':'','status':'QUALIFIE'})
        quote = self.seed('/api/admin/quotes', {'opportunity_id':opportunity['id'],'title':'Livraison V83','scope':'Livrable fictif','mode':'FORFAIT','currency':'EUR','days':'5','rate':'0','daily_cost':'100','expenses':'0','fixed_price':'1000','status':'PROPOSE','valid_until':'2099-01-01','terms':'Recette fictive'})
        route = '/api/admin/quotes/'+quote['id']
        for action in ('TRANSMIS','ACCEPTE'):
            response = self.context.request.post(route+'/transmission',data={'version':1,'action':action,'evidence':'Preuve fictive V83'},headers={'Authorization':'Bearer '+server.ADMIN_TOKEN})
            self.assertEqual(response.status,200,response.text())
        self.seed(route+'/contract',{'version':2,'reference':'V83-CONTRAT','signed_date':'2020-01-01','evidence':'Signature fictive'})
        mission = self.seed('/api/admin/missions',{'quote_id':quote['id'],'consultant_id':profile['id'],'contract_ref':'V83-CONTRAT','start_date':'2020-01-01','end_date':'2020-01-31'})
        self.activate('comptable.v83','COMPTABLE')
        expect(self.page.locator('#modules a')).to_have_count(0)
        self.page.locator('#mfa-setup [name=password]').fill(self.password)
        self.page.locator('#mfa-setup button').click()
        expect(self.page.locator('#mfa-pending')).to_be_visible()
        secret = self.page.locator('#secret').input_value()
        self.page.locator('#mfa-confirm [name=code]').fill(server.authentication.totp(secret, int(time.time())//30))
        self.page.locator('#mfa-confirm button').click()
        expect(self.page.locator('#recovery')).to_be_visible()
        code = self.page.locator('#recovery-codes').inner_text().splitlines()[0]
        self.page.locator('#dismiss-recovery').click()
        self.login('comptable.v83',code)
        self.page.locator('#modules a[href="billing.html"]').click()
        expect(self.page.locator('#workspace')).to_be_visible()

        def fill(form, values):
            for name, value in values.items():
                self.page.locator(f'{form} [name={name}]').fill(value)
        def select_mission(selector):
            self.page.locator(selector).select_option(mission['id'])
        def amount_at(row,index,value):
            cell=row.locator('td').nth(index)
            expect(cell).to_be_visible()
            self.assertEqual(Decimal(cell.inner_text()),Decimal(value))
        due=(date.today()+timedelta(days=10)).isoformat()
        select_mission('#milestone-mission')
        fill('#milestone',{'title':'Livrable initial V83','amount':'1001'})
        self.page.locator('#milestone button').click()
        expect(self.page.locator('#notice')).to_contain_text('Montant supérieur au forfait')
        fill('#milestone',{'amount':'600'})
        self.page.locator('#milestone button').click()
        milestone=self.page.locator('#milestone-rows tr').filter(has_text='Livrable initial V83')
        expect(milestone).to_contain_text('PREVU')
        # The success notice is written after the list reload: wait for it so it cannot overwrite the next refusal.
        expect(self.page.locator('#notice')).to_contain_text('Enregistrement effectué')

        select_mission('#invoice-mission')
        fill('#invoice',{'reference':'V83-CREANCE','amount':'600','due_date':due})
        self.page.locator('#invoice button').click()
        expect(self.page.locator('#notice')).to_contain_text('Montant supérieur au disponible facturable validé')
        expect(self.page.locator('#rows tr')).to_have_count(0)
        self.page.once('dialog',lambda dialog: dialog.accept())
        milestone.get_by_role('button',name='Valider',exact=True).click()
        expect(milestone).to_contain_text('VALIDE')
        expect(milestone.get_by_role('button',name='Valider',exact=True)).to_have_count(0)
        self.page.locator('#invoice button').click()
        expect(self.page.locator('#rows')).to_contain_text('V83-CREANCE')

        select_mission('#schedule-mission')
        fill('#schedule',{'label':'Échéance V83','amount':'600','due_date':due})
        self.page.locator('#schedule button').click()
        schedule=self.page.locator('#schedule-rows tr').filter(has_text='Échéance V83')
        expect(schedule).to_contain_text('PREVU')
        schedule.get_by_label('Référence créance').fill('INCONNUE')
        schedule.get_by_role('button',name='Rapprocher').click()
        expect(self.page.locator('#notice')).to_contain_text('Créance absente ou montant différent')
        schedule.get_by_label('Référence créance').fill('V83-CREANCE')
        schedule.get_by_role('button',name='Rapprocher').click()
        expect(schedule).to_contain_text('RAPPROCHE / V83-CREANCE')

        self.page.locator('#planned-expense [name=currency]').select_option('EUR')
        fill('#planned-expense',{'reference':'V83-BUDGET','amount':'250','due_date':due,'description':'Budget consultant fictif'})
        self.page.locator('#planned-expense button').click()
        budget=self.page.locator('#budget-rows tr').filter(has_text='V83-BUDGET')
        expect(budget).to_contain_text('PREVU')
        expect(self.page.locator('#notice')).to_contain_text('Dépense planifiée')
        forecast=self.page.locator('#forecast-rows tr').filter(has_text='EUR')
        amount_at(forecast,9,'250')
        self.page.locator('#expense [name=currency]').select_option('EUR')
        select_mission('#expense-mission')
        fill('#expense',{'reference':'V83-DEP','amount':'250','paid_date':date.today().isoformat(),'description':'Décaissement fictif'})
        self.page.locator('#expense button').click()
        expect(self.page.locator('#notice')).to_contain_text('Décaissement enregistré')
        budget.get_by_label('Référence décaissement').fill('V83-DEP')
        budget.get_by_role('button',name='Rapprocher').click()
        expect(budget).to_contain_text('RAPPROCHE / V83-DEP')
        # Refresh explicitly so asynchronous forecast updates cannot race the assertions.
        self.page.reload()
        expect(self.page.locator('#workspace')).to_be_visible()
        amount_at(forecast,8,'250')
        amount_at(forecast,9,'0')
        amount_at(forecast,5,'0')
        self.page.goto('/connexion.html')
        expect(self.page.locator('#workspace')).to_be_visible()
        self.page.locator('#logout').click()
        expect(self.page.locator('#login')).to_be_visible()
        self.assertEqual(self.errors, [])

    def test_recruitment_consultant_and_private_document_lifecycle(self):
        import antivirus
        from datetime import date
        self.page.goto('/')
        for name,value in {'nom':'Candidat V85 fictif','org':'Indépendant','email':'candidat85@example.invalid','message':'Candidature fictive Data Engineer'}.items():
            self.page.locator(f'#request [name={name}]').fill(value)
        self.page.locator('#need').select_option(label='Candidature spontanée')
        self.page.locator('#request [name=consent]').check()
        self.page.locator('#request [type=submit]').click()
        expect(self.page.locator('#request-status')).to_contain_text('Demande enregistrée localement')
        self.activate('rh.v85','RH')
        self.page.locator('#modules a[href="recruitment.html"]').click()
        expect(self.page.locator('#workspace')).to_be_visible()
        candidate=self.page.locator('#rows section').filter(has_text='Candidat V85 fictif')
        candidate.locator('[name=role]').fill('Data Engineer')
        candidate.locator('[name=skills]').fill('Python, Snowflake')
        candidate.get_by_role('button',name='Qualifier dans le vivier').click()
        expect(candidate).to_contain_text('Profil qualifié')
        expect(candidate.get_by_role('button',name='Qualifier dans le vivier')).to_have_count(0)
        self.page.locator('#filter [name=state]').select_option('PENDING')
        self.page.locator('#filter button').click()
        expect(self.page.locator('#rows')).to_contain_text('Aucune candidature')
        self.page.locator('#filter [name=state]').select_option('QUALIFIED')
        self.page.locator('#filter [name=q]').fill('Candidat V85')
        self.page.locator('#filter button').click()
        expect(candidate).to_contain_text('Profil qualifié')
        response=self.context.request.get('/api/admin/recruitment',headers={'Authorization':'Bearer session'})
        self.assertEqual(response.status,200)
        cid=response.json()['items'][0]['consultant_id']
        candidate.get_by_role('link',name='Profil qualifié — ouvrir le vivier').click()
        expect(self.page.locator('#workspace')).to_be_visible()
        profile=self.page.locator('#rows tr').filter(has_text='Candidat V85 fictif')
        expect(profile).to_contain_text('À qualifier')
        profile.get_by_role('button',name='Modifier').click()
        expect(self.page.locator('#editor [name=email]')).to_have_value('candidat85@example.invalid')
        self.page.locator('#editor [name=location]').fill('Guinée')
        self.page.locator('#editor [name=experience]').fill('5')
        self.page.locator('#editor [name=availability]').fill('Immédiate')
        self.page.locator('#editor [name=status]').select_option('DISPONIBLE')
        self.page.locator('#save').click()
        expect(profile).to_contain_text('Disponible')
        expect(profile).to_contain_text('Snowflake')
        expect(self.page.locator('#rows tr')).to_have_count(1)
        self.page.goto('/documents.html')
        expect(self.page.locator('#notice')).to_contain_text('Permission insuffisante')
        expect(self.page.locator('#workspace')).to_be_hidden()
        self.page.goto('/connexion.html')
        expect(self.page.locator('#workspace')).to_be_visible()
        self.page.locator('#logout').click()
        expect(self.page.locator('#login')).to_be_visible()

        self.activate('admin.v85','ADMIN')
        expect(self.page.locator('#modules a')).to_have_count(0)
        self.page.locator('#mfa-setup [name=password]').fill(self.password)
        self.page.locator('#mfa-setup button').click()
        expect(self.page.locator('#mfa-pending')).to_be_visible()
        secret=self.page.locator('#secret').input_value()
        self.page.locator('#mfa-confirm [name=code]').fill(server.authentication.totp(secret,int(time.time())//30))
        self.page.locator('#mfa-confirm button').click()
        expect(self.page.locator('#recovery')).to_be_visible()
        code=self.page.locator('#recovery-codes').inner_text().splitlines()[0]
        self.page.locator('#dismiss-recovery').click()
        self.login('admin.v85',code)
        self.page.locator('#modules a[href="accounts.html"]').click()
        expect(self.page.locator('#workspace')).to_be_visible()
        self.page.locator('#create [name=username]').fill('consultant.v85')
        self.page.locator('#create [name=role]').select_option('CONSULTANT')
        expect(self.page.locator('#consultant-id option')).to_have_count(2)
        self.page.locator('#consultant-id').select_option(cid)
        self.page.locator('#create button[type=submit]').click()
        expect(self.page.locator('#notice')).to_have_text('Compte créé.')
        consultant_key=self.page.locator('#key').input_value()
        self.page.locator('#clear-key').click()
        self.page.goto('/connexion.html')
        expect(self.page.locator('#workspace')).to_be_visible()
        self.page.locator('#modules a[href="documents.html"]').click()
        expect(self.page.locator('#workspace')).to_be_visible()
        raw1=b'%PDF-1.4\nSynthetic CV V85 version 1\n%%EOF'
        raw2=b'%PDF-1.4\nSynthetic CV V85 version 2\n%%EOF'
        editor=self.page.locator('#editor')
        def attach(raw):
            editor.locator('[name=pdf]').set_input_files({'name':'cv-fictif.pdf','mimeType':'application/pdf','buffer':raw})
        editor.locator('[name=category]').select_option('CV')
        editor.locator('[name=entity_id]').fill(cid)
        editor.locator('[name=title]').fill('CV V85 fictif')
        editor.locator('[name=review_date]').fill(date.today().isoformat())
        attach(raw1)
        with patch.dict(os.environ,{'DSIG_DOCUMENT_KEY':Fernet.generate_key().decode(),'DSIG_DOCUMENT_PREVIOUS_KEY':'','DSIG_CLAMD_SOCKET':''}):
            # Real fail-closed unavailable path; no ClamAV daemon required by browser CI.
            self.page.locator('#save').click()
            expect(self.page.locator('#notice')).to_contain_text('Contrôle antivirus indisponible')
            expect(self.page.locator('#rows tr')).to_have_count(0)
            with patch('antivirus.scan',side_effect=antivirus.Infected):
                self.page.locator('#save').click()
                expect(self.page.locator('#notice')).to_contain_text('Document refusé par le contrôle antivirus')
                expect(self.page.locator('#rows tr')).to_have_count(0)
            # Simulate a clean scan only at the scanner boundary in this test fixture.
            with patch('antivirus.scan') as scan:
                self.page.locator('#save').click()
                first=self.page.locator('#rows tr').filter(has_text='v1 (actuelle)')
                expect(first).to_contain_text('CV V85 fictif')
                expect(first).to_contain_text('à revoir')
                first.locator('.row-actions summary').click()
                first.get_by_role('button',name='Nouvelle version').click()
                expect(editor.locator('[name=entity_id]')).to_have_value(cid)
                attach(raw2)
                self.page.locator('#save').click()
                current=self.page.locator('#rows tr').filter(has_text='v2 (actuelle)')
                expect(current).to_contain_text('CV V85 fictif')
                expect(self.page.locator('#rows tr').filter(has_text='v1 (historique)')).to_have_count(1)
                expect(self.page.locator('#rows tr')).to_have_count(2)
                with self.page.expect_download() as download:
                    current.locator('.row-actions summary').click()
                    current.get_by_role('button',name='Télécharger').click()
                self.assertEqual(Path(download.value.path()).read_bytes(),raw2)
                self.assertEqual(scan.call_count,3)
            response=self.context.request.get('/api/admin/documents',headers={'Authorization':'Bearer session'})
            self.assertEqual(response.status,200)
            items=response.json()['items']
            self.assertEqual(len(items),2)
            self.assertNotIn('ciphertext',response.text())
            with server.connect() as db:
                encrypted=[row[0] for row in db.execute('SELECT ciphertext FROM documents')]
                self.assertEqual(len(encrypted),2)
                self.assertTrue(all(raw1 not in item and raw2 not in item for item in encrypted))
            current_id=next(item['id'] for item in items if item['current'])
            self.page.goto('/connexion.html')
            expect(self.page.locator('#workspace')).to_be_visible()
            self.page.locator('#logout').click()
            expect(self.page.locator('#login')).to_be_visible()
            self.assertEqual(self.context.request.get('/api/admin/documents/'+current_id).status,401)
        opportunity=self.seed('/api/admin/crm',{'company':'Client V93 fictif','contact':'Contact fictif','email':'client93@example.invalid','title':'Mission RH V93','mode':'REGIE','skills':'Python','consultant_id':'','next_action':'','followup':'','notes':'','status':'QUALIFIE'})
        quote=self.seed('/api/admin/quotes',{'opportunity_id':opportunity['id'],'title':'Mission RH V93','scope':'Prestation fictive','mode':'REGIE','currency':'EUR','days':'5','rate':'600','daily_cost':'400','expenses':'0','fixed_price':'0','status':'PROPOSE','valid_until':'2099-01-01','terms':'Recette fictive'})
        route='/api/admin/quotes/'+quote['id']
        for action in ('TRANSMIS','ACCEPTE'):
            response=self.context.request.post(route+'/transmission',data={'version':1,'action':action,'evidence':'Preuve fictive V93'},headers={'Authorization':'Bearer '+server.ADMIN_TOKEN})
            self.assertEqual(response.status,200,response.text())
        self.seed(route+'/contract',{'version':2,'reference':'V93-CONTRAT','signed_date':'2020-01-01','evidence':'Signature fictive'})
        # Independent fictitious actors share the isolated loopback IP; keep the
        # production rate limiter intact and reset only the test fixture.
        server.authentication.ATTEMPTS.clear()
        self.activate('projet.v93','PROJET')
        self.page.locator('#modules a[href="missions.html"]').click()
        expect(self.page.locator('#workspace')).to_be_visible()
        self.page.locator('#quote').select_option(quote['id'])
        self.page.locator('#consultant').select_option(cid)
        self.page.locator('#mission [name=start_date]').fill('2020-01-01')
        self.page.locator('#mission [name=end_date]').fill('2020-01-31')
        self.page.locator('#mission button:not([type])').click()
        expect(self.page.locator('#rows')).to_contain_text('Mission RH V93')
        self.page.goto('/connexion.html')
        expect(self.page.locator('#workspace')).to_be_visible()
        self.page.locator('#logout').click()
        expect(self.page.locator('#login')).to_be_visible()
        server.authentication.ATTEMPTS.clear()
        for name,value in {'username':'consultant.v85','key':consultant_key,'password':self.password}.items():
            self.page.locator(f'#activate [name={name}]').fill(value)
        self.page.locator('#activate button').click()
        expect(self.page.locator('#notice')).to_contain_text('Activation effectuée')
        self.login('consultant.v85')
        self.page.locator('#modules a[href="my-activity.html"]').click()
        expect(self.page.locator('#workspace')).to_be_visible()
        expect(self.page.locator('#mission option')).to_have_count(2)
        self.page.locator('#mission').select_option(label='Mission RH V93 (REGIE)')
        for name,value in {'work_date':'2020-01-08','worked':'1','billable':'1','expenses':'0','description':'CRA recrutement V93'}.items():
            self.page.locator(f'#cra [name={name}]').fill(value)
        self.page.locator('#cra button').click()
        expect(self.page.locator('#rows')).to_contain_text('SOUMIS')
        self.assertEqual(self.errors, [])

    def test_tender_pipeline_and_appointment_conflicts(self):
        opportunity = self.seed('/api/admin/crm', {'company':'Client V86 fictif','contact':'Contact fictif','email':'v86@example.invalid','title':'Mission V86','mode':'CONSEIL','skills':'Data','consultant_id':'','next_action':'','followup':'','notes':'','status':'QUALIFIE'})
        self.activate('commercial.v86', 'COMMERCIAL')
        self.page.locator('#modules a[href="tenders.html"]').click()
        expect(self.page.locator('#workspace')).to_be_visible()
        values = {'title':'Appel V86 fictif','client':'Client V86 fictif','reference':'AO-V86','deadline':'2020-01-01','owner':'Commercial fictif','notes':'Qualification fictive','budget':'1250.50'}
        for name, value in values.items():
            self.page.locator(f'#editor [name={name}]').fill(value)
        self.page.locator('#editor [name=currency]').select_option('EUR')
        self.page.locator('#editor-stage').select_option('QUALIFICATION')
        self.page.locator('#save').click()
        expect(self.page.locator('#notice')).to_have_text('Dossier enregistré.')
        row = self.page.locator('#rows tr').filter(has_text='AO-V86')
        expect(row).to_contain_text('échue')
        expect(row).to_contain_text('1250.50 EUR')
        headers = {'Authorization':'Bearer session', 'Origin':self.url}
        endpoint = '/api/admin/tenders'
        saved = self.context.request.get(endpoint, headers=headers).json()['items'][0]
        row.get_by_role('button', name='Modifier').click()
        self.page.locator('#editor-stage').select_option('GO')
        self.page.locator('#save').click()
        expect(row).to_contain_text('Go')
        stale = dict(values, currency='EUR', stage='PERDU', version=saved['version'])
        response = self.context.request.patch(endpoint+'/'+saved['id'], headers=headers, data=stale)
        self.assertEqual(response.status, 409, response.text())
        self.page.locator('#stage').select_option('PERDU')
        self.page.locator('#filter button').click()
        expect(self.page.locator('#rows')).to_contain_text('Aucun dossier.')
        self.page.locator('#stage').select_option('GO')
        self.page.locator('#search').fill('AO-V86')
        self.page.locator('#filter button').click()
        expect(row).to_contain_text('Go')
        self.page.goto('/appointments.html')
        expect(self.page.locator('#workspace')).to_be_visible()
        expect(self.page.locator('#editor')).to_be_visible()

        def schedule(title, starts, ends):
            self.page.locator('#editor [name=opportunity_id]').select_option(opportunity['id'])
            for name, value in {'title':title,'starts':starts,'ends':ends}.items():
                self.page.locator(f'#editor [name={name}]').fill(value)
            self.page.locator('#editor button').click()

        schedule('Réunion V86', '2099-05-01T09:00', '2099-05-01T10:00')
        expect(self.page.locator('#notice')).to_have_text('Rendez-vous planifié.')
        meeting = self.page.locator('#rows section').filter(has_text='Réunion V86')
        expect(meeting).to_contain_text('PLANIFIE')
        schedule('Conflit V86', '2099-05-01T09:30', '2099-05-01T10:30')
        expect(self.page.locator('#notice')).to_contain_text('Créneau occupé')
        expect(self.page.locator('#rows')).not_to_contain_text('Conflit V86')
        schedule('Adjacent V86', '2099-05-01T10:00', '2099-05-01T11:00')
        adjacent = self.page.locator('#rows section').filter(has_text='Adjacent V86')
        expect(adjacent).to_contain_text('PLANIFIE')
        adjacent.get_by_role('button',name='Annuler').click()
        expect(adjacent).to_contain_text('ANNULE')
        expect(adjacent.get_by_role('button')).to_have_count(0)
        schedule('Créneau libéré V86', '2099-05-01T10:00', '2099-05-01T11:00')
        expect(self.page.locator('#rows')).to_contain_text('Créneau libéré V86')
        meeting.get_by_role('button',name='Terminer').click()
        expect(meeting).to_contain_text('TERMINE')
        expect(meeting.get_by_role('button')).to_have_count(0)
        appointments = self.context.request.get('/api/admin/crm/appointments', headers=headers).json()['items']
        finished = next(a for a in appointments if a['title']=='Réunion V86')
        self.assertEqual([event['status'] for event in finished['history']], ['PLANIFIE','TERMINE'])
        self.assertEqual(finished['opportunity_id'], opportunity['id'])
        self.assertEqual(finished['starts'], '2099-05-01T09:00:00+00:00')
        response = self.context.request.patch('/api/admin/crm/appointments/'+finished['id'], headers=headers, data={'status':'ANNULE','version':1})
        self.assertEqual(response.status, 409, response.text())
        with server.connect() as db:
            events = db.execute('SELECT stage,version FROM tender_events WHERE tender_id=? ORDER BY id',(saved['id'],)).fetchall()
            self.assertEqual([tuple(event) for event in events], [('QUALIFICATION',1),('GO',2)])
        self.assertEqual(self.errors, [])

    def test_english_parity_and_intake(self):
        self.page.goto('/')
        styles = self.page.locator('link[rel=stylesheet]').evaluate_all('(links) => links.map(x => x.getAttribute("href"))')
        sections = self.page.locator('main section[id]').evaluate_all('(nodes) => nodes.map(x => x.id)')
        for width in (390, 1440):
            self.page.set_viewport_size({'width': width, 'height': 900})
            self.page.goto('/en.html')
            self.assertEqual(self.page.locator('link[rel=stylesheet]').evaluate_all('(links) => links.map(x => x.getAttribute("href"))'), styles)
            self.assertEqual(self.page.locator('main section[id]').evaluate_all('(nodes) => nodes.map(x => x.id)'), sections)
            expect(self.page.locator('#expertise-groups article')).to_have_count(29)
            self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'))
        self.page.get_by_role('heading', name='Cybersecurity audit & GRC', exact=True).locator('..').get_by_role('link').click()
        expect(self.page.locator('#deliverables')).to_contain_text('Risk register')
        self.page.locator('#expertise-contact').click()
        expect(self.page.locator('#need')).to_have_value('Cybersécurité & résilience')
        expect(self.page.locator('#request [name=message]')).to_have_value('Expertise: Cybersecurity audit & GRC — ')
        for name, value in {'nom':'Fictitious English client','org':'Fictitious organisation','email':'en-qa@example.invalid','message':'English browser test request'}.items():
            self.page.locator(f'#request [name={name}]').fill(value)
        self.page.locator('#request [name=consent]').check()
        self.page.locator('#request [type=submit]').click()
        expect(self.page.locator('#request-status')).to_contain_text('Request recorded locally. Reference:')
        response = self.context.request.get('/api/admin/requests', headers={'Authorization': 'Bearer '+server.ADMIN_TOKEN})
        self.assertEqual(response.status, 200)
        self.assertIn('English browser test request', response.text())
        self.page.locator('#contact a[href="privacy-en.html"]').click()
        expect(self.page.locator('h1')).to_have_text('Privacy and personal data')
        self.assertEqual(self.errors, [])

    def test_mobile_navigation_and_accessibility(self):
        self.page.set_viewport_size({'width':390,'height':844})
        external=[]
        self.page.on('request',lambda request: external.append(request.url) if request.url.startswith(('http://','https://')) and not request.url.startswith(self.url+'/') else None)
        self.page.goto('/')
        self.page.keyboard.press('Tab')
        expect(self.page.locator('.skip-link')).to_be_focused()
        self.page.keyboard.press('Enter')
        expect(self.page.locator('#main')).to_be_focused()
        self.page.locator('#menu').click()
        expect(self.page.locator('#menu')).to_have_attribute('aria-expanded','true')
        self.page.keyboard.press('Escape')
        expect(self.page.locator('#menu')).to_have_attribute('aria-expanded','false')
        expect(self.page.locator('#menu')).to_be_focused()
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),392)
        self.page.goto('/connexion.html')
        expect(self.page.locator('#signin')).to_be_visible()
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),392)
        self.assertEqual(external,[])
        self.assertEqual(self.errors,[])

    def test_self_hosted_typography(self):
        for path in ('/', '/en.html', '/expertise.html', '/connexion.html'):
            for width in (390, 1440):
                self.page.set_viewport_size({'width': width, 'height': 900})
                self.page.goto(path)
                loaded = self.page.evaluate("""async () => {
                    await document.fonts.ready;
                    const faces = await document.fonts.load('400 16px "DSIG Open Sans"', 'École Guinée');
                    return faces.length > 0 && faces.every(face => face.status === 'loaded') &&
                        getComputedStyle(document.body).fontFamily.includes('DSIG Open Sans');
                }""")
                self.assertTrue(loaded, f'Font not loaded: {path} ({width}px)')
                self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), path)

    def test_cybersecurity_expertise_and_prefill(self):
        self.page.goto('/')
        expect(self.page.locator('#expertise-groups article')).to_have_count(29)
        expect(self.page.locator('#expertise-groups h3')).to_have_count(6)
        self.page.locator('article').filter(has=self.page.get_by_role('heading',name='Audit de cybersécurité & GRC',exact=True)).get_by_role('link').click()
        expect(self.page.locator('#deliverables')).to_contain_text('Registre des risques')
        self.page.locator('#expertise-contact').click()
        expect(self.page.locator('#need')).to_have_value('Cybersécurité & résilience')
        expect(self.page.locator('#request [name=message]')).to_have_value('Domaine : Audit de cybersécurité & GRC — ')
        self.assertEqual(self.errors, [])

    def test_logistics_expertise_bilingual(self):
        for path, label, detail in (('/', 'Logistique & transport', 'Cartographie des flux'),('/en.html', 'Logistics & transportation', 'Flow maps')):
            self.page.goto(path)
            expect(self.page.get_by_role('heading',name='Supply Chain Management',exact=True)).to_be_visible()
            self.page.locator('article').filter(has=self.page.get_by_role('heading',name=label,exact=True)).get_by_role('link').click()
            expect(self.page.locator('#deliverables')).to_contain_text(detail)
            self.page.locator('#expertise-contact').click()
            expect(self.page.locator('#need')).to_have_value('Conseil & expertise')
            expect(self.page.locator('#request [name=message]')).to_have_value(('Domaine : ' if path=='/' else 'Expertise: ')+label+' — ')
        self.assertEqual(self.errors, [])

    def test_saas_offer_draft(self):
        self.seed('/api/admin/crm',{'company':'Prospect SaaS V129','contact':'','email':'','title':'Cadrage','mode':'CONSEIL','skills':'','consultant_id':'','next_action':'','followup':'','notes':'','status':'PROSPECT'})
        self.page.goto('/crm.html')
        self.page.locator('#token').fill(server.ADMIN_TOKEN)
        self.page.locator('#login-form button').click()
        expect(self.page.locator('#workspace')).to_be_visible()
        form=self.page.locator('#saas-form')
        form.locator('[name=product_id]').select_option('minefleet360')
        form.locator('[name=currency]').select_option('EUR')
        form.locator('[name=quantity]').fill('10')
        form.locator('[name=unit_price]').fill('25')
        draft=self.page.locator('#saas-offer-form')
        draft.locator('[name=search]').fill('Prospect SaaS V129')
        draft.get_by_role('button',name='Rechercher les opportunités').click()
        expect(draft.locator('[name=opportunity_id] option')).to_have_count(2)
        draft.locator('[name=opportunity_id]').select_option(index=1)
        draft.locator('[name=title]').fill('Brouillon V129')
        draft.locator('[name=valid_until]').fill('2099-01-01')
        draft.get_by_role('button',name='Enregistrer le brouillon SaaS').click()
        expect(self.page.locator('#saas-offer-notice')).to_contain_text('Brouillon SaaS enregistré')
        row=self.page.locator('#saas-offer-rows details').filter(has_text='Brouillon V129')
        row.locator('summary').click()
        expect(row).to_contain_text('3000.00 EUR')
        row.get_by_label('Décision commerciale').select_option('VALIDEE')
        row.get_by_label('Preuve de décision SaaS').fill('Validation fictive V130')
        self.page.once('dialog',lambda dialog:dialog.accept())
        row.get_by_role('button',name='Enregistrer la décision').click()
        expect(row.locator('summary')).to_contain_text('VALIDEE')
        row.locator('summary').click()
        expect(row).to_contain_text('Validation fictive V130')
        for decision in ('TRANSMISE','ACCEPTEE'):
            row.get_by_label('Décision commerciale').select_option(decision)
            row.get_by_label('Preuve de décision SaaS').fill('Preuve fictive '+decision)
            self.page.once('dialog',lambda dialog:dialog.accept())
            row.get_by_role('button',name='Enregistrer la décision').click()
            expect(row.locator('summary')).to_contain_text(decision)
            row.locator('summary').click()
        row.locator('[name=starts_on]').fill('2099-01-01')
        row.locator('[name=ends_on]').fill('2099-02-01')
        row.locator('[name=reference]').fill('Contrat fictif V131')
        self.page.once('dialog',lambda dialog:dialog.accept())
        row.get_by_role('button',name='Enregistrer l’abonnement').click()
        records=self.page.locator('#saas-subscription-rows')
        expect(records).to_contain_text('PLANIFIE')
        expect(self.page.locator('#saas-subscription-metrics')).to_contain_text('1 planifiés')
        self.page.get_by_label('État des abonnements SaaS').select_option('ACTIF')
        expect(records).to_contain_text('Aucun abonnement')
        self.page.get_by_label('État des abonnements SaaS').select_option('PLANIFIE')
        expect(records).to_contain_text('PLANIFIE')
        self.page.get_by_label('Rechercher un abonnement SaaS').fill('absent')
        expect(records).to_contain_text('Aucun abonnement')
        self.page.get_by_label('Rechercher un abonnement SaaS').fill('V131')
        expect(records).to_contain_text('PLANIFIE')
        records.locator(':scope > details > summary').click()
        expect(records.get_by_text('Historique des décisions (0)',exact=True)).to_be_visible()
        expect(self.page.locator('#saas-renewals')).to_contain_text('0 contrat(s)')
        records.get_by_role('button',name='Voir l’échéancier de facturation').click()
        expect(records).to_contain_text('0/1 échéances préparées')
        self.page.once('dialog',lambda dialog:dialog.accept())
        records.get_by_role('button',name='Préparer cette échéance').click()
        expect(records).to_contain_text('1/1 échéances préparées')
        from datetime import date
        day=date.today().isoformat()
        records.get_by_label('Référence de la facture émise').fill('FAC-REC-134')
        records.get_by_label('Date d’émission réelle').fill(day)
        records.get_by_label('Date limite de règlement').fill(day)
        records.get_by_label('Montant de taxe figurant sur la facture (0 si aucune)').fill('0')
        self.page.once('dialog',lambda dialog:dialog.accept())
        records.get_by_role('button',name='Rapprocher la facture').click()
        expect(records).to_contain_text('FAC-REC-134')
        records.get_by_label('Référence du règlement réel').fill('VIR-REC-134')
        records.get_by_label('Date réelle du règlement').fill(day)
        records.get_by_label('Montant reçu').fill('100')
        self.page.once('dialog',lambda dialog:dialog.accept())
        records.get_by_role('button',name='Enregistrer le règlement').click()
        expect(records).to_contain_text('PARTIELLE')
        self.page.goto('/billing.html')
        self.page.locator('#token').fill(server.ADMIN_TOKEN)
        self.page.locator('#login-form button').click()
        expect(self.page.locator('#creances-saas')).to_contain_text('FAC-REC-134')
        self.page.get_by_label('Rechercher une créance SaaS').fill('absent')
        expect(self.page.locator('#creances-saas')).to_contain_text('0 facture(s)')
        self.page.get_by_label('Rechercher une créance SaaS').fill('FAC-REC-134')
        section=self.page.locator('#creances-saas')
        expect(section).to_contain_text('PARTIELLE')
        section.get_by_text('Historique et actions').click()
        section.get_by_label('Note de relance SaaS').fill('Relance fictive V136')
        self.page.once('dialog',lambda dialog:dialog.accept())
        section.get_by_role('button',name='Consigner une relance SaaS').click()
        expect(section).to_contain_text('Relance fictive V136')
        section.get_by_text('Historique et actions').click()
        section.get_by_label('Référence règlement SaaS').fill('VIR-REC-136')
        section.get_by_label('Date règlement SaaS').fill(day)
        section.get_by_label('Montant règlement SaaS').fill('150')
        self.page.once('dialog',lambda dialog:dialog.accept())
        section.get_by_role('button',name='Enregistrer règlement SaaS').click()
        expect(self.page.locator('#creances-saas')).to_contain_text('REGLEE')
        costs=self.page.locator('#rentabilite-saas')
        expect(costs).to_contain_text('MineFleet360')
        expect(costs).to_contain_text('250')
        expect(costs.get_by_role('button',name='Affecter le coût SaaS')).to_be_visible()
        expense=self.page.locator('#expense')
        for name,value in [('reference','DEP-REC-137'),('amount','100'),('paid_date',day),('description','Hébergement fictif')]:
            expense.locator('[name='+name+']').fill(value)
        expense.locator('[name=currency]').select_option('EUR')
        expense.locator('[name=category]').select_option('FONCTIONNEMENT')
        expense.get_by_role('button',name='Enregistrer le décaissement').click()
        expect(self.page.locator('#expense-rows')).to_contain_text('DEP-REC-137')
        costs.get_by_label('Référence du décaissement enregistré').fill('DEP-REC-137')
        costs.get_by_label('Produit SaaS').select_option('minefleet360')
        costs.get_by_label('Nature du coût').select_option('INFRASTRUCTURE')
        costs.get_by_label('Montant à affecter').fill('60')
        self.page.once('dialog',lambda dialog:dialog.accept())
        costs.get_by_role('button',name='Affecter le coût SaaS').click()
        expect(costs).to_contain_text('DEP-REC-137')
        expect(costs).to_contain_text('190.00')
        monthly=self.page.locator('#saas-monthly')
        monthly.get_by_label('Mois de début').fill(day[:7])
        monthly.get_by_label('Mois de fin').fill(day[:7])
        monthly.get_by_label('Produit SaaS mensuel').select_option('minefleet360')
        monthly.get_by_label('Devise mensuelle').select_option('EUR')
        monthly.get_by_role('button',name='Afficher la période').click()
        expect(monthly).to_contain_text('190.00')
        expect(monthly).to_contain_text('1 ligne(s)')
        expect(monthly.get_by_role('button',name='Exporter la période (CSV)')).to_be_enabled()
        monthly.get_by_label('Mois du budget').fill(day[:7])
        monthly.get_by_label('Produit du budget').select_option('minefleet360')
        monthly.get_by_label('Devise du budget').select_option('EUR')
        monthly.get_by_label('Objectif de facturation HT').fill('250')
        monthly.get_by_label('Budget de coûts').fill('50')
        self.page.once('dialog',lambda dialog:dialog.accept())
        monthly.get_by_role('button',name='Enregistrer le budget SaaS').click()
        expect(monthly.get_by_role('region',name='Performance mensuelle SaaS')).to_contain_text('Dépassement')
        costs.get_by_label('Rechercher une affectation SaaS').fill('absent')
        expect(costs).to_contain_text('0 affectation(s)')
        self.page.set_viewport_size({'width':390,'height':844})
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'))
        self.assertEqual(self.errors,[])

    def test_saas_simulator(self):
        self.page.goto('/crm.html')
        self.page.locator('#token').fill(server.ADMIN_TOKEN)
        self.page.locator('#login-form button').click()
        expect(self.page.locator('#workspace')).to_be_visible()
        form=self.page.locator('#saas-form')
        form.locator('[name=product_id]').select_option('minefleet360')
        form.locator('[name=currency]').select_option('EUR')
        for name,value in {'quantity':'10','unit_price':'25.50','options':'10','setup':'200','training':'100'}.items():
            form.locator('[name='+name+']').fill(value)
        form.get_by_role('button',name='Simuler les revenus').click()
        expect(self.page.locator('#saas-results')).to_contain_text('3480.00 EUR')
        form.locator('[name=cycle]').select_option('ANNUAL')
        expect(self.page.locator('#saas-results .count')).to_have_count(0)
        form.get_by_role('button',name='Simuler les revenus').click()
        expect(self.page.locator('#saas-results')).to_contain_text('22.08 EUR')
        form.get_by_role('button',name='Effacer la simulation').click()
        expect(self.page.locator('#saas-results .count')).to_have_count(0)
        self.page.set_viewport_size({'width':390,'height':844})
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'))
        self.assertEqual(self.errors,[])

    def test_quote_templates(self):
        self.page.goto('/quotes.html')
        self.page.locator('#token').fill(server.ADMIN_TOKEN)
        self.page.locator('#login-form button').click()
        expect(self.page.locator('#workspace')).to_be_visible()
        editor=self.page.locator('#editor')
        editor.locator('[name=rate]').fill('650')
        editor.locator('[name=currency]').select_option('EUR')
        self.page.locator('#proposal-template').select_option('SAAS')
        self.page.locator('#apply-template').click()
        expect(editor.locator('[name=scope]')).to_have_value(re.compile('.*Démonstration.*',re.DOTALL))
        expect(editor.locator('[name=rate]')).to_have_value('650')
        expect(editor.locator('[name=currency]')).to_have_value('EUR')
        self.page.locator('#proposal-template').select_option('FORFAIT')
        self.page.once('dialog',lambda dialog:dialog.dismiss())
        self.page.locator('#apply-template').click()
        expect(editor.locator('[name=title]')).to_have_value(re.compile('Cadrage de solution SaaS'))
        self.page.once('dialog',lambda dialog:dialog.accept())
        self.page.locator('#apply-template').click()
        expect(editor.locator('[name=title]')).to_have_value(re.compile('Projet au forfait'))
        self.page.locator('#cancel').click()
        expect(editor.locator('[name=scope]')).to_have_value('')
        expect(self.page.locator('#apply-template')).to_be_disabled()
        self.page.set_viewport_size({'width':390,'height':844})
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'))
        self.assertEqual(self.errors, [])

    def test_crm_prospect_conversion(self):
        org = self.seed('/api/admin/crm/organizations', {'name':'Prospect V126 fictif','kind':'PROSPECT','country':'Guinée','notes':'Historique'})
        opportunity = {'company':'Prospect V126 fictif','contact':'','email':'','title':'Mission V126','mode':'CONSEIL','skills':'','consultant_id':'','next_action':'','followup':'','notes':'','status':'GAGNE','organization_id':org['id']}
        self.seed('/api/admin/crm', opportunity)
        self.page.goto('/crm.html')
        self.page.locator('#token').fill(server.ADMIN_TOKEN)
        self.page.locator('#login-form button').click()
        row = self.page.locator('#org-rows tr').filter(has_text='Prospect V126 fictif')
        expect(row).to_contain_text('1 gagnée(s)')
        self.page.once('dialog', lambda dialog: dialog.accept())
        row.get_by_role('button', name='Convertir en client').click()
        expect(row).to_contain_text('CLIENT')
        expect(row.get_by_role('button', name='Convertir en client')).to_have_count(0)
        expect(self.page.locator('#org-notice')).to_contain_text('Historique conservé')
        self.assertEqual(self.errors, [])

    def test_crm_qualification_editor(self):
        self.page.goto('/crm.html')
        self.page.locator('#token').fill(server.ADMIN_TOKEN)
        self.page.locator('#login-form button').click()
        expect(self.page.locator('#workspace')).to_be_visible()
        editor = self.page.locator('#editor')
        editor.locator('[name=company]').fill('Prospect V125 fictif')
        editor.locator('[name=title]').fill('Démo V125')
        editor.locator('[name=qualification_need]').select_option('YES')
        editor.locator('[name=qualification_budget]').select_option('YES')
        editor.locator('[name=qualification_demo_status]').select_option('SCHEDULED')
        editor.locator('[name=qualification_demo_date]').fill('2027-01-15')
        expect(editor.locator('.crm-qualification p')).to_contain_text('2/4')
        self.page.locator('#save').click()
        expect(self.page.locator('#rows')).to_contain_text('Démo V125')
        self.page.locator('#rows').get_by_role('button', name='Modifier').click()
        expect(editor.locator('[name=qualification_need]')).to_have_value('YES')
        expect(editor.locator('[name=qualification_demo_date]')).to_have_value('2027-01-15')
        self.page.set_viewport_size({'width':390,'height':844})
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'))
        self.assertEqual(self.errors, [])

    def test_admin_mfa_all_modules_and_logout(self):
        self.activate('admin.e2e', 'ADMIN')
        expect(self.page.locator('#modules a')).to_have_count(0)
        expect(self.page.locator('#notice')).to_contain_text('MFA obligatoire')
        self.page.locator('#mfa-setup [name=password]').fill(self.password)
        self.page.locator('#mfa-setup button').click()
        expect(self.page.locator('#mfa-pending')).to_be_visible()
        secret = self.page.locator('#secret').input_value()
        self.page.locator('#mfa-confirm [name=code]').fill(server.authentication.totp(secret, int(time.time())//30))
        self.page.locator('#mfa-confirm button').click()
        expect(self.page.locator('#recovery')).to_be_visible()
        code = self.page.locator('#recovery-codes').inner_text().splitlines()[0]
        self.page.locator('#dismiss-recovery').click()
        self.login('admin.e2e', code)
        expect(self.page.locator('#modules a')).to_have_count(16)
        for module in ('admin','crm','taches','appointments','quotes','tenders','consultants','recruitment','missions','billing','direction','accounts','audit','documents','alerts','notifications'):
            with self.subTest(module=module):
                self.page.goto('/'+module+'.html')
                if module=='audit':
                    expect(self.page.locator('#notice')).to_contain_text('événements correspondants')
                    expect(self.page.locator('#rows tr').first).to_be_visible()
                    expect(self.page.get_by_role('combobox',name='Éléments par page')).to_have_value('10')
                else: expect(self.page.locator('#dashboard' if module=='admin' else '#workspace')).to_be_visible()
                active = self.page.locator('.app-sidebar nav a[aria-current="page"]')
                expect(active).to_have_attribute('href', module+'.html')
                expect(active).to_have_css('min-height','44px')
                expect(active).to_have_css('font-weight','700')
                expect(self.page.locator('body')).to_have_css('background-color','rgb(245, 246, 250)')
                self.assert_responsive(module)
                if module=='accounts':
                    expect(self.page.locator('#events')).to_have_count(0)
                    expect(self.page.locator('.app-sidebar nav a[href="audit.html"]')).to_be_visible()
                    own=self.page.locator('#rows tr').filter(has_text='admin.e2e')
                    expect(own).to_contain_text('Activé')
                    expect(own.get_by_role('combobox')).to_be_disabled()
                    expect(own.get_by_role('button')).to_be_disabled()
                    self.page.locator('#create [name=username]').fill('commercial.v53')
                    self.page.locator('#create [name=role]').select_option('COMMERCIAL')
                    self.page.locator('#create button[type=submit]').click()
                    expect(self.page.locator('#key')).to_be_visible()
                    expect(self.page.locator('#rows tr').filter(has_text='commercial.v53')).to_contain_text('À activer')
                    self.page.locator('#clear-key').click()
                    expect(self.page.locator('#key')).to_be_hidden()
                if module in ('crm','missions','billing'):
                    links=self.page.locator('.workflow-nav a')
                    self.assertGreaterEqual(links.count(),2)
                    for link in links.all():
                        target=link.get_attribute('href')
                        expect(self.page.locator(target)).to_be_visible()
                    links.last.click()
                    self.assertTrue(self.page.evaluate('location.hash.length > 1'))
                    self.page.set_viewport_size({'width':390,'height':844})
                    self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'))
                    self.page.set_viewport_size({'width':1280,'height':900})
                if module=='crm':
                    expect(self.page.locator('#catalogue-rows')).to_contain_text('Guinée Logistique')
                    expect(self.page.locator('#catalogue-rows')).to_contain_text('Prototype de démonstration')
                    sc=self.page.locator('#sc-form')
                    sc.locator('[name=period]').fill('2026-11')
                    for key,value in {'shipments':100,'on_time':95,'otif':90,'checked':50,'accurate':48,'cost':100000,'km':1000}.items():
                        sc.locator('[name='+key+']').fill(str(value))
                    sc.get_by_role('button',name='Calculer les indicateurs').click()
                    expect(self.page.locator('#sc-results .count')).to_have_count(5)
                    expect(self.page.locator('#sc-results')).to_contain_text('90 %')
                    expect(self.page.locator('#sc-results')).to_contain_text('96 %')
                    sc.locator('[name=otif]').fill('96')
                    sc.get_by_role('button',name='Calculer les indicateurs').click()
                    expect(self.page.locator('#sc-notice')).to_contain_text('Incohérence')
                    expect(self.page.locator('#sc-results .count')).to_have_count(0)
                    for key in ('shipments','on_time','otif','checked','accurate','km'):
                        sc.locator('[name='+key+']').fill('0')
                    sc.get_by_role('button',name='Calculer les indicateurs').click()
                    expect(self.page.locator('#sc-results .count').filter(has_text='Non calculable')).to_have_count(5)
                    sc.get_by_role('button',name='Effacer le diagnostic').click()
                    expect(self.page.locator('#sc-results .count')).to_have_count(0)
                    self.page.locator('#org-editor [name=name]').fill('Organisation fictive E2E')
                    self.page.locator('#org-editor [name=kind]').select_option('CLIENT')
                    self.page.locator('#org-editor button').first.click()
                    expect(self.page.locator('#org-rows')).to_contain_text('Organisation fictive E2E')
                    self.page.locator('#org-rows').get_by_role('button',name='Associer').click()
                    self.page.locator('#editor [name=title]').fill('Mission fictive E2E')
                    self.page.locator('#save').click()
                    expect(self.page.locator('#rows')).to_contain_text('Mission fictive E2E')
                    self.page.locator('#rows').get_by_role('button',name='Modifier').click()
                    expect(self.page.locator('#editor [name=organization_id]')).not_to_have_value('')
                if module=='direction':
                    expect(self.page.locator('.app-sidebar nav a[aria-current="page"]')).to_have_text('Pilotage')
                    expect(self.page.locator('#breakdown .status-card')).to_have_count(5)
                    self.page.set_viewport_size({'width':390,'height':844})
                    self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'))
                    self.page.set_viewport_size({'width':1280,'height':900})
                    expect(self.page.locator('#control-tables table')).to_have_count(6)
                    expect(self.page.locator('#control-tables')).to_contain_text('Budget coût consommé (%)')
                    expect(self.page.locator('#control-tables')).to_contain_text('Rentabilité par contrat')
                    expect(self.page.locator('#control-tables')).to_contain_text('Flux net affecté')
                    expect(self.page.locator('#control-tables')).to_contain_text('Jours facturables / travaillés (%)')
                    self.page.locator('#control-currency').select_option('GNF')
                    expect(self.page.locator('#control-tables')).to_contain_text('Aucun résultat.')
                    expect(self.page.locator('#control-tables')).to_contain_text('Flux de trésorerie enregistrés')
                    self.page.locator('#control-export-table').select_option('3')
                    with self.page.expect_download() as download:
                        self.page.locator('#control-export').click()
                    self.assertEqual(download.value.suggested_filename,'dsig-pilotage-tresorerie.csv')
                    csv=Path(download.value.path()).read_text(encoding='utf-8-sig')
                    self.assertIn('"Devise";"Entrées";"Sorties";"Flux net"',csv)
                    self.assertEqual(self.page.evaluate("controlCsvCell('=1+1')"), "\"'=1+1\"")
                    self.assertEqual(self.page.evaluate("controlCsvCell('-1000')"), '"-1000"')
                    self.page.locator('#report-start').fill('2020-01-01')
                    self.page.locator('#report-end').fill('2020-01-31')
                    self.page.locator('#report-form').get_by_role('button',name='Afficher').click()
                    expect(self.page.locator('#report-rows')).to_contain_text('-1000')
                    expect(self.page.locator('#report-export')).to_be_enabled()
                if module=='alerts':
                    expect(self.page.locator('#alert-counts .count')).to_have_count(6)
                    self.page.locator('#horizon').select_option('60')
                    self.page.locator('#filter button').click()
                    expect(self.page.locator('#summary')).to_contain_text('60 jours')
                if module=='billing':
                    self.page.locator('#expense [name=reference]').fill('DEP-E2E')
                    self.page.locator('#expense [name=amount]').fill('1000')
                    self.page.locator('#expense [name=paid_date]').fill('2020-01-01')
                    self.page.locator('#expense [name=description]').fill('Décaissement fictif')
                    self.page.locator('#expense button').click()
                    expect(self.page.locator('#expense-rows')).to_contain_text('DEP-E2E')
                    expect(self.page.locator('#cash-rows')).to_contain_text('-1000')
        self.page.goto('/connexion.html')
        expect(self.page.locator('#workspace')).to_be_visible()
        self.page.locator('#logout').click()
        expect(self.page.locator('#login')).to_be_visible()
        self.page.goto('/admin.html')
        expect(self.page.locator('#login')).to_be_visible()
        self.assertEqual(self.errors, [])

    def test_consultant_scope(self):
        profile = self.seed('/api/admin/consultants', {'name':'Consultant fictif','email':'qa@example.invalid','role':'Data Engineer','skills':'Python','location':'Guinée','experience':'5','availability':'Immédiate','notes':'','status':'DISPONIBLE'})
        self.activate('consultant.e2e', 'CONSULTANT', profile['id'])
        expect(self.page.locator('#modules a')).to_have_count(1)
        self.page.locator('#modules a').click()
        expect(self.page.locator('#workspace')).to_be_visible()
        expect(self.page.locator('.app-sidebar nav a')).to_have_count(2)
        expect(self.page.locator('.app-sidebar nav a[href="my-activity.html"]')).to_be_visible()
        expect(self.page.locator('.app-sidebar nav a[href="accounts.html"]')).to_have_count(0)
        self.assert_responsive('my-activity.html')
        self.page.goto('/accounts.html')
        expect(self.page.locator('#notice')).to_contain_text('Permission insuffisante')
        expect(self.page.locator('#workspace')).to_be_hidden()
        self.assertEqual(self.errors, [])


    def test_non_admin_role_navigation_and_api_matrix(self):
        profile = self.seed('/api/admin/consultants', {'name':'Consultant V90 fictif','email':'v90@example.invalid','role':'Data Engineer','skills':'Python','location':'Guinée','experience':'5','availability':'Immédiate','notes':'','status':'DISPONIBLE'})
        opportunity = self.seed('/api/admin/crm', {'company':'Client V90 fictif','contact':'Contact fictif','email':'client90@example.invalid','title':'Forfait V90','mode':'FORFAIT','skills':'Python','consultant_id':'','next_action':'','followup':'','notes':'','status':'QUALIFIE'})
        quote = self.seed('/api/admin/quotes', {'opportunity_id':opportunity['id'],'title':'Livraison V90','scope':'Livrable fictif','mode':'FORFAIT','currency':'EUR','days':'5','rate':'0','daily_cost':'100','expenses':'0','fixed_price':'1000','status':'PROPOSE','valid_until':'2099-01-01','terms':'Recette fictive'})
        route = '/api/admin/quotes/'+quote['id']
        for action in ('TRANSMIS','ACCEPTE'):
            response = self.context.request.post(route+'/transmission',data={'version':1,'action':action,'evidence':'Preuve fictive V90'},headers={'Authorization':'Bearer '+server.ADMIN_TOKEN})
            self.assertEqual(response.status,200,response.text())
        self.seed(route+'/contract',{'version':2,'reference':'V90-CONTRAT','signed_date':'2020-01-01','evidence':'Signature fictive'})
        self.seed('/api/admin/missions',{'quote_id':quote['id'],'consultant_id':profile['id'],'contract_ref':'V90-CONTRAT','start_date':'2020-01-01','end_date':'2020-01-31'})
        # Independent business expectations, not derived from the implementation.
        matrix = {
            'DIRECTION': ({'direction','billing','missions','quotes','crm','tenders','alerts'}, {'notifications'}),
            'COMMERCIAL': ({'consultants'}, {'requests','crm','quotes','tenders'}),
            'RH': ({'requests'}, {'consultants','recruitment'}),
            'PROJET': ({'consultants','quotes'}, {'missions'}),
            'CONTROLE': ({'direction','missions','billing','quotes'}, set()),
            'COMPTABLE': ({'missions'}, {'billing'}),
            'AUDITEUR': ({'direction','audit'}, set()),
        }
        pages = {
            'requests':'admin.html', 'crm':'crm.html', 'quotes':'quotes.html',
            'tenders':'tenders.html', 'consultants':'consultants.html',
            'recruitment':'recruitment.html', 'missions':'missions.html',
            'billing':'billing.html', 'direction':'direction.html',
            'accounts':'accounts.html', 'audit':'audit.html',
            'documents':'documents.html', 'alerts':'alerts.html',
            'notifications':'notifications.html',
        }
        nested = {
            'crm': ('crm/tasks','crm/catalogue','crm/organizations','crm/appointments','crm/saas-commercial','crm/saas-renewals','crm/customer-success','crm/customer-growth','crm/partners'),
            'billing': ('billing/expenses','billing/milestones','billing/contracts','billing/schedule','billing/receivables','billing/forecast','billing/planned-expenses','billing/saas-monthly','billing/partner-commissions','billing/partner-targets','billing/partner-costs','billing/reconciliation'),
            'direction': ('direction/saas-monthly','direction/saas-commercial','direction/saas-renewals','direction/customer-success','direction/customer-growth','direction/partners','direction/partner-commissions','direction/partner-profitability','direction/partner-targets','direction/financial-consolidation','direction/reconciliation'),
            'missions': ('missions/eligible',),
        }
        for role, (read, write) in matrix.items():
            with self.subTest(role=role):
                self.context.clear_cookies()
                # Isolate each fictitious user's login rate-limit fixture.
                server.authentication.ATTEMPTS.clear()
                username = role.lower()+'.v56'
                self.activate(username, role)
                if role in {'DIRECTION','CONTROLE','COMPTABLE','AUDITEUR'}:
                    expect(self.page.locator('#modules a')).to_have_count(0)
                    self.page.locator('#mfa-setup [name=password]').fill(self.password)
                    self.page.locator('#mfa-setup button').click()
                    expect(self.page.locator('#mfa-pending')).to_be_visible()
                    secret = self.page.locator('#secret').input_value()
                    self.page.locator('#mfa-confirm [name=code]').fill(server.authentication.totp(secret, int(time.time())//30))
                    self.page.locator('#mfa-confirm button').click()
                    expect(self.page.locator('#recovery')).to_be_visible()
                    code = self.page.locator('#recovery-codes').inner_text().splitlines()[0]
                    self.page.locator('#dismiss-recovery').click()
                    self.login(username, code)
                allowed = read | write
                expected = {pages[resource] for resource in allowed}
                if 'crm' in allowed:
                    expected.update({'appointments.html','taches.html'})
                expect(self.page.locator('#modules a')).to_have_count(len(expected))
                self.assertEqual(set(self.page.locator('#modules a').evaluate_all('(nodes) => nodes.map(a => a.getAttribute("href"))')), expected)
                for resource in allowed:
                    mode = 'Lecture / écriture' if resource in write else 'Lecture'
                    expect(self.page.locator(f'#modules a[href="{pages[resource]}"] .module-mode')).to_have_text(mode)
                # Direct API checks use the authenticated browser cookie, never bootstrap.
                headers = {'Authorization':'Bearer session'}
                for resource in pages:
                    response = self.context.request.get('/api/admin/'+resource, headers=headers)
                    self.assertEqual(response.status, 200 if resource in allowed else 403, f'{role}: {resource}')
                for resource, paths in nested.items():
                    for path in paths:
                        response = self.context.request.get('/api/admin/'+path, headers=headers)
                        self.assertEqual(response.status, 200 if resource in allowed else 403, f'{role}: {path}')
                for target in sorted(expected):
                    with self.subTest(role=role, target=target):
                        response = self.page.goto('/'+target)
                        self.assertEqual(response.status, 200)
                        nav = self.page.locator('.app-sidebar nav a')
                        expect(nav).to_have_count(len(expected)+1)
                        self.assertEqual(set(nav.evaluate_all('(nodes) => nodes.map(a => a.getAttribute("href"))')), expected | {'connexion.html'})
                        expect(self.page.locator('.app-sidebar nav a[aria-current="page"]')).to_have_attribute('href', target)
                        if target == 'audit.html':
                            expect(self.page.locator('#notice')).to_contain_text('événements correspondants')
                        else:
                            expect(self.page.locator('#dashboard' if target=='admin.html' else '#workspace')).to_be_visible()
                        if target == 'missions.html':
                            response = self.context.request.get('/api/admin/missions', headers=headers)
                            self.assertEqual(response.json()['can_write'], 'missions' in write)
                            if 'missions' in write:
                                expect(self.page.locator('#mission')).to_be_visible()
                            else:
                                expect(self.page.locator('#mission')).to_be_hidden()
                                row = self.page.locator('#rows tr').filter(has_text='Livraison V90')
                                expect(row).to_be_visible()
                                row.locator('.row-actions summary').click()
                                expect(row.get_by_role('button',name='Clôturer')).to_have_count(0)
                                row.get_by_role('button',name='CRA',exact=True).click()
                                expect(self.page.locator('#cra')).to_be_visible()
                                expect(self.page.locator('#activity')).to_be_hidden()
                                self.assertEqual(self.context.request.post('/api/admin/missions', headers={**headers,'Origin':self.url}, data={}).status,403)
                        self.assert_responsive(target)
                self.page.goto('/accounts.html')
                expect(self.page.locator('#notice')).to_contain_text('Permission insuffisante')
                expect(self.page.locator('#workspace')).to_be_hidden()
                self.page.goto('/connexion.html')
                expect(self.page.locator('#workspace')).to_be_visible()
                self.page.locator('#logout').click()
                expect(self.page.locator('#login')).to_be_visible()
                revoked = self.context.request.get('/api/admin/'+sorted(allowed)[0], headers=headers)
                self.assertEqual(revoked.status, 401, f'{role}: session after logout')
        self.assertEqual(self.errors, [])

    def test_client_portal_session_and_support(self):
        org=self.seed('/api/admin/crm/organizations',{'name':'Client navigateur fictif','kind':'CLIENT','country':'Guinée','notes':''})
        account=self.seed('/api/admin/accounts',{'username':'client.browser','role':'CLIENT','consultant_id':'','organization_id':org['id']})
        self.page.goto('/connexion.html')
        for name,value in {'username':'client.browser','key':account['key'],'password':self.password}.items():
            self.page.locator(f'#activate [name={name}]').fill(value)
        self.page.locator('#activate button').click()
        expect(self.page.locator('#notice')).to_contain_text('Activation effectuée')
        self.login('client.browser')
        expect(self.page.locator('#modules a')).to_have_count(0)
        self.page.locator('#mfa-setup [name=password]').fill(self.password)
        self.page.locator('#mfa-setup button').click()
        expect(self.page.locator('#mfa-pending')).to_be_visible()
        secret=self.page.locator('#secret').input_value()
        self.page.locator('#mfa-confirm [name=code]').fill(server.authentication.totp(secret,int(time.time())//30))
        self.page.locator('#mfa-confirm button').click()
        expect(self.page.locator('#recovery')).to_be_visible()
        code=self.page.locator('#recovery-codes').inner_text().splitlines()[0]
        self.page.locator('#dismiss-recovery').click()
        self.login('client.browser',code)
        expect(self.page.locator('#modules a')).to_have_count(1)
        self.page.locator('#modules a[href="client-portal.html"]').click()
        expect(self.page.locator('#workspace')).to_be_visible()
        expect(self.page.locator('#organization')).to_have_text('Client navigateur fictif')
        self.page.locator('#ticket [name=title]').fill('Demande fictive navigateur')
        self.page.locator('#ticket [name=description]').fill('Description de test')
        self.page.locator('#ticket button').click()
        expect(self.page.locator('#rows')).to_contain_text('Demande fictive navigateur')
        self.assert_responsive('client-portal.html')
        self.page.locator('#logout').click()
        self.page.wait_for_url('**/connexion.html')
        expect(self.page.locator('#login')).to_be_visible()
        self.assertEqual(self.context.request.get('/api/admin/client-portal',headers={'Authorization':'Bearer session'}).status,401)
        self.assertEqual(self.errors,[])

    def test_anonymous_private_routes_and_crm_workspace(self):
        # A public static shell must not grant access to private records.
        paths = (
            'requests','crm','crm/catalogue','crm/organizations','crm/appointments',
            'quotes','tenders','consultants','recruitment','missions','missions/eligible',
            'billing','billing/expenses','billing/contracts','billing/milestones',
            'billing/schedule','billing/receivables','billing/forecast','billing/planned-expenses',
            'direction','direction/reporting','accounts','audit','documents',
            'alerts','notifications','my-activity','client-portal',
        )
        for path in paths:
            with self.subTest(path=path):
                response = self.context.request.get('/api/admin/'+path)
                self.assertEqual(response.status, 401)
                self.assertNotIn('items', response.json())
        self.page.goto('/crm.html')
        expect(self.page.locator('#login')).to_be_visible()
        expect(self.page.locator('#workspace')).to_be_hidden()
        expect(self.page.locator('#supply-chain')).to_be_hidden()
        self.assertEqual(self.errors, [])


    def test_cockpit_dashboard(self):
        for i,need in enumerate(('Mission en régie','Data & IA')):
            server.RATE.clear()
            response=self.context.request.post('/api/requests',data={'nom':'Contact cockpit','org':f'Cockpit {i} fictif','email':f'cockpit{i}@example.invalid','besoin':need,'solution':'','message':'Fictif','consent':True,'website':''})
            self.assertEqual(response.status,201)
        self.seed('/api/admin/crm',{'company':'Cockpit gagné fictif','contact':'Contact fictif','email':'won@example.invalid','title':'Mission gagnée','mode':'CONSEIL','skills':'','consultant_id':'','next_action':'','followup':'','notes':'','status':'GAGNE'})
        self.activate('commercial.cockpit','COMMERCIAL')
        cockpit=self.page.locator('#cockpit')
        expect(cockpit.get_by_role('heading',name='Tableau de bord')).to_be_visible()
        expect(cockpit.locator('.kpi').filter(has_text='Demandes nouvelles')).to_contain_text('2')
        expect(cockpit.locator('.kpi').filter(has_text='Opportunités ouvertes')).to_contain_text('2')
        expect(cockpit.locator('.kpi').filter(has_text='Gagnées / en mission')).to_contain_text('1')
        expect(cockpit.get_by_role('img',name='Pipeline commercial',exact=False)).to_have_attribute('aria-label','Pipeline commercial : Prospect 2, Qualifié 0, Proposition 0, Négociation 0, Gagné 1, En mission 0, Terminé 0, Perdu 0')
        expect(cockpit.locator('.cockpit-list').first).to_contain_text('Cockpit 1 fictif · Data & IA')
        expect(cockpit.locator('.kpi').filter(has_text='Alertes')).to_have_count(0)
        self.assert_responsive('/connexion.html cockpit')
        cockpit.locator('.kpi').filter(has_text='Opportunités ouvertes').click()
        expect(self.page.locator('#kanban .kanban-card')).to_have_count(3)
        self.page.goto('/connexion.html')
        expect(cockpit.locator('.kpi').first).to_be_visible()
        self.page.locator('#logout').click()
        expect(self.page.locator('#login')).to_be_visible()
        expect(cockpit.locator('.kpi')).to_have_count(0)
        self.assertEqual(self.errors, [])

    def test_commercial_tasks_from_kanban(self):
        admin={'Authorization':'Bearer '+server.ADMIN_TOKEN}
        opp={'company':'Tâches fictives','contact':'','email':'','title':'Projet tâches','mode':'CONSEIL','skills':'','consultant_id':'','next_action':'','followup':'','notes':'','status':'PROSPECT'}
        self.assertEqual(self.context.request.post('/api/admin/crm',data=opp,headers=admin).status,201)
        self.page.goto('/crm.html')
        self.page.locator('#token').fill(server.ADMIN_TOKEN)
        self.page.locator('#login-form button').click()
        self.page.locator('#kanban').get_by_role('link',name='Nouvelle tâche pour Projet tâches').click()
        self.page.locator('#token').fill(server.ADMIN_TOKEN)
        self.page.locator('#login-form button').click()
        expect(self.page.locator('#task-opportunity option:checked')).to_have_text('Tâches fictives · Projet tâches')
        expect(self.page.locator('#task-form [name=title]')).to_be_focused()
        self.page.locator('#task-form [name=title]').fill('Appeler pour cadrage')
        self.page.locator('#task-form button').click()
        expect(self.page.locator('#notice')).to_have_text('Tâche ajoutée.')
        self.page.locator('#view').select_option('team')
        item=self.page.locator('.task-list li').filter(has_text='Appeler pour cadrage')
        expect(item).to_contain_text('Tâches fictives · Projet tâches')
        expect(self.page.get_by_role('heading',name='Aujourd’hui (1)')).to_be_visible()
        self.assert_responsive('/taches.html')
        item.get_by_role('button',name='Reporter à demain : Appeler pour cadrage').click()
        expect(self.page.get_by_role('heading',name='À venir (1)')).to_be_visible()
        self.page.locator('.task-list li').filter(has_text='Appeler pour cadrage').get_by_role('button',name='Marquer comme faite : Appeler pour cadrage').click()
        expect(self.page.locator('#task-groups')).to_contain_text('Aucune tâche à faire')
        self.page.locator('#state').select_option('done')
        expect(self.page.get_by_role('heading',name='Terminées (1)')).to_be_visible()
        self.assertEqual(self.errors, [])

    def test_mobile_shell_and_installable_app(self):
        server.authentication.ATTEMPTS.clear()
        self.activate('commercial.mobile', 'COMMERCIAL')
        self.page.set_viewport_size({'width':390,'height':844})
        self.page.goto('/taches.html')
        expect(self.page.locator('#workspace')).to_be_visible()
        toggle=self.page.locator('.sidebar-toggle')
        expect(toggle).to_be_visible()
        expect(self.page.locator('#app-modules')).to_be_hidden()
        toggle.click()
        expect(toggle).to_have_attribute('aria-expanded','true')
        expect(self.page.locator('#app-modules a[href="crm.html"]')).to_be_visible()
        self.page.keyboard.press('Escape')
        expect(toggle).to_have_attribute('aria-expanded','false')
        expect(toggle).to_be_focused()
        bar=self.page.locator('.app-bottombar')
        expect(bar).to_be_visible()
        self.assertEqual(bar.locator('a').evaluate_all('(nodes) => nodes.map(a => a.textContent)'), ['Accueil','Tâches','CRM'])
        expect(bar.locator('a[aria-current="page"]')).to_have_text('Tâches')
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'))
        # Service worker: registered, and it never stores API responses (customer data).
        self.assertEqual(self.page.evaluate("navigator.serviceWorker.ready.then(r => r.active.scriptURL.endsWith('/sw.js'))"), True)
        self.page.reload()
        expect(self.page.locator('#workspace')).to_be_visible()
        cached=self.page.evaluate("caches.keys().then(keys => Promise.all(keys.map(k => caches.open(k).then(c => c.keys())))).then(all => all.flat().map(r => new URL(r.url).pathname))")
        self.assertIn('/offline.html', cached)
        self.assertFalse([url for url in cached if url.startswith('/api/')])
        self.page.set_viewport_size({'width':1280,'height':900})
        expect(toggle).to_be_hidden()
        expect(bar).to_be_hidden()
        expect(self.page.locator('#app-modules')).to_be_visible()
        self.assertEqual(self.errors, [])

    def test_weekly_report_page(self):
        server.RATE.clear()
        self.assertEqual(self.context.request.post('/api/requests',data={'nom':'Contact rapport','org':'Rapport fictif','email':'rapport@example.invalid','besoin':'Projet au forfait','solution':'','message':'Fictif','consent':True,'website':''}).status,201)
        self.page.goto('/direction.html')
        self.page.locator('#token').fill(server.ADMIN_TOKEN)
        self.page.locator('#login-form button').click()
        self.page.get_by_role('link',name='Rapport hebdomadaire (CSV / PDF)').click()
        self.page.locator('#token').fill(server.ADMIN_TOKEN)
        self.page.locator('#login-form button').click()
        expect(self.page.locator('#report-kpis .kpi').filter(has_text='Demandes reçues')).to_contain_text('1')
        expect(self.page.locator('#need-rows')).to_contain_text('Projet au forfait')
        expect(self.page.locator('#next')).to_be_disabled()
        with self.page.expect_download() as download:
            self.page.locator('#export-csv').click()
        self.assertRegex(download.value.suggested_filename, r'^rapport-direction-\d{4}-W\d{2}\.csv$')
        self.assertIn('Demandes reçues;1', Path(download.value.path()).read_text(encoding='utf-8-sig'))
        self.page.locator('#previous').click()
        expect(self.page.locator('#report-kpis .kpi').filter(has_text='Demandes reçues')).to_contain_text('0')
        expect(self.page.locator('#next')).to_be_enabled()
        self.page.emulate_media(media='print')
        expect(self.page.locator('.report-toolbar')).to_be_hidden()
        expect(self.page.locator('#report-kpis')).to_be_visible()
        self.page.emulate_media(media='screen')
        self.assert_responsive('/rapport.html')
        self.assertNotIn('rapport@example.invalid', self.page.content())
        self.assertEqual(self.errors, [])

    def test_client_email_templates(self):
        admin={'Authorization':'Bearer '+server.ADMIN_TOKEN}
        server.RATE.clear()
        rid=self.context.request.post('/api/requests',data={'nom':'Awa Courriel','org':'Courriel fictif','email':'courriel@example.invalid','besoin':'Projet au forfait','solution':'','message':'Fictif','consent':True,'website':''}).json()['id']
        self.assertEqual(self.context.request.patch('/api/admin/requests/'+rid,data={'status':'QUALIFIEE','previous':'NOUVELLE'},headers=admin).status,200)
        self.assertEqual(self.context.request.post('/api/admin/requests/'+rid+'/convert',headers=admin).status,201)
        self.page.goto('/crm.html')
        self.page.locator('#token').fill(server.ADMIN_TOKEN)
        self.page.locator('#login-form button').click()
        self.page.locator('#kanban').get_by_role('link',name='Fiche client Courriel fictif').click()
        self.page.locator('#token').fill(server.ADMIN_TOKEN)
        self.page.locator('#login-form button').click()
        expect(self.page.locator('#composer')).to_be_visible()
        expect(self.page.locator('#manage-templates')).to_be_visible()
        self.page.locator('#compose-template').select_option(label='Relance (FR)')
        self.page.locator('#compose-preview').click()
        expect(self.page.locator('#compose-to')).to_have_value('courriel@example.invalid')
        expect(self.page.locator('#compose-subject')).to_have_value('DSIG — Suite à notre échange : Projet au forfait')
        expect(self.page.locator('#compose-body')).to_have_value(re.compile('^Bonjour Awa Courriel,'))
        self.page.locator('#compose-subject').fill('Relance ajustée')
        self.page.locator('#compose-message button').click()
        expect(self.page.locator('#notice')).to_contain_text('E-mail enregistré dans l’historique')
        expect(self.page.locator('#compose-mailto')).to_have_attribute('href',re.compile(r'^mailto:courriel%40example\.invalid\?subject=Relance%20ajust%C3%A9e&body=Bonjour'))
        expect(self.page.get_by_role('heading',name='E-mails préparés (1)')).to_be_visible()
        expect(self.page.locator('.timeline')).to_contain_text('E-mail préparé : Relance ajustée (bootstrap)')
        self.assert_responsive('/client.html composer')
        self.page.locator('#manage-templates').click()
        self.page.locator('#token').fill(server.ADMIN_TOKEN)
        self.page.locator('#login-form button').click()
        self.page.get_by_role('button',name='Modifier le modèle Relance').first.click()
        self.page.locator('#editor [name=name]').fill('Relance douce')
        self.page.locator('#editor [name=body]').fill('Bonjour {nom}')
        self.page.locator('#editor button').first.click()
        expect(self.page.locator('#notice')).to_have_text('Modèle ou message invalide.')
        self.page.locator('#editor [name=body]').fill('Bonjour {contact},' + chr(10) + 'Petit rappel amical.' + chr(10) + '{commercial}')
        self.page.locator('#editor button').first.click()
        expect(self.page.locator('#notice')).to_have_text('Modèle enregistré.')
        expect(self.page.locator('#rows')).to_contain_text('Relance douce')
        self.assert_responsive('/modeles-email.html')
        self.assertEqual(self.errors, [])

    def test_client_360_sheet(self):
        admin={'Authorization':'Bearer '+server.ADMIN_TOKEN}
        server.RATE.clear()
        rid=self.context.request.post('/api/requests',data={'nom':'Contact fiche','org':'Fiche 360 fictive','email':'fiche@example.invalid','besoin':'Projet au forfait','solution':'','message':'Fictif','consent':True,'website':''}).json()['id']
        self.assertEqual(self.context.request.patch('/api/admin/requests/'+rid,data={'status':'QUALIFIEE','previous':'NOUVELLE'},headers=admin).status,200)
        self.assertEqual(self.context.request.post('/api/admin/requests/'+rid+'/convert',headers=admin).status,201)
        self.page.goto('/crm.html')
        self.page.locator('#token').fill(server.ADMIN_TOKEN)
        self.page.locator('#login-form button').click()
        expect(self.page.locator('#kanban').get_by_role('link',name='Fiche client Fiche 360 fictive')).to_be_visible()
        self.page.locator('#org-rows').get_by_role('link',name='Fiche client Fiche 360 fictive').click()
        self.page.locator('#token').fill(server.ADMIN_TOKEN)
        self.page.locator('#login-form button').click()
        expect(self.page.locator('h1')).to_have_text('Fiche 360 fictive')
        expect(self.page.locator('#client-kpis .kpi').filter(has_text='Opportunités ouvertes')).to_contain_text('1')
        expect(self.page.get_by_role('heading',name='Opportunités (1)')).to_be_visible()
        expect(self.page.get_by_role('heading',name='Demandes reçues (1)')).to_be_visible()
        timeline=self.page.locator('.timeline')
        expect(timeline).to_contain_text('Demande web : Projet au forfait (Contact fiche)')
        expect(timeline).to_contain_text('Projet au forfait → QUALIFIE')
        self.assert_responsive('/client.html')
        self.page.goto('/client.html?id=invalid')
        self.page.locator('#token').fill(server.ADMIN_TOKEN)
        self.page.locator('#login-form button').click()
        expect(self.page.locator('#notice')).to_contain_text('Organisation non précisée')
        expect(self.page.locator('#workspace')).to_be_hidden()
        self.assertEqual(self.errors, [])

    def test_topbar_global_search(self):
        admin={'Authorization':'Bearer '+server.ADMIN_TOKEN}
        server.RATE.clear()
        rid=self.context.request.post('/api/requests',data={'nom':'Contact recherche','org':'Énergie Recherche fictive','email':'search@example.invalid','besoin':'Data & IA','solution':'','message':'Fictif','consent':True,'website':''}).json()['id']
        self.context.request.patch('/api/admin/requests/'+rid,data={'status':'QUALIFIEE','previous':'NOUVELLE'},headers=admin)
        self.assertEqual(self.context.request.post('/api/admin/requests/'+rid+'/convert',headers=admin).status,201)
        self.activate('commercial.search','COMMERCIAL')
        self.page.locator('#modules a[href="crm.html"]').click()
        expect(self.page.locator('#workspace')).to_be_visible()
        expect(self.page.locator('header .topbar-role')).to_have_text('COMMERCIAL')
        search=self.page.get_by_role('searchbox',name='Recherche globale')
        self.page.keyboard.press('Control+k')
        expect(search).to_be_focused()
        search.fill('energie recherche')
        results=self.page.locator('#global-results')
        expect(results.get_by_role('link')).to_have_count(3)
        expect(results).to_contain_text('Organisation')
        expect(results).to_contain_text('Demande')
        self.page.keyboard.press('ArrowDown')
        expect(results.get_by_role('link').first).to_be_focused()
        self.page.keyboard.press('Escape')
        expect(results).to_be_hidden()
        expect(search).to_be_focused()
        search.fill('zz-introuvable')
        expect(results).to_contain_text('Aucun résultat')
        search.fill('energie recherche')
        results.get_by_role('link').filter(has_text='Organisation').click()
        expect(self.page.locator('h1')).to_have_text('Énergie Recherche fictive')
        expect(self.page.get_by_role('searchbox',name='Recherche globale')).to_be_visible()
        self.assert_responsive('/client.html topbar')
        self.assertEqual(self.errors, [])

    def test_crm_kanban_pipeline(self):
        base={'contact':'Contact fictif','email':'kanban@example.invalid','mode':'CONSEIL','skills':'Python','consultant_id':'','next_action':'Relancer','notes':''}
        first=self.seed('/api/admin/crm',{**base,'company':'Kanban A fictif','title':'Opportunité Kanban A','followup':'2020-01-01','status':'PROSPECT'})
        self.seed('/api/admin/crm',{**base,'company':'Kanban B fictif','title':'Opportunité Kanban B','followup':'','status':'QUALIFIE'})
        self.page.goto('/crm.html')
        self.page.locator('#token').fill(server.ADMIN_TOKEN)
        self.page.locator('#login-form button').click()
        board=self.page.locator('#kanban')
        expect(board.locator('.kanban-col')).to_have_count(8)
        prospect=board.locator('.kanban-col[data-status=PROSPECT]')
        card=prospect.locator('.kanban-card').filter(has_text='Opportunité Kanban A')
        expect(card).to_contain_text('En retard · 2020-01-01')
        # Keyboard-accessible move through the select.
        card.get_by_label('Déplacer Opportunité Kanban A vers une autre étape').select_option('PROPOSITION')
        expect(self.page.locator('#kanban-notice')).to_contain_text('déplacé vers Proposition')
        moved=board.locator('.kanban-col[data-status=PROPOSITION] .kanban-card').filter(has_text='Opportunité Kanban A')
        expect(moved).to_be_visible()
        expect(prospect.locator('.kanban-card')).to_have_count(0)
        # Drag and drop to another column.
        source=board.locator('.kanban-col[data-status=QUALIFIE] .kanban-card').filter(has_text='Opportunité Kanban B')
        source.drag_to(board.locator('.kanban-col[data-status=NEGOCIATION]'))
        expect(board.locator('.kanban-col[data-status=NEGOCIATION] .kanban-card').filter(has_text='Opportunité Kanban B')).to_be_visible()
        response=self.context.request.get('/api/admin/crm?status=PROPOSITION',headers={'Authorization':'Bearer '+server.ADMIN_TOKEN})
        item=next(x for x in response.json()['items'] if x['id']==first['id'])
        self.assertEqual((item['status'],item['version'],item['company'],item['followup']),('PROPOSITION',2,'Kanban A fictif','2020-01-01'))
        # Stale version is refused by the server and reported.
        stale=self.context.request.patch('/api/admin/crm/'+first['id'],data={**base,'company':'Kanban A fictif','title':'Opportunité Kanban A','followup':'2020-01-01','status':'GAGNE','version':1},headers={'Authorization':'Bearer '+server.ADMIN_TOKEN})
        self.assertEqual(stale.status,409)
        self.assert_responsive('/crm.html kanban')
        self.assertEqual(self.errors, [])

    def test_contract_renewal_alerts_and_notifications(self):
        from datetime import date, timedelta
        import notifications
        today=date.today()
        old_end=(today+timedelta(days=3)).isoformat()
        new_end=(today+timedelta(days=120)).isoformat()
        profile=self.seed('/api/admin/consultants',{'name':'Consultant V84 fictif','email':'v84@example.invalid','role':'Data Engineer','skills':'Python','location':'Guinée','experience':'5','availability':'Immédiate','notes':'','status':'DISPONIBLE'})
        opportunity=self.seed('/api/admin/crm',{'company':'Client V84 fictif','contact':'Contact fictif','email':'client84@example.invalid','title':'Renouvellement V84','mode':'REGIE','skills':'Python','consultant_id':'','next_action':'Relance fictive','followup':today.isoformat(),'notes':'','status':'QUALIFIE'})
        self.seed('/api/admin/crm',{'company':'Prospect relance V84','contact':'Contact fictif','email':'relance84@example.invalid','title':'Relance commerciale V84','mode':'CONSEIL','skills':'Python','consultant_id':'','next_action':'Relancer','followup':today.isoformat(),'notes':'','status':'QUALIFIE'})
        quote=self.seed('/api/admin/quotes',{'opportunity_id':opportunity['id'],'title':'Mission V84','scope':'Audit fictif','mode':'REGIE','currency':'EUR','days':'5','rate':'600','daily_cost':'400','expenses':'0','fixed_price':'0','status':'PROPOSE','valid_until':'2099-01-01','terms':'Recette fictive'})
        route='/api/admin/quotes/'+quote['id']
        for action in ('TRANSMIS','ACCEPTE'):
            response=self.context.request.post(route+'/transmission',data={'version':1,'action':action,'evidence':'Preuve fictive V84'},headers={'Authorization':'Bearer '+server.ADMIN_TOKEN})
            self.assertEqual(response.status,200,response.text())
        self.seed(route+'/contract',{'version':2,'reference':'V84-CONTRAT','signed_date':today.isoformat(),'evidence':'Signature fictive'})
        mission=self.seed('/api/admin/missions',{'quote_id':quote['id'],'consultant_id':profile['id'],'contract_ref':'V84-CONTRAT','start_date':today.isoformat(),'end_date':old_end})
        def logout():
            self.page.goto('/connexion.html')
            expect(self.page.locator('#workspace')).to_be_visible()
            self.page.locator('#logout').click()
            expect(self.page.locator('#login')).to_be_visible()
        def open_contract():
            mission_row=self.page.locator('#rows tr').filter(has_text='Mission V84')
            mission_row.locator('.row-actions summary').click()
            mission_row.get_by_role('button',name='Contrat / renouvellement').click()
            expect(self.page.get_by_role('heading',name='Contrat et renouvellements')).to_be_visible()

        self.activate('projet.v84','PROJET')
        self.page.locator('#modules a[href="missions.html"]').click()
        expect(self.page.locator('#workspace')).to_be_visible()
        open_contract()
        form=self.page.locator('form').filter(has=self.page.get_by_role('button',name='Soumettre le renouvellement'))
        for key,value in {'new_end':new_end,'reference':'V84-AVENANT','reason':'Prolongation fictive'}.items():
            form.locator('[name='+key+']').fill(value)
        form.get_by_role('button',name='Soumettre le renouvellement').click()
        expect(self.page.locator('#notice')).to_contain_text('Renouvellement soumis')
        expect(form).to_be_hidden()
        expect(self.page.get_by_text('V84-AVENANT',exact=False)).to_contain_text('SOUMIS')
        expect(self.page.get_by_role('button',name='VALIDE',exact=True)).to_have_count(0)
        response=self.context.request.get('/api/admin/missions/'+mission['id']+'/renewals',headers={'Authorization':'Bearer session'})
        self.assertEqual(response.status,200)
        renewal=response.json()['items'][0]
        denial=self.context.request.patch('/api/admin/missions/'+mission['id']+'/renewals/'+renewal['id'],data={'status':'VALIDE'},headers={'Authorization':'Bearer session'})
        self.assertEqual(denial.status,403)
        logout()

        self.activate('admin.v84','ADMIN')
        expect(self.page.locator('#modules a')).to_have_count(0)
        self.page.locator('#mfa-setup [name=password]').fill(self.password)
        self.page.locator('#mfa-setup button').click()
        expect(self.page.locator('#mfa-pending')).to_be_visible()
        secret=self.page.locator('#secret').input_value()
        self.page.locator('#mfa-confirm [name=code]').fill(server.authentication.totp(secret,int(time.time())//30))
        self.page.locator('#mfa-confirm button').click()
        expect(self.page.locator('#recovery')).to_be_visible()
        code=self.page.locator('#recovery-codes').inner_text().splitlines()[0]
        self.page.locator('#dismiss-recovery').click()
        self.login('admin.v84',code)
        self.page.locator('#modules a[href="alerts.html"]').click()
        expect(self.page.locator('#workspace')).to_be_visible()
        self.page.locator('#kind').select_option('RELANCE')
        self.page.locator('#filter button').click()
        expect(self.page.locator('#rows tr').filter(has_text='Relance commerciale V84')).to_be_visible()
        # CONTRAT and RENOUVELLEMENT alerts share the V84-CONTRAT label: wait for each filter to apply.
        contract_rows=self.page.locator('#rows tr').filter(has_text='V84-CONTRAT')
        expect(contract_rows).to_have_count(0)
        self.page.locator('#kind').select_option('RENOUVELLEMENT')
        self.page.locator('#filter button').click()
        expect(contract_rows).to_have_count(1)
        pending=contract_rows
        expect(pending).to_contain_text('RENOUVELLEMENT')
        expect(pending).to_contain_text('Décision en attente')
        # Run the internal scheduler on this isolated database, twice.
        with server.connect() as db:
            self.assertGreater(notifications.run(db,today),0)
            self.assertEqual(notifications.run(db,today),0)
        pending.get_by_role('link',name='Consulter').click()
        expect(self.page.locator('#workspace')).to_be_visible()
        open_contract()
        history=self.page.get_by_text('V84-AVENANT',exact=False)
        history.get_by_role('button',name='VALIDE',exact=True).click()
        expect(history).to_contain_text('VALIDE')
        expect(self.page.locator('#notice')).to_contain_text('Renouvellement traité')
        expect(self.page.locator('#rows')).to_contain_text(new_end)
        self.page.locator('.app-sidebar a[href="alerts.html"]').click()
        expect(self.page.locator('#workspace')).to_be_visible()
        self.page.locator('#kind').select_option('RENOUVELLEMENT')
        self.page.locator('#filter button').click()
        expect(self.page.locator('#rows')).to_contain_text('Aucune alerte')
        self.page.locator('#kind').select_option('CONTRAT')
        self.page.locator('#filter button').click()
        expect(self.page.locator('#rows')).to_contain_text('Aucune alerte')
        with server.connect() as db:
            notifications.run(db,today)
        self.page.locator('.app-sidebar a[href="notifications.html"]').click()
        expect(self.page.locator('#workspace')).to_be_visible()
        self.page.locator('#state').select_option('all')
        self.page.locator('#filter button').click()
        resolved=self.page.locator('#rows tr').filter(has_text='RENOUVELLEMENT').filter(has_text='V84-CONTRAT')
        expect(resolved).to_contain_text('Résolue')
        resolved.get_by_role('button',name='Marquer comme lue').click()
        expect(resolved).to_contain_text('Résolue / Lue')
        expect(resolved.get_by_role('button',name='Marquer comme lue')).to_have_count(0)
        logout()
        self.assertEqual(self.errors, [])

    def test_consultant_live_search_and_server_pagination(self):
        for i in range(12):
            self.seed('/api/admin/consultants', {
                'name':f'V109 Profil {i:02d}','email':f'v109-{i}@example.invalid',
                'role':'Data Engineer','skills':'Python','location':'Conakry',
                'experience':'5','availability':'','notes':'','status':'DISPONIBLE'})
        self.page.goto('/consultants.html')
        self.page.locator('#token').fill(server.ADMIN_TOKEN)
        self.page.locator('#login-form button').click()
        expect(self.page.locator('#workspace')).to_be_visible()
        rows = self.page.locator('#rows tr')
        expect(rows).to_have_count(10)
        self.page.locator('#next').click()
        expect(rows).to_have_count(2)
        self.page.locator('#search').fill('11')
        expect(rows).to_have_count(1)
        expect(rows).to_contain_text('V109 Profil 11')
        expect(self.page.locator('#prev')).to_be_disabled()
        self.page.locator('#search').clear()
        self.page.locator('#page-size').select_option('25')
        expect(rows).to_have_count(12)
        self.assert_responsive('consultants')
        self.assertEqual(self.errors, [])

    def test_consultant_account_picker_and_pagination(self):
        profile = self.seed('/api/admin/consultants', {
            'name':'REC V89 Consultant','email':'v89@example.invalid','role':'Data Engineer',
            'skills':'Python','location':'Conakry','experience':'5','availability':'',
            'notes':'','status':'DISPONIBLE'})
        for i in range(26):
            self.seed('/api/admin/accounts', {'username':f'v89-user-{i:02d}','role':'RH','consultant_id':''})
        self.page.goto('/accounts.html')
        self.page.locator('#token').fill(server.ADMIN_TOKEN)
        self.page.locator('#login-form button').click()
        expect(self.page.locator('#workspace')).to_be_visible()
        pager = self.page.locator('[aria-label="Pagination rows"]')
        expect(pager).to_be_visible()
        expect(self.page.locator('#rows tr:visible')).to_have_count(10)
        pager.get_by_role('button',name='Suivant').click()
        expect(self.page.locator('#rows tr:visible')).to_have_count(10)
        pager.get_by_role('button',name='Suivant').click()
        expect(self.page.locator('#rows tr:visible')).to_have_count(6)
        search = pager.get_by_role('searchbox',name='Rechercher dans rows')
        search.fill('V89-USER-05')
        expect(self.page.locator('#rows tr:visible')).to_have_count(1)
        expect(self.page.locator('#rows tr:visible')).to_contain_text('v89-user-05')
        expect(pager.get_by_role('button',name='Précédent')).to_be_disabled()
        search.fill('05')
        expect(self.page.locator('#rows tr:visible')).to_have_count(1)
        search.fill('r')
        expect(self.page.locator('#rows tr:visible')).to_have_count(10)
        search.fill('Supprimer')
        expect(self.page.locator('#rows tr:visible')).to_have_count(0)
        search.fill('aucun-compte-v91')
        expect(self.page.locator('#rows tr:visible')).to_have_count(0)
        expect(pager.get_by_role('status')).to_contain_text('Aucun résultat')
        search.clear()
        expect(self.page.locator('#rows tr:visible')).to_have_count(10)
        size = pager.get_by_role('combobox',name='Éléments par page')
        size.select_option('10')
        expect(self.page.locator('#rows tr:visible')).to_have_count(10)
        size.select_option('50')
        expect(self.page.locator('#rows tr:visible')).to_have_count(26)
        size.select_option('25')
        self.page.locator('#create [name=username]').fill('rec-v89-consultant')
        self.page.locator('#create [name=role]').select_option('CONSULTANT')
        expect(self.page.locator('#consultant-id option')).to_have_count(2)
        self.page.locator('#consultant-id').select_option(profile['id'])
        self.page.locator('#create button[type=submit]').click()
        expect(self.page.locator('#notice')).to_have_text('Compte créé.')
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT consultant_id FROM accounts WHERE username=?',('rec-v89-consultant',)).fetchone()[0],profile['id'])
        for width in (360, 768, 1280):
            self.page.set_viewport_size({'width':width,'height':844})
            self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'))
        self.assertEqual(self.errors, [])

    def test_account_lifecycle_archive_and_delete(self):
        self.seed('/api/admin/accounts', {'username':'unused.v103','role':'RH','consultant_id':''})
        used = self.seed('/api/admin/accounts', {'username':'used.v103','role':'RH','consultant_id':''})
        response=self.context.request.post('/api/auth/activate',data={'username':'used.v103','key':used['key'],'password':self.password})
        self.assertEqual(response.status,200)
        self.page.goto('/accounts.html')
        self.page.locator('#token').fill(server.ADMIN_TOKEN)
        self.page.locator('#login-form button').click()
        expect(self.page.locator('#workspace')).to_be_visible()
        fresh=self.page.locator('#rows tr').filter(has_text='unused.v103')
        historical=self.page.locator('#rows tr').filter(has_text='used.v103').filter(has_not_text='unused.v103')
        expect(historical.locator('option[value=DELETE]')).to_be_disabled()
        expect(fresh.get_by_role('button')).to_be_disabled()
        fresh.get_by_role('combobox').select_option('DELETE')
        expect(fresh).to_have_count(1)
        self.page.once('dialog',lambda dialog:dialog.dismiss())
        fresh.get_by_role('button').click()
        expect(fresh).to_have_count(1)
        self.page.once('dialog',lambda dialog:dialog.accept())
        fresh.get_by_role('button').click()
        expect(self.page.locator('#notice')).to_have_text('Compte supprimé.')
        expect(fresh).to_have_count(0)
        self.page.once('dialog',lambda dialog:dialog.accept())
        historical.get_by_role('combobox').select_option('ARCHIVE')
        historical.get_by_role('button').click()
        expect(self.page.locator('#notice')).to_have_text('Compte archivé. Historique conservé.')
        expect(historical).to_contain_text('Archivé')
        expect(historical.get_by_role('button')).to_have_count(0)
        self.assert_responsive('accounts.html')
        self.assertEqual(self.errors,[])


if __name__ == '__main__':
    unittest.main()
