"""Browser acceptance tests: isolated loopback server and fictitious records."""
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from playwright.sync_api import sync_playwright, expect
import server


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

    def test_public_intake_and_catalogue(self):
        self.page.goto('/')
        expect(self.page.locator('h1')).to_be_visible()
        self.assertNotIn('MineFleet360', self.page.content())
        self.assertEqual(self.context.request.get('/catalogue.js').status, 404)
        for name,value in {'nom':'Client fictif','org':'Entreprise fictive','email':'qa@example.invalid','message':'Demande de recette navigateur'}.items():
            self.page.locator(f'#request [name={name}]').fill(value)
        self.page.locator('#need').select_option(label='Mission en régie')
        self.page.locator('#request [name=consent]').check()
        self.page.locator('#request [type=submit]').click()
        expect(self.page.locator('#request-status')).to_contain_text('Demande enregistrée localement')
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

    def test_cybersecurity_expertise_and_prefill(self):
        self.page.goto('/')
        expect(self.page.locator('#expertise-groups article')).to_have_count(25)
        expect(self.page.locator('#expertise-groups h3')).to_have_count(5)
        self.page.locator('article').filter(has=self.page.get_by_role('heading',name='Audit de cybersécurité & GRC',exact=True)).get_by_role('link').click()
        expect(self.page.locator('#deliverables')).to_contain_text('Registre des risques')
        self.page.locator('#expertise-contact').click()
        expect(self.page.locator('#need')).to_have_value('Cybersécurité & résilience')
        expect(self.page.locator('#request [name=message]')).to_have_value('Domaine : Audit de cybersécurité & GRC — ')
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
        expect(self.page.locator('#modules a')).to_have_count(12)
        for module in ('admin','crm','quotes','tenders','consultants','missions','billing','direction','accounts','audit','documents','alerts'):
            with self.subTest(module=module):
                self.page.goto('/'+module+'.html')
                if module=='audit': expect(self.page.locator('#notice')).to_contain_text('100 derniers événements')
                else: expect(self.page.locator('#dashboard' if module=='admin' else '#workspace')).to_be_visible()
                if module=='crm':
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
                    expect(self.page.locator('#control-tables table')).to_have_count(5)
                    self.page.locator('#control-currency').select_option('GNF')
                    expect(self.page.locator('#control-tables')).to_contain_text('Aucun résultat.')
                    expect(self.page.locator('#control-tables')).to_contain_text('Flux de trésorerie enregistrés')
                    self.page.locator('#report-start').fill('2020-01-01')
                    self.page.locator('#report-end').fill('2020-01-31')
                    self.page.locator('#report-form').get_by_role('button',name='Afficher').click()
                    expect(self.page.locator('#report-rows')).to_contain_text('-1000')
                    expect(self.page.locator('#report-export')).to_be_enabled()
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
        self.page.goto('/accounts.html')
        expect(self.page.locator('#notice')).to_contain_text('Permission insuffisante')
        expect(self.page.locator('#workspace')).to_be_hidden()
        self.assertEqual(self.errors, [])


if __name__ == '__main__':
    unittest.main()
