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

    def assert_responsive(self, page_name):
        for width in (360, 768, 1280):
            with self.subTest(page=page_name, width=width):
                self.page.set_viewport_size({'width':width,'height':900})
                self.page.evaluate('document.fonts.ready')
                self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'),
                                f'{page_name}: horizontal overflow at {width}px')
        self.page.set_viewport_size({'width':1280,'height':900})

    def test_public_pages_responsive(self):
        for path in ('/', '/en.html', '/expertise.html?id=logistique-transport', '/expertise-en.html?id=logistique-transport', '/confidentialite.html', '/privacy-en.html', '/connexion.html'):
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
        self.page.locator('#need').select_option(label='Mission en régie')
        self.page.locator('#request [name=consent]').check()
        self.page.locator('#request [type=submit]').click()
        expect(self.page.locator('#request-status')).to_contain_text('Demande enregistrée localement')
        self.page.goto('/admin.html')
        self.page.locator('#token').fill(server.ADMIN_TOKEN)
        self.page.locator('#login-form button').click()
        expect(self.page.locator('#dashboard')).to_be_visible()
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
        lead.get_by_label('Nouveau statut pour Client V81 fictif').select_option('QUALIFIEE')
        lead.get_by_role('button',name='Enregistrer',exact=True).click()
        expect(self.page.locator('#notice')).to_contain_text('Statut enregistré')
        lead.get_by_role('button',name='Créer une opportunité CRM').click()
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
        quote.get_by_role('button',name='Aperçu PDF').click()
        expect(self.page.locator('#proposal-document')).to_contain_text('Audit navigateur V81')
        self.page.locator('#close-proposal').click()
        quote.get_by_label('Preuve de transmission ou décision').fill('Transmission fictive V81')
        quote.get_by_role('button',name='Enregistrer le suivi').click()
        expect(self.page.locator('#notice')).to_contain_text('Suivi enregistré')
        expect(quote).to_contain_text('Transmission enregistrée')
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
        self.page.locator('#rows tr').filter(has_text='Audit navigateur V81').get_by_role('button',name='CRA',exact=True).click()
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
                first.get_by_role('button',name='Nouvelle version').click()
                expect(editor.locator('[name=entity_id]')).to_have_value(cid)
                attach(raw2)
                self.page.locator('#save').click()
                current=self.page.locator('#rows tr').filter(has_text='v2 (actuelle)')
                expect(current).to_contain_text('CV V85 fictif')
                expect(self.page.locator('#rows tr').filter(has_text='v1 (historique)')).to_have_count(1)
                expect(self.page.locator('#rows tr')).to_have_count(2)
                with self.page.expect_download() as download:
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
        expect(self.page.locator('#modules a')).to_have_count(15)
        for module in ('admin','crm','appointments','quotes','tenders','consultants','recruitment','missions','billing','direction','accounts','audit','documents','alerts','notifications'):
            with self.subTest(module=module):
                self.page.goto('/'+module+'.html')
                if module=='audit': expect(self.page.locator('#notice')).to_contain_text('100 derniers événements')
                else: expect(self.page.locator('#dashboard' if module=='admin' else '#workspace')).to_be_visible()
                self.assert_responsive(module)
                if module=='accounts':
                    own=self.page.locator('#rows tr').filter(has_text='admin.e2e')
                    expect(own).to_contain_text('Activé')
                    expect(own.get_by_role('button',name='Désactiver')).to_be_disabled()
                    expect(own.get_by_role('button',name='Renouveler / réactiver')).to_be_disabled()
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
            'crm': ('crm/catalogue','crm/organizations','crm/appointments'),
            'billing': ('billing/expenses','billing/milestones','billing/contracts','billing/schedule','billing/receivables','billing/forecast','billing/planned-expenses'),
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
                    expected.add('appointments.html')
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
                            expect(self.page.locator('#notice')).to_contain_text('100 derniers événements')
                        else:
                            expect(self.page.locator('#dashboard' if target=='admin.html' else '#workspace')).to_be_visible()
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

    def test_anonymous_private_routes_and_crm_workspace(self):
        # A public static shell must not grant access to private records.
        paths = (
            'requests','crm','crm/catalogue','crm/organizations','crm/appointments',
            'quotes','tenders','consultants','recruitment','missions','missions/eligible',
            'billing','billing/expenses','billing/contracts','billing/milestones',
            'billing/schedule','billing/receivables','billing/forecast','billing/planned-expenses',
            'direction','direction/reporting','accounts','audit','documents',
            'alerts','notifications','my-activity',
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
            self.page.locator('#rows tr').filter(has_text='Mission V84').get_by_role('button',name='Contrat / renouvellement').click()
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
        self.page.locator('#kind').select_option('RENOUVELLEMENT')
        self.page.locator('#filter button').click()
        pending=self.page.locator('#rows tr').filter(has_text='V84-CONTRAT')
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
        expect(self.page.locator('#rows tr:visible')).to_have_count(25)
        pager.get_by_role('button',name='Suivant').click()
        expect(self.page.locator('#rows tr:visible')).to_have_count(1)
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


if __name__ == '__main__':
    unittest.main()
