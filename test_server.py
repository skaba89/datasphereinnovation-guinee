import json
from decimal import Decimal
import tempfile
import threading
import unittest
import time
import os
from cryptography.fernet import Fernet
from unittest.mock import patch
from http.client import HTTPConnection
from pathlib import Path
import server


class IntakeTests(unittest.TestCase):
    def setUp(self):
        # Existing lifecycle tests explicitly preserve the legacy local policy; a separate test exercises the strict default.
        self.mfa_env=patch.dict(os.environ,{'DSIG_MFA_KEY':Fernet.generate_key().decode(),'DSIG_MFA_REQUIRED_ROLES':''});self.mfa_env.start();self.addCleanup(self.mfa_env.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.original = server.DB
        self.original_token = server.ADMIN_TOKEN
        server.ADMIN_TOKEN = "test-token-only-" + "x"*32
        server.DB = Path(self.tmp.name) / "requests.sqlite3"
        server.RATE.clear()
        self.http = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.http.server_address[1]
        self.payload = {"nom": "Test", "org": "Organisation fictive", "email": "qa@example.invalid",
                        "besoin": "Demande de démonstration", "solution": "MineFleet360",
                        "message": "Test de recette", "consent": True, "website": ""}

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        server.DB = self.original
        server.ADMIN_TOKEN = self.original_token
        self.tmp.cleanup()

    def request(self, method, path, payload=None, headers=None):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        body = None if payload is None else json.dumps(payload)
        conn.request(method, path, body, headers or {"Content-Type": "application/json"})
        res = conn.getresponse()
        result = res.status, res.read(), dict(res.getheaders())
        conn.close()
        return result

    def test_list_page_size_validation(self):
        headers={'Authorization':'Bearer '+server.ADMIN_TOKEN}
        for resource in ('requests','consultants','crm','tenders','quotes','documents','missions','recruitment'):
            for size in ('0','11','1000','invalid','10','25','50'):
                with self.subTest(resource=resource,size=size):
                    code,body,_=self.request('GET',f'/api/admin/{resource}?page_size={size}',headers=headers)
                    self.assertEqual(code,200 if size in ('10','25','50') else 400,body)

    def test_end_to_end_prospect_to_paid_contract(self):
        admin={'Authorization':'Bearer '+server.ADMIN_TOKEN,'Content-Type':'application/json'}
        def call(method,path,payload=None,headers=None,status=200):
            code,body,_=self.request(method,path,payload,headers)
            self.assertEqual(code,status,(method,path,body))
            return json.loads(body)
        def account(role,consultant_id=''):
            data=call('POST','/api/admin/accounts',{'username':'journey.'+role.lower(),'role':role,'consultant_id':consultant_id},admin,201)
            return {'Authorization':'Bearer '+data['key'],'Content-Type':'application/json'}
        commercial=account('COMMERCIAL')
        rh=account('RH')
        project=account('PROJET')
        finance=account('COMPTABLE')
        direction=account('DIRECTION')
        request=call('POST','/api/requests',self.payload|{'besoin':'Mission en régie','solution':''},status=201)
        route='/api/admin/requests/'+request['id']
        call('PATCH',route,{'status':'QUALIFIEE','previous':'NOUVELLE'},commercial)
        conversion=call('POST',route+'/convert',headers=commercial,status=201)
        self.assertEqual(call('POST',route+'/convert',headers=commercial),conversion)
        oid=conversion['opportunity_id']
        profile={'name':'Consultant parcours fictif','email':'journey@example.invalid','role':'Data Engineer','skills':'Python','location':'Guinée','experience':'5','availability':'Immédiate','notes':'','status':'DISPONIBLE'}
        cid=call('POST','/api/admin/consultants',profile,rh,201)['id']
        consultant=account('CONSULTANT',cid)
        quote={'opportunity_id':oid,'title':'Audit fictif','scope':'Diagnostic','mode':'REGIE','currency':'EUR','days':'10','rate':'600','daily_cost':'400','expenses':'0','fixed_price':'0','status':'PROPOSE','valid_until':'2099-01-01','terms':'Recette'}
        qid=call('POST','/api/admin/quotes',quote,commercial,201)['id']
        qroute='/api/admin/quotes/'+qid
        decision={'version':1,'action':'TRANSMIS','evidence':'Transmission fictive'}
        call('POST',qroute+'/transmission',decision,commercial)
        call('POST',qroute+'/transmission',decision|{'action':'ACCEPTE'},commercial)
        mission={'quote_id':qid,'consultant_id':cid,'contract_ref':'JOURNEY-001','start_date':'2020-01-01','end_date':'2020-01-31'}
        call('POST','/api/admin/missions',mission,project,409)
        call('POST',qroute+'/contract',{'version':2,'reference':'JOURNEY-001','signed_date':'2020-01-01','evidence':'Signature fictive'},commercial,201)
        mid=call('POST','/api/admin/missions',mission,project,201)['id']
        activity={'mission_id':mid,'work_date':'2020-01-08','worked':'1','billable':'1','expenses':'25','description':'CRA fictif'}
        aid=call('POST','/api/admin/my-activity',activity,consultant,201)['id']
        call('PATCH','/api/admin/missions/activity/'+aid,{'status':'VALIDE'},consultant,403)
        invoice={'mission_id':mid,'reference':'JOURNEY-INV','amount':'600','due_date':'2020-02-01'}
        call('POST','/api/admin/billing/invoices',invoice,finance,409)
        call('PATCH','/api/admin/missions/activity/'+aid,{'status':'VALIDE'},project)
        iid=call('POST','/api/admin/billing/invoices',invoice,finance,201)['id']
        payment={'invoice_id':iid,'reference':'JOURNEY-PAY1','amount':'200','paid_date':'2020-02-01'}
        call('POST','/api/admin/billing/payments',payment,finance,201)
        call('POST','/api/admin/billing/payments',payment|{'reference':'OVERPAY','amount':'401'},finance,409)
        call('POST','/api/admin/billing/payments',payment|{'reference':'JOURNEY-PAY2','amount':'400'},finance,201)
        call('POST','/api/admin/billing/expenses',{'reference':'JOURNEY-DEP','currency':'EUR','amount':'425','paid_date':'2020-02-01','category':'CONSULTANT','description':'Décaissement fictif','mission_id':mid},finance,201)
        call('PATCH','/api/admin/missions/'+mid,{'status':'TERMINE'},project)
        self.assertEqual(Decimal(call('GET','/api/admin/billing',headers=finance)['totals']['EUR']['balance']),Decimal('0'))
        control=call('GET','/api/admin/direction',headers=direction)['controlling']
        row=next(x for x in control['missions'] if x['mission_id']==mid)
        self.assertEqual(row['contract_ref'],'JOURNEY-001')
        self.assertTrue(row['organization_id'])
        for field,amount in {'validated_revenue':'600','validated_cost':'425','validated_margin':'175','received':'600','receivable':'0','allocated_cash_flow':'175'}.items():
            self.assertEqual(Decimal(row[field]),Decimal(amount),field)
        client=next(x for x in control['clients'] if x['organization_id']==row['organization_id'])
        self.assertEqual(Decimal(client['validated_margin']),Decimal('175'))
        lead=call('GET','/api/admin/requests',headers=commercial)['items'][0]['conversion']
        self.assertEqual((lead['opportunity_id'],lead['quotes'],lead['missions']),(oid,1,1))
        # Imported fictional ledger rows exercise searches beyond the first page.
        with server.connect() as db:
            db.executemany('INSERT INTO invoices(id,mission_id,reference,amount,due_date,created_at) VALUES(?,?,?,?,?,?)',
                [(f'fixture-{i:02}',mid,f'FIXTURE-{i:02}','1','2020-02-01','2099-01-01') for i in range(26)])
        route='/api/admin/billing'
        first=call('GET',route,headers=finance)
        self.assertEqual((len(first['items']),first['total']),(25,27))
        self.assertNotIn(iid,[x['id'] for x in first['items']])
        found=call('GET',route+'?q=journey-inv&state=PAID',headers=finance)
        self.assertEqual([x['id'] for x in found['items']],[iid])
        self.assertEqual(found['totals'],first['totals'])
        opened=call('GET',route+'?state=OVERDUE&page=2',headers=finance)
        self.assertEqual((len(opened['items']),opened['total']),(1,26))
        self.assertEqual(call('GET',route+'?state=OPEN&q=journey-inv',headers=finance)['total'],0)
        call('GET',route+'?state=INVALID',headers=finance,status=400)

    def test_qualified_request_conversion(self):
        auth={'Authorization':'Bearer '+server.ADMIN_TOKEN,'Content-Type':'application/json'}
        code,body,_=self.request('POST','/api/requests',self.payload)
        self.assertEqual(code,201)
        rid=json.loads(body)['id']
        path='/api/admin/requests/'+rid+'/convert'
        self.assertEqual(self.request('POST',path)[0],401)
        self.assertEqual(self.request('POST',path,headers=auth)[0],409)
        self.assertEqual(self.request('PATCH','/api/admin/requests/'+rid,{'status':'QUALIFIEE','previous':'NOUVELLE'},auth)[0],200)
        with server.connect() as db:
            db.execute("INSERT INTO organizations(id,name,name_key,kind,country,notes) VALUES ('existing','Organisation fictive','organisation fictive','CLIENT','','')")
        code,body,_=self.request('POST',path,headers=auth)
        self.assertEqual(code,201)
        result=json.loads(body)
        self.assertEqual(result['status'],'QUALIFIE')
        code,body,_=self.request('POST',path,headers=auth)
        self.assertEqual(code,200)
        self.assertEqual(json.loads(body),result)
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM opportunities').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM organizations').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT organization_id FROM organization_links').fetchone()[0],'existing')
            self.assertEqual(db.execute('SELECT status FROM requests WHERE id=?',(rid,)).fetchone()[0],'QUALIFIEE')
        data=json.loads(self.request('GET','/api/admin/requests',headers=auth)[1])
        self.assertEqual(data['items'][0]['conversion'],result)

    def test_request_workflow_assignment_and_revision(self):
        headers={'Authorization':'Bearer '+server.ADMIN_TOKEN,'Content-Type':'application/json'}
        code,body,_=self.request('POST','/api/requests',self.payload)
        self.assertEqual(code,201)
        rid=json.loads(body)['id']
        with server.connect() as db:
            db.execute("INSERT INTO accounts(id,username,role,key_hash) VALUES ('seller','commercial.test','COMMERCIAL','fictional-hash')")
        path='/api/admin/requests/'+rid+'/workflow'
        data={'owner_id':'seller','priority':'URGENTE','due_date':'2020-01-01','revision':0,'note':'Appel de qualification fictif'}
        self.assertEqual(self.request('PATCH',path,data)[0],401)
        self.assertEqual(self.request('PATCH',path,data|{'owner_id':'unknown'},headers)[0],400)
        self.assertEqual(self.request('PATCH',path,data|{'due_date':'2027-02-30'},headers)[0],400)
        code,body,_=self.request('PATCH',path,data,headers)
        self.assertEqual(code,200)
        self.assertEqual(json.loads(body)['revision'],1)
        self.assertEqual(self.request('PATCH',path,data,headers)[0],409)
        code,body,_=self.request('GET','/api/admin/requests',headers=headers)
        self.assertEqual(code,200)
        row=json.loads(body)['items'][0]
        self.assertEqual(row['workflow']['owner'],'commercial.test')
        self.assertEqual(row['workflow']['history'][0]['note'],data['note'])
        self.assertEqual(row['status'],'NOUVELLE')
        code,body,_=self.request('GET','/api/admin/requests?owner=seller&priority=URGENTE&overdue=1',headers=headers)
        self.assertEqual(code,200)
        data=json.loads(body)
        self.assertEqual(data['total'],1)
        self.assertEqual(data['workload'][0]['overdue'],1)
        self.assertEqual(data['workload'][0]['urgent'],1)
        code,body,_=self.request('GET','/api/admin/requests?owner=unassigned',headers=headers)
        self.assertEqual(code,200)
        self.assertEqual(json.loads(body)['total'],0)
        self.assertEqual(self.request('GET','/api/admin/requests?priority=invalid',headers=headers)[0],400)
        self.assertEqual(self.request('GET','/api/admin/requests?owner=mine',headers=headers)[0],400)
        code,body,_=self.request('POST','/api/admin/accounts',{'username':'rh.workflow','role':'RH','consultant_id':''},headers)
        self.assertEqual(code,201)
        rh={'Authorization':'Bearer '+json.loads(body)['key']}
        self.assertEqual(self.request('GET','/api/admin/requests?owner=seller',headers=rh)[0],403)
        code,body,_=self.request('GET','/api/admin/requests',headers=rh)
        self.assertEqual(code,200)
        self.assertEqual(json.loads(body)['workload'],[])

    def test_commercial_metrics_cohort(self):
        with server.connect() as db:
            for rid, age, status, category in (
                ('won', '-3 days', 'GAGNEE', 'Mission en régie'),
                ('late', '-4 days', 'NOUVELLE', 'Mission en régie'),
                ('old', '-100 days', 'NOUVELLE', 'Partenariat'),
            ):
                db.execute("""INSERT INTO requests(id,created_at,nom,org,email,besoin,solution,message,status)
                    VALUES (?,datetime('now',?),'Test','Fictif','qa@example.invalid',?,'','Test',?)""",
                    (rid,age,category,status))
            db.execute("""INSERT INTO request_events(request_id,created_at,previous_status,new_status)
                VALUES ('won',datetime('now','-2 days'),'NOUVELLE','GAGNEE')""")
        headers={'Authorization':'Bearer '+server.ADMIN_TOKEN}
        self.assertEqual(self.request('GET','/api/admin/requests?period=invalid',headers=headers)[0],400)
        self.assertEqual(self.request('GET','/api/admin/requests?period=30')[0],401)
        code, body, _ = self.request('GET','/api/admin/requests?period=30',headers=headers)
        self.assertEqual(code,200)
        data=json.loads(body)
        self.assertEqual(data['total'],2)
        row,=data['commercial_metrics']
        self.assertEqual((row['total'],row['won'],row['untreated'],row['overdue'],row['treated']),(2,1,1,1,1))
        self.assertAlmostEqual(row['treatment_hours'],24,places=3)
        code, body, _ = self.request('GET','/api/admin/requests?period=30&status=NOUVELLE',headers=headers)
        self.assertEqual(code,200)
        self.assertEqual(json.loads(body)['commercial_metrics'][0]['won'],0)

    def test_accessibility_assets_and_local_csp(self):
        for name in ('index','en','expertise','confidentialite','connexion','admin','accounts','audit','billing','consultants','crm','direction','missions','my-activity','quotes','tenders','documents','alerts','notifications'):
            with self.subTest(page=name):
                s,b,h=self.request('GET','/'+name+'.html');self.assertEqual(s,200)
                self.assertIn(b'class="skip-link"',b);self.assertIn(b'accessibility.css',b);self.assertIn(b'tabindex="-1"',b)
                self.assertNotIn('fonts.googleapis.com',h['Content-Security-Policy'])
        self.assertEqual(self.request('GET','/accessibility.css')[0],200)
        self.assertNotIn(b'fonts.googleapis.com',self.request('GET','/studio.css')[1])

    def test_local_font_assets_are_strictly_allowlisted(self):
        for weight in ('Regular','Semibold','Bold','ExtraBold'):
            path='/fonts/open-sans-'+weight+'.woff'
            s,b,h=self.request('GET',path)
            self.assertEqual(s,200)
            self.assertEqual({k.lower():v for k,v in h.items()}['content-type'],'font/woff')
            self.assertEqual(b[:4],b'wOFF')
            self.assertEqual(self.request('HEAD',path)[0],200)
        self.assertEqual(self.request('GET','/fonts/LICENSE.txt')[0],200)
        for path in ('/fonts/','/fonts/unknown.woff','/fonts/../server.py','/fonts/%2e%2e/index.html','/fonts//open-sans-Regular.woff','/open-sans-Regular.woff'):
            self.assertEqual(self.request('GET',path)[0],404,path)

    def test_health_and_security(self):
        status, _, headers = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(headers["X-Robots-Tag"], "noindex, nofollow")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])

    def test_https_origin_and_secure_session(self):
        origin='https://rec.dsig-consulting.com'
        admin={'Authorization':'Bearer '+server.ADMIN_TOKEN,'Content-Type':'application/json','Host':'rec.dsig-consulting.com','Origin':origin}
        server.authentication.ATTEMPTS.clear()
        with server.connect():pass
        with patch.dict(os.environ,{'DSIG_HTTPS_ORIGIN':origin}):
            self.assertEqual(self.request('GET','/api/ready')[0],200)
            self.assertEqual(self.request('GET','/connexion.html')[0],403)
            self.assertEqual(self.request('GET','/connexion.html',headers=admin)[0],200)
            self.assertEqual(self.request('GET','/api/admin/requests',headers=admin|{'Origin':'http://rec.dsig-consulting.com','X-Forwarded-Proto':'https'})[0],403)
            self.assertEqual(self.request('GET','/api/admin/requests',headers=admin|{'Origin':'https://evil.invalid'})[0],403)
            s,b,_=self.request('POST','/api/admin/accounts',{'username':'https.test','role':'COMPTABLE','consultant_id':''},admin)
            self.assertEqual(s,201)
            credentials={'username':'https.test','password':'fictitious-password-123'}
            browser={'Host':'rec.dsig-consulting.com','Origin':origin,'Content-Type':'application/json','X-DSIG-Session':'cookie'}
            self.assertEqual(self.request('POST','/api/auth/activate',credentials|{'key':json.loads(b)['key']},browser)[0],200)
            s,b,h=self.request('POST','/api/auth/login',credentials,browser)
            self.assertEqual(s,200);self.assertIn('; Secure',h['Set-Cookie'])
            session=browser|{'Authorization':'Bearer session','Cookie':h['Set-Cookie'].split(';')[0]}
            self.assertEqual(self.request('GET','/api/admin/billing',headers=session)[0],200)
            self.assertEqual(self.request('POST','/api/auth/mfa-setup',{'password':credentials['password']},session)[0],200)
            s,_,h=self.request('POST','/api/auth/logout',{},session)
            self.assertEqual(s,200);self.assertIn('; Secure',h['Set-Cookie'])
        with patch.dict(os.environ,{'DSIG_HTTPS_ORIGIN':'http://rec.dsig-consulting.com'}):
            with self.assertRaises(ValueError):server.configured_origin()

    def test_security_transport(self):
        import socket
        auth={'Authorization':'Bearer '+server.ADMIN_TOKEN,'Origin':'https://example.invalid'}
        self.assertEqual(self.request('GET','/api/admin/requests',headers=auth)[0],403)
        self.assertEqual(self.request('HEAD','/api/admin/requests')[0],404)
        for target in ('/../server.py','/%2e%2e/server.py','/.env','/data/requests.sqlite3'):
            self.assertEqual(self.request('GET',target)[0],404)
        for headers in (b'Content-Length: 0\r\nContent-Length: 1\r\n',b'Transfer-Encoding: chunked\r\n'):
            with socket.create_connection(('127.0.0.1',self.port),timeout=3) as sock:
                sock.sendall(b'POST /api/requests HTTP/1.0\r\nHost: localhost\r\n'+headers+b'\r\n')
                self.assertIn(b'400',sock.recv(1024).split(b'\r\n')[0])
        link=server.ROOT/'dist'/'test-security-link.html'
        try:
            link.symlink_to(server.ROOT/'server.py')
            self.assertEqual(self.request('GET','/test-security-link.html')[0],404)
        finally:
            if link.is_symlink():link.unlink()

    def test_valid_request_persists(self):
        status, data, _ = self.request("POST", "/api/requests", self.payload)
        self.assertEqual(status, 201)
        with server.connect() as db:
            self.assertEqual(db.execute("SELECT id, solution, status FROM requests").fetchone(),
                             (json.loads(data)["id"], "MineFleet360", "NOUVELLE"))

    def test_recruitment_route(self):
        import uuid
        s,b,_=self.request('POST','/api/requests',self.payload|{'besoin':'Candidature spontanée','solution':''})
        self.assertEqual(s,201);rid=json.loads(b)['id']
        path='/api/admin/recruitment';auth={'Authorization':'Bearer '+server.ADMIN_TOKEN,'Content-Type':'application/json'}
        self.assertEqual(self.request('GET',path)[0],401)
        self.assertEqual(json.loads(self.request('GET',path,headers=auth)[1])['items'][0]['id'],rid)
        payload={'request_id':rid,'role':'Data Engineer','skills':'Python'}
        self.assertEqual(self.request('POST',path,payload,auth)[0],201)
        self.assertEqual(self.request('POST',path,payload,auth)[0],200)
        with server.connect() as db:
            db.executemany('INSERT INTO requests(id,nom,org,email,besoin,solution,message) VALUES (?,?,?,?,?,?,?)',[(str(uuid.uuid4()),f'Candidat {i:03d}','Fictif','qa@example.invalid','Candidature spontanée','','Python') for i in range(105)])
        def results(query):
            status,body,_=self.request('GET',path+query,headers=auth)
            self.assertEqual(status,200)
            return json.loads(body)
        first=results('?state=PENDING&page=1');last=results('?state=PENDING&page=5')
        self.assertEqual((first['total'],len(first['items']),len(last['items'])),(105,25,5))
        self.assertFalse({x['id'] for x in first['items']} & {x['id'] for x in last['items']})
        self.assertEqual(results('?state=QUALIFIED')['items'][0]['id'],rid)
        self.assertEqual(results('?q=Candidat%20104')['total'],1)
        ten=results('?state=PENDING&page=1&page_size=10');end=results('?state=PENDING&page=11&page_size=10')
        self.assertEqual((ten['total'],len(ten['items']),len(end['items'])),(105,10,5))
        self.assertFalse({x['id'] for x in ten['items']} & {x['id'] for x in end['items']})
        self.assertEqual(self.request('GET',path+'?page=0',headers=auth)[0],400)
        self.assertEqual(self.request('GET',path+'?state=UNKNOWN',headers=auth)[0],400)

    def test_contact_mail_atomic_enqueue(self):
        with patch.dict(os.environ,{'DSIG_ENV':'REC'}):
            status,data,_=self.request('POST','/api/requests',self.payload|{'language':'en'})
            self.assertEqual(status,201)
            with server.connect() as db:
                self.assertEqual(set(db.execute('SELECT kind,language,state FROM contact_mail WHERE request_id=?',(json.loads(data)['id'],))),{('ack','en','PENDING'),('internal','en','PENDING')})
            self.assertEqual(self.request('POST','/api/requests',self.payload|{'language':'xx'})[0],400)

    def test_invalid_requests(self):
        for changes in ({"consent": False}, {"email": "no-email"}, {"solution": ""},
                        {"website": "spam"}, {"besoin": "inconnu"}, {"message": "x" * 4001}):
            self.assertEqual(self.request("POST", "/api/requests", self.payload | changes)[0], 400)

    def test_origin_and_content_type(self):
        self.assertEqual(self.request("POST", "/api/requests", self.payload,
                         {"Content-Type": "application/json", "Origin": "https://example.invalid"})[0], 403)
        self.assertEqual(self.request("POST", "/api/requests", self.payload,
                         {"Content-Type": "text/plain"})[0], 415)

    def test_rate_limit(self):
        for _ in range(5):
            self.assertEqual(self.request("POST", "/api/requests", self.payload)[0], 201)
        self.assertEqual(self.request("POST", "/api/requests", self.payload)[0], 429)

    def test_no_public_lead_listing_or_database(self):
        self.assertEqual(self.request("GET", "/api/requests")[0], 404)
        self.assertEqual(self.request("GET", "/data/requests.sqlite3")[0], 404)

    def test_public_site_does_not_expose_product_catalogue(self):
        status, data, _ = self.request("GET", "/")
        self.assertEqual(status, 200)
        for term in (b"#solutions", b"catalogue.js", b"solution.html", b"MineFleet360", b"Guin\xc3\xa9e Logistique"):
            self.assertNotIn(term, data)
        for route in ("/catalogue.js", "/solution.html?id=minefleet360", "/solution.js", "/internal-catalogue/catalogue.js"):
            self.assertEqual(self.request("GET", route)[0], 404)
        self.assertEqual(self.request("GET", "/expertise.html?id=data-engineering")[0], 200)

    def test_private_product_catalogue(self):
        path='/api/admin/crm/catalogue'
        self.assertEqual(self.request('GET',path)[0],401)
        auth={'Authorization':'Bearer '+server.ADMIN_TOKEN,'Content-Type':'application/json'}
        self.assertEqual(self.request('GET',path,headers=auth|{'Origin':'https://other.invalid'})[0],403)
        status,body,_=self.request('GET',path,headers=auth)
        self.assertEqual(status,200)
        rows=json.loads(body)['items']
        item=next(x for x in rows if x['id']=='guinee-logistique')
        self.assertEqual(item['status'],'Prototype de démonstration')
        self.assertIn('Données fictives',item['conditions'])
        self.assertEqual(len({x['id'] for x in rows}),5)
        _,body,_=self.request('POST','/api/admin/accounts',{'username':'catalogue.rh','role':'RH','consultant_id':''},auth)
        self.assertEqual(self.request('GET',path,headers={'Authorization':'Bearer '+json.loads(body)['key']})[0],403)

    def test_non_demo_solution_not_stored(self):
        self.assertEqual(self.request("POST", "/api/requests", self.payload | {"besoin": "Mission en régie"})[0], 201)
        with server.connect() as db:
            self.assertEqual(db.execute("SELECT solution FROM requests").fetchone(), ("",))

    def test_admin_requires_token(self):
        self.assertEqual(self.request("GET", "/api/admin/requests")[0], 401)
        self.assertEqual(self.request("GET", "/api/admin/requests", headers={"Authorization":"Bearer wrong"})[0], 401)
        server.ADMIN_TOKEN = ""
        self.assertEqual(self.request("GET", "/api/admin/requests")[0], 503)

    def test_password_sessions(self):
        server.authentication.ATTEMPTS.clear()
        auth={'Authorization':'Bearer '+server.ADMIN_TOKEN,'Content-Type':'application/json'}
        s,body,_=self.request('POST','/api/admin/accounts',{'username':'finance.test','role':'COMPTABLE','consultant_id':''},auth);self.assertEqual(s,201);a=json.loads(body)
        initial={'Authorization':'Bearer '+a['key']}
        credentials={'username':'finance.test','password':'fictitious-test-password-123'}
        self.assertEqual(self.request('POST','/api/auth/activate',credentials|{'key':a['key']})[0],200)
        self.assertEqual(self.request('GET','/api/admin/billing',headers=initial)[0],401)
        self.assertEqual(self.request('POST','/api/auth/login',credentials|{'password':'incorrect-password'})[0],401)
        s,body,_=self.request('POST','/api/auth/login',credentials);self.assertEqual(s,200);token=json.loads(body)['token']
        session={'Authorization':'Bearer '+token,'Content-Type':'application/json'}
        self.assertEqual(self.request('GET','/api/admin/billing',headers=session)[0],200)
        self.assertEqual(self.request('GET','/api/admin/accounts',headers=session)[0],403)
        self.assertEqual(self.request('POST','/api/auth/logout',{},session)[0],200)
        self.assertEqual(self.request('GET','/api/admin/billing',headers=session)[0],401)
        s,body,_=self.request('POST','/api/auth/login',credentials);self.assertEqual(s,200)
        session={'Authorization':'Bearer '+json.loads(body)['token']}
        with server.connect() as db:db.execute('UPDATE sessions SET expires=0')
        self.assertEqual(self.request('GET','/api/admin/billing',headers=session)[0],401)
        self.assertEqual(self.request('GET','/connexion.html')[0],200)

    def test_login_session_committed_before_response(self):
        import sqlite3
        admin={'Authorization':'Bearer '+server.ADMIN_TOKEN,'Content-Type':'application/json'}
        status,body,_=self.request('POST','/api/admin/accounts',{'username':'commit.test','role':'COMPTABLE','consultant_id':''},admin)
        self.assertEqual(status,201)
        credentials={'username':'commit.test','password':'fictitious-password-123'}
        self.assertEqual(self.request('POST','/api/auth/activate',credentials|{'key':json.loads(body)['key']})[0],200)
        observed=[]
        original=server.Handler.json_response
        def check(handler,status,body):
            if handler.path=='/api/auth/login' and status==200:
                with sqlite3.connect(server.DB) as reader:
                    observed.append(reader.execute('SELECT 1 FROM sessions WHERE token_hash=?',(server.accounts.digest(body['token']),)).fetchone())
            return original(handler,status,body)
        with patch.object(server.Handler,'json_response',check):
            self.assertEqual(self.request('POST','/api/auth/login',credentials)[0],200)
        self.assertEqual(observed,[(1,)])

    def test_mfa_and_shared_session(self):
        server.authentication.ATTEMPTS.clear()
        admin={'Authorization':'Bearer '+server.ADMIN_TOKEN,'Content-Type':'application/json'}
        s,b,_=self.request('POST','/api/admin/accounts',{'username':'mfa.test','role':'COMPTABLE','consultant_id':''},admin)
        self.assertEqual(s,201)
        credentials={'username':'mfa.test','password':'fictitious-password-123'}
        self.assertEqual(self.request('POST','/api/auth/activate',credentials|{'key':json.loads(b)['key']})[0],200)
        login={'Content-Type':'application/json','X-DSIG-Session':'cookie','Origin':f'http://127.0.0.1:{self.port}'}
        s,b,h=self.request('POST','/api/auth/login',credentials,login)
        self.assertEqual(s,200);self.assertNotIn('token',json.loads(b));self.assertIn('HttpOnly; SameSite=Strict',h['Set-Cookie'])
        session=login|{'Authorization':'Bearer session','Cookie':h['Set-Cookie'].split(';')[0]}
        self.assertEqual(self.request('GET','/api/auth/me',headers=session)[0],200)
        self.assertEqual(self.request('GET','/api/admin/billing',headers=session)[0],200)
        self.assertEqual(self.request('GET','/api/admin/accounts',headers=session)[0],403)
        self.assertEqual(self.request('POST','/api/auth/mfa-setup',{'password':credentials['password']},session|{'Origin':'https://evil.invalid'})[0],403)
        s,b,_=self.request('POST','/api/auth/mfa-setup',{'password':credentials['password']},session)
        self.assertEqual(s,200);secret=json.loads(b)['secret']
        now=int(time.time());step=now//30
        with patch('authentication.time.time',return_value=now):
            code=server.authentication.totp(secret,step)
            s,b,_=self.request('POST','/api/auth/mfa-confirm',{'code':code},session);self.assertEqual(s,200)
            codes=json.loads(b)['recovery_codes'];self.assertEqual(len(set(codes)),8)
            with server.connect() as db:
                stored=db.execute('SELECT secret FROM mfa').fetchone()[0];self.assertTrue(stored.startswith('fernet:'));self.assertNotIn(secret,stored)
                self.assertNotIn(codes[0],[r[0] for r in db.execute('SELECT code_hash FROM recovery_codes')])
            self.assertEqual(self.request('GET','/api/auth/me',headers=session)[0],401)
            with patch.dict(os.environ,{'DSIG_MFA_KEY':Fernet.generate_key().decode()}):
                self.assertEqual(self.request('POST','/api/auth/login',credentials|{'otp':codes[0]},login)[0],503)
            s,b,h=self.request('POST','/api/auth/login',credentials|{'otp':codes[0]},login);self.assertEqual(s,200)
            self.assertEqual(self.request('POST','/api/auth/login',credentials|{'otp':codes[0]},login)[0],401)
            self.assertEqual(self.request('POST','/api/auth/login',credentials,login)[0],401)
            self.assertEqual(self.request('POST','/api/auth/login',credentials|{'otp':code},login)[0],401)
            s,b,h=self.request('POST','/api/auth/login',credentials|{'otp':server.authentication.totp(secret,step+1)},login)
            self.assertEqual(s,200)
            session['Cookie']=h['Set-Cookie'].split(';')[0]
            self.assertEqual(self.request('GET','/api/auth/me',headers=session)[0],200)
            self.assertEqual(self.request('POST','/api/auth/logout',{},session)[0],200)
            self.assertEqual(self.request('GET','/api/auth/me',headers=session)[0],401)

    def test_legacy_mfa_migration(self):
        server.authentication.ATTEMPTS.clear()
        admin={'Authorization':'Bearer '+server.ADMIN_TOKEN,'Content-Type':'application/json'}
        s,b,_=self.request('POST','/api/admin/accounts',{'username':'legacy.test','role':'COMPTABLE','consultant_id':''},admin)
        self.assertEqual(s,201);account=json.loads(b)
        credentials={'username':'legacy.test','password':'fictitious-password-123'}
        self.assertEqual(self.request('POST','/api/auth/activate',credentials|{'key':account['key']})[0],200)
        secret='A'*32
        with server.connect() as db:db.execute('INSERT INTO mfa(account_id,secret,enabled) VALUES(?,?,1)',(account['id'],secret))
        code=server.authentication.totp(secret,int(time.time())//30)
        with patch.dict(os.environ,{'DSIG_MFA_KEY':''}):
            self.assertEqual(self.request('POST','/api/auth/login',credentials|{'otp':code})[0],503)
        self.assertEqual(self.request('POST','/api/auth/login',credentials|{'otp':code})[0],200)
        with server.connect() as db:
            stored=db.execute('SELECT secret FROM mfa WHERE account_id=?',(account['id'],)).fetchone()[0]
            self.assertTrue(stored.startswith('fernet:'));self.assertEqual(server.authentication.decrypt_secret(stored),secret)

    def test_revoke_other_sessions(self):
        server.authentication.ATTEMPTS.clear()
        admin={'Authorization':'Bearer '+server.ADMIN_TOKEN,'Content-Type':'application/json'}
        s,b,_=self.request('POST','/api/admin/accounts',{'username':'sessions.test','role':'COMPTABLE','consultant_id':''},admin)
        self.assertEqual(s,201)
        credentials={'username':'sessions.test','password':'fictitious-password-123'}
        self.assertEqual(self.request('POST','/api/auth/activate',credentials|{'key':json.loads(b)['key']})[0],200)
        login={'Content-Type':'application/json','X-DSIG-Session':'cookie','Origin':f'http://127.0.0.1:{self.port}'}
        def sign_in():
            s,b,h=self.request('POST','/api/auth/login',credentials,login);self.assertEqual(s,200)
            return login|{'Authorization':'Bearer session','Cookie':h['Set-Cookie'].split(';')[0]}
        first,second=sign_in(),sign_in()
        self.assertEqual(json.loads(self.request('GET','/api/auth/me',headers=first)[1])['active_sessions'],2)
        self.assertEqual(self.request('GET','/api/admin/billing',headers=first|{'Sec-Fetch-Site':'cross-site'})[0],403)
        self.assertEqual(self.request('POST','/api/auth/revoke-others',{'password':'wrong-password'},first)[0],401)
        self.assertEqual(self.request('POST','/api/auth/revoke-others',{'password':credentials['password']},first|{'Origin':'https://evil.invalid'})[0],403)
        s,b,_=self.request('POST','/api/auth/revoke-others',{'password':credentials['password']},first)
        self.assertEqual(s,200);self.assertEqual(json.loads(b)['revoked'],1)
        self.assertEqual(self.request('GET','/api/auth/me',headers=second)[0],401)
        self.assertEqual(json.loads(self.request('GET','/api/auth/me',headers=first)[1])['active_sessions'],1)
        self.assertEqual(self.request('POST','/api/auth/logout',{},first)[0],200)
        with server.connect() as db:
            actions=[r[0] for r in db.execute("SELECT action FROM access_events WHERE actor='sessions.test'")]
        self.assertIn('REVOCATION_REFUSEE',actions);self.assertIn('SESSIONS_REVOQUEES',actions);self.assertIn('DECONNEXION',actions)

    def test_password_change_revokes_sessions(self):
        server.authentication.ATTEMPTS.clear()
        admin={'Authorization':'Bearer '+server.ADMIN_TOKEN,'Content-Type':'application/json'}
        s,b,_=self.request('POST','/api/admin/accounts',{'username':'password.test','role':'COMMERCIAL','consultant_id':''},admin)
        self.assertEqual(s,201);key=json.loads(b)['key']
        credentials={'username':'password.test','password':'fictitious-password-123'}
        self.assertEqual(self.request('POST','/api/auth/activate',credentials|{'key':key})[0],200)
        login={'Content-Type':'application/json','X-DSIG-Session':'cookie','Origin':f'http://127.0.0.1:{self.port}'}
        def sign_in():
            s,b,h=self.request('POST','/api/auth/login',credentials,login);self.assertEqual(s,200)
            return login|{'Authorization':'Bearer session','Cookie':h['Set-Cookie'].split(';')[0]}
        first,second=sign_in(),sign_in()
        data={'password':credentials['password'],'new_password':'new-fictitious-password-456','otp':''}
        path='/api/auth/change-password'
        self.assertEqual(self.request('POST',path,data|{'password':'wrong-password'},first)[0],401)
        self.assertEqual(self.request('POST',path,data,first|{'Origin':'https://evil.invalid'})[0],403)
        self.assertEqual(self.request('POST',path,data,first)[0],200)
        for session in (first,second):self.assertEqual(self.request('GET','/api/auth/me',headers=session)[0],401)
        self.assertEqual(self.request('POST','/api/auth/login',credentials,login)[0],401)
        self.assertEqual(self.request('POST','/api/auth/login',credentials|{'password':data['new_password']},login)[0],200)

    def test_role_matrix(self):
        import accounts
        expected={
            'ADMIN':(set(accounts.RESOURCES)-{'my-activity'},set(accounts.RESOURCES)-{'my-activity'}),
            'DIRECTION':({'direction','billing','missions','quotes','crm','tenders','alerts','notifications'},{'notifications'}),
            'COMMERCIAL':({'requests','crm','quotes','tenders','consultants'},{'requests','crm','quotes','tenders'}),
            'RH':({'consultants','requests','recruitment'},{'consultants','recruitment'}),
            'PROJET':({'missions','consultants','quotes'},{'missions'}),
            'CONTROLE':({'direction','missions','billing','quotes'},set()),
            'COMPTABLE':({'billing','missions'},{'billing'}),
            'AUDITEUR':({'direction','audit'},set()),
            'CONSULTANT':({'my-activity'},{'my-activity'}),
        }
        self.assertEqual(set(expected),set(accounts.ROLES))
        for role,(read,write) in expected.items():
            for resource in accounts.RESOURCES|{'unknown'}:
                for method in ('GET','POST','PATCH','DELETE','OPTIONS'):
                    with self.subTest(role=role,resource=resource,method=method):
                        self.assertEqual(accounts.allowed(role,resource,method),resource in (read if method=='GET' else write if method in ('POST','PATCH','DELETE') else set()))

    def test_sensitive_role_mfa_gate(self):
        import accounts
        server.authentication.ATTEMPTS.clear()
        with patch.dict(os.environ,{'DSIG_MFA_REQUIRED_ROLES':'DIRECTION,CONTROLE,COMPTABLE,AUDITEUR'}):
            for role in accounts.ROLES:
                self.assertEqual(accounts.mfa_required(role),role in {'ADMIN','DIRECTION','CONTROLE','COMPTABLE','AUDITEUR'})
            admin={'Authorization':'Bearer '+server.ADMIN_TOKEN,'Content-Type':'application/json'}
            s,b,_=self.request('POST','/api/admin/accounts',{'username':'secure.test','role':'ADMIN','consultant_id':''},admin)
            self.assertEqual(s,201);account=json.loads(b);key=account['key']
            self.assertEqual(self.request('GET','/api/admin/accounts',headers={'Authorization':'Bearer '+key})[0],403)
            credentials={'username':'secure.test','password':'fictitious-password-123'}
            self.assertEqual(self.request('POST','/api/auth/activate',credentials|{'key':key})[0],200)
            login={'Content-Type':'application/json','Origin':f'http://127.0.0.1:{self.port}','X-DSIG-Session':'cookie'}
            s,b,h=self.request('POST','/api/auth/login',credentials,login);self.assertEqual(s,200);self.assertEqual(json.loads(b)['permissions'],{})
            session=login|{'Authorization':'Bearer session','Cookie':h['Set-Cookie'].split(';')[0]}
            self.assertEqual(self.request('GET','/api/admin/accounts',headers=session)[0],403)
            self.assertEqual(json.loads(self.request('GET','/api/auth/me',headers=session)[1])['permissions'],{})
            s,b,_=self.request('POST','/api/auth/mfa-setup',{'password':credentials['password']},session);self.assertEqual(s,200)
            secret=json.loads(b)['secret'];now=int(time.time());step=now//30
            with patch('authentication.time.time',return_value=now):
                self.assertEqual(self.request('POST','/api/auth/mfa-confirm',{'code':server.authentication.totp(secret,step)},session)[0],200)
                self.assertEqual(self.request('GET','/api/admin/accounts',headers=session)[0],401)
                s,b,h=self.request('POST','/api/auth/login',credentials|{'otp':server.authentication.totp(secret,step+1)},login);self.assertEqual(s,200)
                session['Cookie']=h['Set-Cookie'].split(';')[0]
                self.assertEqual(self.request('GET','/api/admin/accounts',headers=session)[0],200)
                for action in ('DISABLE','ROTATE','ARCHIVE','DELETE'):
                    self.assertEqual(self.request('PATCH','/api/admin/accounts/'+account['id'],{'action':action},session)[0],409)
                self.assertEqual(self.request('GET','/api/admin/accounts',headers=session)[0],200)

    def test_named_accounts(self):
        auth={'Authorization':'Bearer '+server.ADMIN_TOKEN,'Content-Type':'application/json'}
        path='/api/admin/accounts'
        s,body,_=self.request('POST',path,{'username':'audit.test','role':'AUDITEUR','consultant_id':''},auth);self.assertEqual(s,201);a=json.loads(body)
        user={'Authorization':'Bearer '+a['key'],'Content-Type':'application/json'}
        self.assertEqual(self.request('GET','/api/admin/direction',headers=user)[0],200)
        self.assertEqual(self.request('GET','/api/admin/audit',headers=user)[0],200)
        self.assertEqual(self.request('GET','/api/admin/billing',headers=user)[0],403)
        self.assertEqual(self.request('POST',path,{'username':'bad','role':'ADMIN','consultant_id':''},user)[0],403)
        self.assertNotIn(a['key'].encode(),self.request('GET',path,headers=auth)[1])
        self.assertEqual(self.request('PATCH',path+'/'+a['id'],{'action':'DISABLE'},auth)[0],200)
        self.assertEqual(self.request('GET','/api/admin/direction',headers=user)[0],401)
        s,body,_=self.request('PATCH',path+'/'+a['id'],{'action':'ROTATE'},auth);self.assertEqual(s,200)
        self.assertEqual(self.request('GET','/api/admin/direction',headers=user)[0],401)
        self.assertEqual(self.request('GET','/api/admin/direction',headers={'Authorization':'Bearer '+json.loads(body)['key']})[0],200)

    def test_account_deletion_and_archive(self):
        auth={'Authorization':'Bearer '+server.ADMIN_TOKEN,'Content-Type':'application/json'}
        path='/api/admin/accounts'
        def create(name,role='RH'):
            code,body,_=self.request('POST',path,{'username':name,'role':role,'consultant_id':''},auth)
            self.assertEqual(code,201);return json.loads(body)
        def action(account,verb,headers=auth):
            return self.request('PATCH',path+'/'+account['id'],{'action':verb},headers)[0]
        admin=create('last.admin','ADMIN')
        for verb in ('DISABLE','ROTATE','ARCHIVE','DELETE'):self.assertEqual(action(admin,verb),409)
        fresh=create('unused.rec')
        self.assertEqual(action(fresh,'DELETE',{'Authorization':'Bearer '+fresh['key'],'Content-Type':'application/json'}),403)
        # The refused access itself is audited, so use a separate unused account.
        fresh=create('unused.second')
        self.assertEqual(action(fresh,'DELETE'),200)
        self.assertEqual(action(fresh,'DELETE'),404)
        self.assertEqual(self.request('POST',path,{'username':'UNUSED.SECOND','role':'RH','consultant_id':''},auth)[0],409)
        used=create('used.rec')
        credentials={'username':'used.rec','password':'fictitious-password-123'}
        self.assertEqual(self.request('POST','/api/auth/activate',credentials|{'key':used['key']})[0],200)
        code,body,_=self.request('POST','/api/auth/login',credentials)
        self.assertEqual(code,200)
        session={'Authorization':'Bearer '+json.loads(body)['token'],'Content-Type':'application/json'}
        self.assertEqual(self.request('GET','/api/admin/consultants',headers=session)[0],200)
        self.assertEqual(action(used,'DELETE'),409)
        self.assertEqual(action(used,'ARCHIVE'),200)
        self.assertEqual(action(used,'ROTATE'),409)
        self.assertEqual(action(used,'DELETE'),409)
        self.assertEqual(self.request('POST','/api/auth/login',credentials)[0],401)
        self.assertEqual(self.request('GET','/api/admin/consultants',headers=session)[0],401)
        items=json.loads(self.request('GET',path,headers=auth)[1])['items']
        archived=next(a for a in items if a['id']==used['id'])
        self.assertTrue(archived['archived']);self.assertFalse(archived['enabled']);self.assertFalse(archived['deletable'])
        with server.connect() as db:
            self.assertFalse(db.execute('SELECT 1 FROM credentials WHERE account_id=?',(used['id'],)).fetchone())
            self.assertTrue(db.execute("SELECT 1 FROM access_events WHERE action='COMPTE_ARCHIVE' AND resource='used.rec'").fetchone())
            self.assertTrue(db.execute("SELECT 1 FROM access_events WHERE action='COMPTE_SUPPRIME' AND resource='unused.second'").fetchone())
            with self.assertRaises(__import__('sqlite3').IntegrityError):db.execute('UPDATE accounts SET enabled=1 WHERE id=?',(used['id'],))

    def test_rec_account_invitation(self):
        import contact_mail
        auth={'Authorization':'Bearer '+server.ADMIN_TOKEN,'Content-Type':'application/json'}
        path='/api/admin/accounts'
        with patch.dict(os.environ,{'DSIG_ENV':'REC'}):
            s,b,_=self.request('POST',path,{'username':'invite.test','role':'COMMERCIAL','consultant_id':''},auth)
            self.assertEqual(s,201);account=json.loads(b)
            target=path+'/'+account['id']
            self.assertEqual(self.request('PATCH',target,{'action':'INVITE'},headers={'Authorization':'Bearer '+account['key'],'Content-Type':'application/json'})[0],403)
            self.assertEqual(self.request('PATCH',target,{'action':'INVITE'},auth)[0],200)
            self.assertEqual(self.request('PATCH',target,{'action':'INVITE'},auth)[0],409)
            cfg={'api_key':'re_test','sender':'alerts@dsig-consulting.com','test_recipient':'qa@example.invalid'}
            calls=[]
            def deliver(*args):calls.append(args);return 'provider-id'
            self.assertEqual(contact_mail.run(server.connect,cfg,deliver,invitations=True)['accepted'],1)
            self.assertEqual(contact_mail.run(server.connect,cfg,deliver,invitations=True)['accepted'],0)
            self.assertEqual(calls[0][2],'invite')
            self.assertNotIn(account['key'],str(calls))
            self.assertEqual(self.request('POST','/api/auth/activate',{'username':'invite.test','password':'fictitious-password-123','key':account['key']})[0],200)
            self.assertEqual(self.request('PATCH',target,{'action':'INVITE'},auth)[0],409)

    def test_scheduled_commercial_reminders(self):
        import notifications
        from datetime import date
        auth={'Authorization':'Bearer '+server.ADMIN_TOKEN}
        with server.connect() as db:
            db.execute("""INSERT INTO requests(id,created_at,nom,org,email,besoin,solution,message)
                VALUES ('request-1','2020-01-01 12:00:00','Privé','Fictif','qa@example.invalid','Partenariat','','Message privé')""")
            db.execute("INSERT INTO request_workflow VALUES ('request-1','','URGENTE','2020-01-02',1)")
            db.commit()
            self.assertEqual(notifications.run(db,date(2020,1,4)),3)
            self.assertEqual(notifications.run(db,date(2020,1,5)),0)
        code,body,_=self.request('GET','/api/admin/notifications',headers=auth)
        self.assertEqual(code,200)
        data=json.loads(body)
        self.assertEqual({i['kind'] for i in data['items']},{'DEMANDE_ECHEANCE','DEMANDE_AFFECTATION','DEMANDE_RELANCE'})
        self.assertNotIn('qa@example.invalid',body.decode())
        self.assertNotIn('Message privé',body.decode())
        with server.connect() as db:
            db.execute("UPDATE requests SET status='GAGNEE' WHERE id='request-1'")
            db.commit()
            self.assertEqual(notifications.run(db,date(2020,1,6)),0)
        self.assertEqual(json.loads(self.request('GET','/api/admin/notifications',headers=auth)[1])['total'],0)

    def test_scheduled_notifications(self):
        import notifications
        from datetime import date
        auth={'Authorization':'Bearer '+server.ADMIN_TOKEN,'Content-Type':'application/json'};path='/api/admin/notifications'
        self.assertEqual(self.request('GET',path)[0],401)
        with server.connect() as db:
            db.execute("INSERT INTO missions(id,quote_id,opportunity_id,consultant_id,contract_ref,start_date,end_date) VALUES('m','q','o','c','TEST','2020-01-01','2020-02-01')");db.commit()
            self.assertEqual(notifications.run(db,date(2020,1,15)),1);self.assertEqual(notifications.run(db,date(2020,1,15)),0)
            self.assertEqual(notifications.run(db,date(2020,2,2)),1)
        s,b,_=self.request('GET',path,headers=auth);self.assertEqual(s,200);d=json.loads(b);self.assertEqual(d['unread'],1);oid=d['items'][0]['id'];self.assertEqual(d['items'][0]['priority'],'URGENT')
        for _ in range(2):self.assertEqual(self.request('POST',path,{'id':oid},auth)[0],200)
        self.assertEqual(json.loads(self.request('GET',path+'?state=unread',headers=auth)[1])['total'],0)
        s,b,_=self.request('POST','/api/admin/accounts',{'username':'direction.qa','role':'DIRECTION','consultant_id':''},auth);self.assertEqual(s,201)
        other={'Authorization':'Bearer '+json.loads(b)['key'],'Content-Type':'application/json'}
        self.assertEqual(json.loads(self.request('GET',path+'?state=unread',headers=other)[1])['total'],1)
        self.assertEqual(self.request('POST',path,{'id':oid},other|{'Origin':'https://example.invalid'})[0],403)
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM notification_reads').fetchone()[0],1)
            db.execute("UPDATE missions SET status='TERMINE'");db.commit();notifications.run(db,date(2020,2,3))
        self.assertEqual(json.loads(self.request('GET',path,headers=auth)[1])['total'],0)
        self.assertEqual(json.loads(self.request('GET',path+'?state=all',headers=auth)[1])['total'],2)

    def test_business_alerts(self):
        import alerts,accounts
        from datetime import date
        auth={'Authorization':'Bearer '+server.ADMIN_TOKEN,'Content-Type':'application/json'};path='/api/admin/alerts'
        self.assertEqual(self.request('GET',path)[0],401);self.assertFalse(accounts.allowed('CONSULTANT','alerts','GET'));self.assertTrue(accounts.allowed('DIRECTION','alerts','GET'))
        self.assertEqual(self.request('GET',path+'?page=0',headers=auth)[0],400)
        self.assertEqual(self.request('GET',path+'?horizon=8',headers=auth)[0],400)
        self.assertEqual(json.loads(self.request('GET',path+'?horizon=60',headers=auth)[1])['horizon'],60)
        with server.connect() as db:
            db.execute("INSERT INTO missions(id,quote_id,opportunity_id,consultant_id,contract_ref,start_date,end_date) VALUES('m','q','o','c','TEST','2020-01-01','2020-02-01')")
            db.execute("INSERT INTO activity(id,mission_id,consultant_id,work_date,worked,billable,expenses,description) VALUES('a','m','c','2020-01-01','1','1','0','fictif')")
            db.execute("INSERT INTO opportunities(id,company,contact,email,title,mode,skills,consultant_id,next_action,followup,notes,status) VALUES('o','Test','','','Relance','REGIE','','','','2020-02-02','','PROSPECT')")
            db.execute("INSERT INTO contract_renewals(id,mission_id,old_end,new_end,reference,reason,requester) VALUES('r','m','2020-02-01','2021-01-01','R','Test','test')")
            db.execute("INSERT INTO quotes(id,opportunity_id,title,scope,mode,currency,days,rate,daily_cost,expenses,fixed_price,status) VALUES('q','o','Test','','REGIE','EUR','1','100','0','0','0','ACCEPTE')")
            db.execute("INSERT INTO invoices(id,mission_id,reference,amount,due_date) VALUES('i','m','FICTIF','100.25','2020-02-01')")
            db.execute("INSERT INTO payments(id,invoice_id,reference,amount,paid_date) VALUES('p','i','P','40.15','2020-01-01')")
            results=alerts.snapshot(db,date(2020,1,15));self.assertEqual({x['kind'] for x in results},{'CONTRAT','CRA','RELANCE','RENOUVELLEMENT','FACTURE'})
            self.assertEqual(next(x['details'] for x in results if x['kind']=='FACTURE'),'60.10 EUR restant')
            self.assertEqual(next(x['days_remaining'] for x in results if x['kind']=='CONTRAT'),17)
            self.assertFalse(any(x['kind']=='CONTRAT' for x in alerts.snapshot(db,date(2020,1,15),7)))
            self.assertTrue(any(x['kind']=='CONTRAT' for x in alerts.snapshot(db,date(2020,1,15),60)))
            db.execute("INSERT INTO payments(id,invoice_id,reference,amount,paid_date) VALUES('p2','i','P2','60.10','2020-01-02')")
            self.assertFalse(any(x['kind']=='FACTURE' for x in alerts.snapshot(db,date(2020,1,15))))
        s,b,_=self.request('GET',path+'?kind=CRA&priority=URGENT',headers=auth);self.assertEqual(s,200);self.assertEqual(json.loads(b)['total'],1)
        with server.connect() as db:db.execute("UPDATE activity SET status='VALIDE' WHERE id='a'")
        self.assertEqual(json.loads(self.request('GET',path+'?kind=CRA',headers=auth)[1])['total'],0)

    def test_private_documents(self):
        import base64,hashlib
        import accounts,antivirus
        path='/api/admin/documents';auth={'Authorization':'Bearer '+server.ADMIN_TOKEN,'Content-Type':'application/json'}
        self.assertEqual(self.request('GET',path)[0],401)
        self.assertFalse(accounts.allowed('CONSULTANT','documents','GET'))
        self.assertFalse(accounts.allowed('DIRECTION','documents','GET'))
        profile={'name':'Test','email':'qa@example.invalid','role':'Data Engineer','skills':'Python','location':'Guinée','experience':'5','availability':'Immédiate','notes':'','status':'DISPONIBLE'}
        status,body,_=self.request('POST','/api/admin/consultants',profile,auth);self.assertEqual(status,201);cid=json.loads(body)['id']
        raw=b'%PDF-1.4\nsynthetic test only\n%%EOF';payload={'category':'CV','entity_id':cid,'title':'Fictif','content':base64.b64encode(raw).decode()}
        with patch.dict(os.environ,{'DSIG_DOCUMENT_KEY':''}):self.assertEqual(self.request('POST',path,payload,auth)[0],503)
        scanner=patch('antivirus.scan');scan_mock=scanner.start();self.addCleanup(scanner.stop)
        with patch.dict(os.environ,{'DSIG_DOCUMENT_KEY':Fernet.generate_key().decode()}):
            self.assertEqual(self.request('POST',path,payload|{'content':'YWJj'},auth)[0],400)
            self.assertEqual(self.request('POST',path,payload|{'entity_id':'bad'},auth)[0],400)
            self.assertEqual(self.request('POST',path,payload|{'category':'CONTRAT'},auth)[0],400)
            for exc,code in [(antivirus.Infected,422),(antivirus.Unavailable,503)]:
                scan_mock.side_effect=exc;self.assertEqual(self.request('POST',path,payload,auth)[0],code)
                self.assertEqual(json.loads(self.request('GET',path,headers=auth)[1])['total'],0)
            scan_mock.side_effect=None
            s,b,_=self.request('POST',path,payload,auth);self.assertEqual(s,201);oid=json.loads(b)['id']
            self.assertEqual(self.request('POST',path,payload,auth)[0],409)
            s,b,h=self.request('GET',path+'/'+oid,headers=auth);self.assertEqual((s,b),(200,raw));self.assertIn('attachment',h['Content-Disposition']);self.assertEqual(h['Cache-Control'],'no-store')
            for exc,code in [(antivirus.Infected,422),(antivirus.Unavailable,503)]:
                scan_mock.side_effect=exc;self.assertEqual(self.request('GET',path+'/'+oid,headers=auth)[0],code)
            scan_mock.side_effect=None
            s,b,_=self.request('GET',path,headers=auth);self.assertEqual(s,200);item=json.loads(b)['items'][0];self.assertNotIn('ciphertext',item);self.assertEqual(item['sha256'],hashlib.sha256(raw).hexdigest())
            with server.connect() as db:
                self.assertNotIn(raw,db.execute('SELECT ciphertext FROM documents').fetchone()[0]);self.assertEqual(db.execute("SELECT count(*) FROM access_events WHERE action IN ('DOCUMENT_DEPOSE','DOCUMENT_TELECHARGE')").fetchone()[0],2)
            newer=payload|{'content':base64.b64encode(b'%PDF-1.4\nversion two\n%%EOF').decode(),'previous_id':oid,'review_date':'2020-01-01'}
            s,b,_=self.request('POST',path,newer,auth);self.assertEqual(s,201);self.assertEqual(json.loads(b)['version'],2);newid=json.loads(b)['id']
            self.assertEqual(self.request('POST',path,newer,auth)[0],409)
            items={x['id']:x for x in json.loads(self.request('GET',path,headers=auth)[1])['items']};self.assertFalse(items[oid]['current']);self.assertTrue(items[newid]['current']);self.assertTrue(items[newid]['review_due'])
            filtered=json.loads(self.request('GET',path+'?q='+newid+'&page_size=10',headers=auth)[1])
            self.assertEqual(filtered['total'],1);self.assertEqual(filtered['items'][0]['id'],newid)
            self.assertEqual(json.loads(self.request('GET',path+'?q=absent-test',headers=auth)[1])['total'],0)
            self.assertEqual(self.request('GET',path+'/'+oid,headers=auth)[1],raw)
            oldkey=os.environ['DSIG_DOCUMENT_KEY']
        with patch.dict(os.environ,{'DSIG_DOCUMENT_KEY':Fernet.generate_key().decode(),'DSIG_DOCUMENT_PREVIOUS_KEY':''}):self.assertEqual(self.request('GET',path+'/'+oid,headers=auth)[0],503)
        import documents
        newkey=Fernet.generate_key().decode()
        with patch.dict(os.environ,{'DSIG_DOCUMENT_KEY':newkey,'DSIG_DOCUMENT_PREVIOUS_KEY':oldkey}):
            self.assertEqual(self.request('GET',path+'/'+oid,headers=auth)[1],raw)
            with server.connect() as db:self.assertEqual(documents.rotate(db),2)
        with patch.dict(os.environ,{'DSIG_DOCUMENT_KEY':newkey,'DSIG_DOCUMENT_PREVIOUS_KEY':''}):self.assertEqual(self.request('GET',path+'/'+oid,headers=auth)[1],raw)

    def test_antivirus_protocol(self):
        import antivirus,struct
        from unittest.mock import MagicMock
        data=b'fiction'
        with patch.dict(os.environ,{'DSIG_CLAMD_SOCKET':''}):
            with self.assertRaises(antivirus.Unavailable):antivirus.scan(data)
        with patch.dict(os.environ,{'DSIG_CLAMD_SOCKET':'/private/clamd.sock'}),patch('antivirus.socket.socket') as factory:
            sock=MagicMock();factory.return_value.__enter__.return_value=sock
            sock.recv.side_effect=[b'stream: ',b'OK\x00'];antivirus.scan(data)
            self.assertEqual([c.args[0] for c in sock.sendall.call_args_list],[b'zINSTREAM\x00',struct.pack('!I',len(data))+data,b'\0'*4])
            for response,exc in [(b'stream: Test FOUND\x00',antivirus.Infected),(b'stream: ERROR\x00',antivirus.Unavailable),(b'stream: OK',antivirus.Unavailable),(b'',antivirus.Unavailable)]:
                sock.recv.side_effect=[response,b'']
                with self.assertRaises(exc):antivirus.scan(data)
            sock.connect.side_effect=OSError()
            with self.assertRaises(antivirus.Unavailable):antivirus.scan(data)

    def test_document_rotation_rollback(self):
        import documents,accounts,hashlib
        old=Fernet.generate_key();new=Fernet.generate_key();raw=b'%PDF-1.4\n%%EOF';cipher=Fernet(old);encrypted=cipher.encrypt(raw)
        with server.sqlite3.connect(':memory:') as db:
            accounts.schema(db);documents.schema(db)
            for oid,digest in [('a',hashlib.sha256(raw).hexdigest()),('b','invalid')]:
                db.execute('INSERT INTO documents(id,category,entity_id,title,size,sha256,ciphertext,actor) VALUES(?,?,?,?,?,?,?,?)',(oid,'CV','c',oid,len(raw),digest,encrypted,'test'))
            db.commit()
            with patch.dict(os.environ,{'DSIG_DOCUMENT_KEY':new.decode(),'DSIG_DOCUMENT_PREVIOUS_KEY':old.decode()}):
                with self.assertRaises(ValueError):documents.rotate(db)
            self.assertEqual(db.execute('SELECT ciphertext FROM documents ORDER BY id').fetchall(),[(encrypted,),(encrypted,)])
            self.assertEqual(db.execute('SELECT count(*) FROM access_events').fetchone()[0],0)

    def test_mission_activity_migration(self):
        import missions
        with server.sqlite3.connect(':memory:') as db:
            db.execute('CREATE TABLE activity(id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, work_date TEXT NOT NULL, worked TEXT NOT NULL, billable TEXT NOT NULL, expenses TEXT NOT NULL, description TEXT NOT NULL, status TEXT NOT NULL, UNIQUE(mission_id,work_date))')
            db.execute('CREATE TABLE missions(id TEXT PRIMARY KEY, consultant_id TEXT NOT NULL)')
            db.execute("INSERT INTO missions VALUES('m','c')")
            db.execute("INSERT INTO activity VALUES('a','m','2020-01-01','1','1','0','Test','VALIDE')")
            db.commit()
            missions.schema(db)
            missions.schema(db)
            self.assertEqual(db.execute('SELECT id,consultant_id,status FROM activity').fetchall(),[('a','c','VALIDE')])
            db.execute("INSERT INTO activity VALUES('b','m','c2','2020-01-01','1','1','0','Test','SOUMIS')")
            self.assertEqual(db.execute('SELECT count(*) FROM activity').fetchone()[0],2)

    def test_mission_lifecycle(self):
        auth={'Authorization':'Bearer '+server.ADMIN_TOKEN,'Content-Type':'application/json'}
        path='/api/admin/missions'
        self.assertEqual(self.request('GET',path)[0],401)
        profile={'name':'Test','email':'qa@example.invalid','role':'Data Engineer','skills':'Python','location':'Guinée','experience':'5','availability':'Immédiate','notes':'','status':'DISPONIBLE'}
        _,body,_=self.request('POST','/api/admin/consultants',profile,auth);cid=json.loads(body)['id']
        opp={'company':'Test','contact':'','email':'','title':'Analytics','mode':'REGIE','skills':'','consultant_id':cid,'next_action':'','followup':'','notes':'','status':'GAGNE'}
        _,body,_=self.request('POST','/api/admin/crm',opp,auth);oid=json.loads(body)['id']
        v=dict(opportunity_id=oid,title='Analytics',scope='Audit',mode='REGIE',currency='EUR',days='10',rate='600',daily_cost='400',expenses='50',fixed_price='0',status='ACCEPTE')
        _,body,_=self.request('POST','/api/admin/quotes',v,auth);qid=json.loads(body)['id']
        m=dict(quote_id=qid,consultant_id=cid,contract_ref='FICTIF-01',start_date='2020-01-01',end_date='2020-01-31')
        s,body,_=self.request('POST',path,m,auth);self.assertEqual(s,201);mid=json.loads(body)['id']
        for term,count in [('fictif-01',1),('analytics',1),('absent-test',0)]:
            d=json.loads(self.request('GET',path+'?page_size=10&q='+term,headers=auth)[1])
            self.assertEqual((d['total'],len(d['items'])),(count,count))
        self.assertEqual(self.request('POST',path,m,auth)[0],409)
        a=dict(work_date='2020-01-08',worked='1',billable='0.75',expenses='25',description='Test')
        route=path+'/'+mid+'/activity'
        s,body,_=self.request('POST','/api/admin/accounts',{'username':'consultant.test','role':'CONSULTANT','consultant_id':cid},auth);self.assertEqual(s,201)
        own={'Authorization':'Bearer '+json.loads(body)['key'],'Content-Type':'application/json'}
        self.assertEqual(self.request('GET',path,headers=own)[0],403)
        personal='/api/admin/my-activity'
        s,body,_=self.request('GET',personal,headers=own);self.assertEqual(s,200);self.assertEqual(json.loads(body)['missions'][0]['id'],mid);self.assertNotIn(b'daily_cost',body)
        self.assertEqual(self.request('POST',personal,a|{'mission_id':'00000000-0000-0000-0000-000000000000'},own)[0],403)
        self.assertEqual(self.request('POST',route,a|{'billable':'2'},auth)[0],400)
        s,body,_=self.request('POST',personal,a|{'mission_id':mid},own);self.assertEqual(s,201);aid=json.loads(body)['id']
        self.assertEqual(self.request('PATCH',path+'/activity/'+aid,{'status':'VALIDE'},own)[0],403)
        self.assertEqual(self.request('POST',route,a,auth)[0],409)
        self.assertEqual(self.request('PATCH',path+'/'+mid,{'status':'TERMINE'},auth)[0],409)
        self.assertEqual(json.loads(self.request('GET',path,headers=auth)[1])['items'][0]['actual_cost'],'0.00')
        self.assertEqual(self.request('PATCH',path+'/activity/'+aid,{'status':'VALIDE'},auth)[0],200)
        self.assertEqual(self.request('PATCH',path+'/activity/'+aid,{'status':'REFUSE'},auth)[0],409)
        row=json.loads(self.request('GET',path,headers=auth)[1])['items'][0];self.assertEqual(row['actual_cost'],'425.00');self.assertEqual(row['actual_margin'],'25.00')
        finance='/api/admin/billing'
        self.assertEqual(self.request('GET',finance)[0],401)
        inv=dict(mission_id=mid,reference='TEST-001',amount='450',due_date='2020-02-01')
        self.assertEqual(self.request('POST',finance+'/invoices',inv|{'amount':'451'},auth)[0],409)
        s,body,_=self.request('POST',finance+'/invoices',inv,auth);self.assertEqual(s,201);iid=json.loads(body)['id']
        self.assertEqual(self.request('POST',finance+'/invoices',inv|{'reference':'TEST-002','amount':'1'},auth)[0],409)
        p=dict(invoice_id=iid,reference='PAY-001',amount='100',paid_date='2020-02-01')
        self.assertEqual(self.request('POST',finance+'/payments',p,auth)[0],201)
        self.assertEqual(self.request('POST',finance+'/payments',p|{'reference':'PAY-002','amount':'351'},auth)[0],409)
        d=json.loads(self.request('GET',finance,headers=auth)[1]);self.assertEqual(d['totals']['EUR']['balance'],'350');self.assertEqual(d['totals']['EUR']['overdue'],'350')
        self.assertEqual(self.request('GET',finance+'/contracts')[0],401)
        self.assertEqual(self.request('GET',finance+'/contracts',headers=own)[0],403)
        self.assertEqual(self.request('GET',finance+'/contracts?page=invalid',headers=auth)[0],400)
        c=json.loads(self.request('GET',finance+'/contracts',headers=auth)[1])['items'][0]
        schedule=finance+'/schedule'
        plan={'mission_id':mid,'label':'Échéance test','kind':'PERIODIQUE','amount':'450','due_date':'2020-02-01'}
        self.assertEqual(self.request('GET',schedule)[0],401)
        self.assertEqual(self.request('POST',schedule,plan,own)[0],403)
        self.assertEqual(self.request('POST',schedule,plan|{'amount':'6001'},auth)[0],409)
        status,body,_=self.request('POST',schedule,plan,auth)
        self.assertEqual(status,201);sid=json.loads(body)['id']
        self.assertEqual(self.request('POST',schedule,plan,auth)[0],409)
        self.assertTrue(json.loads(self.request('GET',schedule,headers=auth)[1])['items'][0]['overdue'])
        self.assertEqual(self.request('PATCH',schedule+'/'+sid,{'invoice_reference':'ABSENTE'},auth)[0],409)
        self.assertEqual(self.request('PATCH',schedule+'/'+sid,{'invoice_reference':'TEST-001'},auth)[0],200)
        self.assertEqual(self.request('PATCH',schedule+'/'+sid,{'state':'ANNULE'},auth)[0],409)
        self.assertEqual(json.loads(self.request('GET',schedule,headers=auth)[1])['items'][0]['state'],'RAPPROCHE')
        self.assertEqual(json.loads(self.request('GET',finance,headers=auth)[1])['totals']['EUR']['balance'],'350')
        collection=finance+'/receivables'
        reminders=finance+'/reminders'
        reminder={'invoice_id':iid,'channel':'EMAIL','note':'Relance effectuée hors plateforme'}
        self.assertEqual(self.request('GET',collection)[0],401)
        self.assertEqual(self.request('POST',reminders,reminder,own)[0],403)
        self.assertEqual(self.request('POST',reminders,reminder|{'channel':'INVALID'},auth)[0],400)
        self.assertEqual(self.request('POST',reminders,reminder,auth)[0],201)
        aging=json.loads(self.request('GET',collection,headers=auth)[1])
        self.assertEqual(aging['aging']['EUR']['d90_plus'],'350')
        self.assertEqual(aging['items'][0]['reminder_count'],1)
        self.assertEqual(aging['items'][0]['reminders'][0]['note'],reminder['note'])
        for suffix,term in (('/receivables','test-001'),('/schedule','test-001'),('/contracts','fictif-01')):
            found=json.loads(self.request('GET',finance+suffix+'?q='+term,headers=auth)[1])
            empty=json.loads(self.request('GET',finance+suffix+'?q=absent-xyz',headers=auth)[1])
            self.assertEqual(found['total'],1)
            self.assertEqual((empty['total'],empty['items']),(0,[]))
            if suffix=='/receivables':self.assertEqual(found['aging'],empty['aging'])
        forecast=finance+'/forecast'
        self.assertEqual(self.request('GET',forecast)[0],401)
        self.assertEqual(self.request('GET',forecast,headers=own)[0],403)
        f=json.loads(self.request('GET',forecast,headers=auth)[1])['items'][0]
        self.assertEqual((f['currency'],f['overdue'],f['receipts_30'],f['planned_90']),('EUR','350','0','0'))
        from datetime import date, timedelta
        future=(date.today()+timedelta(days=45)).isoformat()
        self.assertEqual(self.request('POST',schedule,plan|{'label':'Prévision future','amount':'100','due_date':future},auth)[0],201)
        f=json.loads(self.request('GET',forecast,headers=auth)[1])['items'][0]
        self.assertEqual((f['planned_30'],f['planned_60'],f['planned_90']),('0','100','100'))
        self.assertEqual(c['contract_ref'],'FICTIF-01')
        self.assertEqual((c['planned'],c['earned'],c['invoiced'],c['paid'],c['balance'],c['overdue'],c['remaining_billable'],c['actual_cost'],c['earned_margin']),('6000.00','450.00','450.00','100.00','350.00','350.00','0.00','425.00','25.00'))
        self.assertEqual(json.loads(self.request('GET',finance+'/contracts?page=2',headers=auth)[1])['items'],[])
        self.assertEqual(self.request('POST',finance+'/milestones',{'mission_id':mid,'title':'Test','amount':'10'},auth)[0],400)
        self.assertEqual(self.request('GET','/billing.html')[0],200)
        _,body,_=self.request('POST','/api/admin/consultants',profile|{'name':'Second consultant','email':'second@example.invalid'},auth);cid2=json.loads(body)['id']
        self.assertEqual(self.request('POST',path+'/'+mid+'/team',{'consultant_id':cid2},auth)[0],201)
        self.assertEqual(self.request('POST',path+'/'+mid+'/team',{'consultant_id':cid2},auth)[0],409)
        _,body,_=self.request('POST','/api/admin/accounts',{'username':'second.test','role':'CONSULTANT','consultant_id':cid2},auth)
        own2={'Authorization':'Bearer '+json.loads(body)['key'],'Content-Type':'application/json'}
        self.assertEqual(json.loads(self.request('GET',personal,headers=own2)[1])['items'],[])
        s,body,_=self.request('POST',personal,a|{'mission_id':mid},own2);self.assertEqual(s,201);aid2=json.loads(body)['id']
        self.assertEqual(self.request('POST',personal,a|{'mission_id':mid},own2)[0],409)
        self.assertEqual(len(json.loads(self.request('GET',personal,headers=own)[1])['items']),1)
        self.assertEqual(self.request('PATCH',path+'/'+mid,{'status':'TERMINE'},auth)[0],409)
        self.assertEqual(self.request('PATCH',path+'/activity/'+aid2,{'status':'VALIDE'},auth)[0],200)
        row=json.loads(self.request('GET',path,headers=auth)[1])['items'][0];self.assertEqual(len(row['team']),2);self.assertEqual(row['actual_cost'],'850.00')
        renew=path+'/'+mid+'/renewals'
        payload={'new_end':'2020-02-29','reference':'AV-001','reason':'Extension fictive'}
        _,body,_=self.request('POST','/api/admin/accounts',{'username':'project.test','role':'PROJET','consultant_id':''},auth)
        project={'Authorization':'Bearer '+json.loads(body)['key'],'Content-Type':'application/json'}
        self.assertEqual(self.request('POST',renew,payload,own)[0],403)
        self.assertEqual(self.request('POST',renew,payload|{'new_end':'2020-01-01'},project)[0],400)
        s,body,_=self.request('POST',renew,payload,project);self.assertEqual(s,201);rid=json.loads(body)['id']
        self.assertEqual(self.request('POST',renew,payload,project)[0],409)
        self.assertEqual(self.request('PATCH',renew+'/'+rid,{'status':'VALIDE'},project)[0],403)
        self.assertEqual(self.request('PATCH',path+'/'+mid,{'status':'TERMINE'},auth)[0],409)
        self.assertEqual(self.request('PATCH',renew+'/'+rid,{'status':'VALIDE'},auth)[0],200)
        self.assertEqual(self.request('PATCH',renew+'/'+rid,{'status':'REFUSE'},auth)[0],409)
        self.assertEqual(json.loads(self.request('GET',renew,headers=auth)[1])['contract']['end_date'],'2020-02-29')
        s,body,_=self.request('POST',renew,payload|{'new_end':'2020-03-31'},project);self.assertEqual(s,201);rid2=json.loads(body)['id']
        self.assertEqual(self.request('PATCH',renew+'/'+rid2,{'status':'REFUSE'},auth)[0],200)
        self.assertEqual(json.loads(self.request('GET',renew,headers=auth)[1])['contract']['end_date'],'2020-02-29')
        self.assertEqual(self.request('PATCH',path+'/'+mid,{'status':'TERMINE'},auth)[0],200)
        self.assertEqual(self.request('POST',route,a|{'work_date':'2020-01-09'},auth)[0],400)
        self.assertEqual(self.request('GET','/missions.html')[0],200)
        _,body,_=self.request('POST','/api/admin/crm',opp|{'mode':'FORFAIT'},auth);oid2=json.loads(body)['id']
        _,body,_=self.request('POST','/api/admin/quotes',v|{'opportunity_id':oid2,'mode':'FORFAIT','fixed_price':'1000'},auth);qid2=json.loads(body)['id']
        s,body,_=self.request('POST',path,m|{'quote_id':qid2},auth);self.assertEqual(s,201);mid2=json.loads(body)['id']
        j={'mission_id':mid2,'title':'Livrable','amount':'600'}
        s,body,_=self.request('POST',finance+'/milestones',j,auth);self.assertEqual(s,201);jid=json.loads(body)['id']
        self.assertEqual(self.request('POST',finance+'/milestones',j|{'amount':'401'},auth)[0],409)
        self.assertEqual(json.loads(self.request('GET',finance+'/milestones?q=livrable',headers=auth)[1])['total'],1)
        self.assertEqual(json.loads(self.request('GET',finance+'/milestones?q=absent',headers=auth)[1])['total'],0)
        inv2=inv|{'mission_id':mid2,'reference':'TEST-F','amount':'600'}
        self.assertEqual(self.request('POST',finance+'/invoices',inv2,auth)[0],409)
        self.assertEqual(self.request('PATCH',finance+'/milestones/'+jid,{'status':'VALIDE'},auth)[0],200)
        self.assertEqual(self.request('POST',finance+'/invoices',inv2,auth)[0],201)
        control=json.loads(self.request('GET','/api/admin/direction',headers=auth)[1])['controlling']
        first=next(x for x in control['missions'] if x['mission_id']==mid)
        second=next(x for x in control['missions'] if x['mission_id']==mid2)
        self.assertEqual(first['validated_revenue'],'900.00')
        self.assertEqual(first['validated_cost'],'850.00')
        self.assertEqual(first['cost_remaining'],'3200.00')
        self.assertEqual(first['validated_margin'],'50.00')
        self.assertEqual(first['margin_rate'],'5.56')
        self.assertEqual(first['budget_cost_used_rate'],'20.99')
        self.assertEqual(second['validated_revenue'],'600')
        bucket=control['currencies'][0]
        self.assertEqual(bucket['currency'],'EUR')
        self.assertEqual(bucket['budget_revenue'],'7000.00')
        self.assertEqual(bucket['validated_revenue'],'1500.00')
        self.assertEqual(bucket['invoiced'],'1050')
        self.assertEqual(bucket['received'],'100')
        self.assertEqual(bucket['receivable'],'950')
        self.assertEqual(bucket['collection_rate'],'9.52')
        self.assertEqual(bucket['unbilled'],'450.00')
        self.assertEqual(len(control['clients']),1)
        self.assertEqual(self.request('GET','/api/admin/direction',headers=own)[0],403)
        _,body,_=self.request('POST','/api/admin/crm',opp,auth);oid3=json.loads(body)['id']
        _,body,_=self.request('POST','/api/admin/quotes',v|{'opportunity_id':oid3,'currency':'GNF'},auth);qid3=json.loads(body)['id']
        self.assertEqual(self.request('POST',path,m|{'quote_id':qid3,'consultant_id':cid2},auth)[0],201)
        control=json.loads(self.request('GET','/api/admin/direction',headers=auth)[1])['controlling']
        self.assertEqual([x['currency'] for x in control['currencies']],['EUR','GNF'])
        self.assertEqual(control['currencies'][0]['budget_revenue'],'7000.00')
        self.assertEqual(control['currencies'][1]['budget_revenue'],'6000')
        self.assertEqual(control['currencies'][1]['validated_revenue'],'0')
        self.assertIsNone(control['currencies'][1]['margin_rate'])
        expenses=finance+'/expenses'
        out={'reference':'DEP-001','currency':'EUR','amount':'80','paid_date':'2020-02-01','category':'CONSULTANT','description':'Paiement fictif','mission_id':mid}
        self.assertEqual(self.request('GET',expenses)[0],401)
        self.assertEqual(self.request('POST',expenses,out,own)[0],403)
        self.assertEqual(self.request('POST',expenses,out|{'currency':'GNF'},auth)[0],400)
        self.assertEqual(self.request('POST',expenses,out,auth)[0],201)
        self.assertEqual(self.request('POST',expenses,out|{'reference':'dep-001'},auth)[0],409)
        self.assertEqual(self.request('POST',expenses,out|{'reference':'DEP-002','currency':'GNF','amount':'1000','mission_id':''},auth)[0],201)
        budget=finance+'/planned-expenses'
        planned={'reference':'BUD-001','currency':'EUR','amount':'80','due_date':future,'category':'CONSULTANT','description':'Prévision fictive'}
        self.assertEqual(self.request('GET',budget)[0],401)
        self.assertEqual(self.request('POST',budget,planned,own)[0],403)
        self.assertEqual(self.request('POST',budget,planned|{'due_date':'2020-01-01'},auth)[0],400)
        status,body,_=self.request('POST',budget,planned,auth)
        self.assertEqual(status,201);bid=json.loads(body)['id']
        self.assertEqual(self.request('POST',budget,planned,auth)[0],409)
        f=next(x for x in json.loads(self.request('GET',forecast,headers=auth)[1])['items'] if x['currency']=='EUR')
        self.assertEqual((f['outflows_30'],f['outflows_60'],f['net_60']),('0','80','-80'))
        self.assertEqual(self.request('PATCH',budget+'/'+bid,{'expense_reference':'DEP-002'},auth)[0],409)
        self.assertEqual(self.request('PATCH',budget+'/'+bid,{'expense_reference':'DEP-001'},auth)[0],200)
        self.assertEqual(self.request('PATCH',budget+'/'+bid,{'state':'ANNULE'},auth)[0],409)
        f=next(x for x in json.loads(self.request('GET',forecast,headers=auth)[1])['items'] if x['currency']=='EUR')
        self.assertEqual((f['outflows_60'],f['recorded_outflows']),('0','80'))
        status,body,_=self.request('POST',budget,planned|{'reference':'BUD-002'},auth)
        self.assertEqual(status,201);bid2=json.loads(body)['id']
        self.assertEqual(self.request('PATCH',budget+'/'+bid2,{'expense_reference':'DEP-001'},auth)[0],409)
        self.assertEqual(self.request('PATCH',budget+'/'+bid2,{'state':'ANNULE'},auth)[0],200)
        self.assertEqual(json.loads(self.request('GET',budget,headers=auth)[1])['total'],2)
        self.assertEqual(json.loads(self.request('GET',budget+'?q=bud-002',headers=auth)[1])['total'],1)
        self.assertEqual(json.loads(self.request('GET',budget+'?q=absent',headers=auth)[1])['total'],0)
        cash=json.loads(self.request('GET',expenses,headers=auth)[1])['cash']
        self.assertEqual(cash,[{'currency':'EUR','received':'100','outflows':'80','net_flow':'20'},{'currency':'GNF','received':'0','outflows':'1000','net_flow':'-1000'}])
        control=json.loads(self.request('GET','/api/admin/direction',headers=auth)[1])['controlling']
        self.assertEqual(control['cash'],cash)
        contract=next(x for x in control['missions'] if x['mission_id']==mid)
        self.assertEqual(contract['contract_ref'],'FICTIF-01')
        self.assertEqual((contract['allocated_outflows'],contract['allocated_cash_flow']),('80','20'))
        self.assertEqual(Decimal(contract['margin_gap']),Decimal(contract['validated_margin'])-Decimal(contract['budget_margin']))
        aggregate=next(x for x in control['contracts'] if x['contract_ref']=='FICTIF-01' and x['currency']=='EUR')
        self.assertEqual(Decimal(aggregate['allocated_outflows']),Decimal('80'))
        eur=next(x for x in control['currencies'] if x['currency']=='EUR')
        self.assertEqual(Decimal(eur['allocated_outflows']),Decimal('80'))
        self.assertEqual(sum(Decimal(x['allocated_outflows']) for x in control['clients'] if x['currency']=='EUR'),Decimal('80'))
        self.assertEqual(next(x for x in control['missions'] if x['mission_id']==mid)['validated_cost'],'850.00')
        individual=[x for x in control['consultants'] if x['mission_id']==mid]
        self.assertEqual(len(individual),2)
        self.assertTrue(all(x['margin']=='25.00' for x in individual))
        self.assertIsNone(next(x for x in control['consultants'] if x['mission_id']==mid2)['margin'])
        self.assertIsNone(next(x for x in control['consultants'] if x['mission_id']==mid2)['billable_rate'])
        self.assertTrue(all(x['margin_rate']=='5.56' for x in individual))
        report='/api/admin/direction/reporting?start=2020-01-01&end=2020-02-29'
        self.assertEqual(self.request('GET',report)[0],401)
        self.assertEqual(self.request('GET',report,headers=own)[0],403)
        self.assertEqual(self.request('GET',report,headers=auth|{'Origin':'https://other.invalid'})[0],403)
        self.assertEqual(self.request('GET','/api/admin/direction/reporting?start=2020-01-01&end=2022-01-01',headers=auth)[0],400)
        rows=json.loads(self.request('GET',report,headers=auth)[1])['items']
        self.assertEqual(len(rows),3)
        self.assertEqual((rows[0]['period'],rows[0]['currency'],rows[0]['validated_revenue'],rows[0]['validated_cost']),('2020-01','EUR','900.00','850.00'))
        self.assertEqual((rows[1]['period'],rows[1]['net_flow']),('2020-02','20'))
        self.assertEqual((rows[2]['currency'],rows[2]['net_flow']),('GNF','-1000'))
        status,body,headers=self.request('GET',report+'&format=csv',headers=auth)
        self.assertEqual(status,200);self.assertIn(b'period;currency;',body);self.assertIn(b'2020-02;GNF;',body)
        today=server.date.today().isoformat() if hasattr(server,'date') else __import__('datetime').date.today().isoformat()
        today_rows=json.loads(self.request('GET','/api/admin/direction/reporting?start='+today+'&end='+today,headers=auth)[1])['items']
        self.assertEqual(today_rows[0]['validated_revenue'],'600')
        self.assertEqual(today_rows[0]['invoiced'],'1050')
        renew2=path+'/'+mid2+'/renewals'
        s,body,_=self.request('POST',renew2,payload,auth);self.assertEqual(s,201);rid3=json.loads(body)['id']
        self.assertEqual(self.request('PATCH',renew2+'/'+rid3,{'status':'VALIDE'},auth)[0],403)

    def test_finance_page_sizes_keep_global_cash(self):
        auth={'Authorization':'Bearer '+server.ADMIN_TOKEN,'Content-Type':'application/json'}
        base='/api/admin/billing'
        for suffix in ('','/expenses','/contracts','/schedule','/receivables','/milestones','/planned-expenses'):
            self.assertEqual(self.request('GET',base+suffix+'?page_size=11',headers=auth)[0],400)
            for size in (10,25,50):
                self.assertEqual(self.request('GET',base+suffix+f'?page_size={size}',headers=auth)[0],200)
        for i in range(12):
            payload={'reference':f'PAGE-{i:02d}','currency':'GNF','amount':'1000','paid_date':'2020-01-01','category':'AUTRE','description':'Dépense fictive','mission_id':''}
            self.assertEqual(self.request('POST',base+'/expenses',payload,auth)[0],201)
        first=json.loads(self.request('GET',base+'/expenses?page_size=10',headers=auth)[1])
        second=json.loads(self.request('GET',base+'/expenses?page_size=10&page=2',headers=auth)[1])
        self.assertEqual((first['total'],len(first['items']),len(second['items'])),(12,10,2))
        self.assertEqual(first['cash'],second['cash'])
        self.assertEqual(first['cash'][0]['outflows'],'12000')
        filtered=json.loads(self.request('GET',base+'/expenses?q=page-11&page_size=10',headers=auth)[1])
        self.assertEqual((filtered['total'],filtered['items'][0]['reference']),(1,'PAGE-11'))
        self.assertEqual(filtered['cash'],first['cash'])
        empty=json.loads(self.request('GET',base+'/expenses?q=%25',headers=auth)[1])
        self.assertEqual((empty['total'],empty['items']),(0,[]))
        for suffix in ('','/expenses','/contracts','/schedule','/receivables','/milestones','/planned-expenses'):
            self.assertEqual(self.request('GET',base+suffix+'?q='+'x'*181,headers=auth)[0],400)

    def test_direction_and_backup(self):
        auth={'Authorization':'Bearer '+server.ADMIN_TOKEN,'Content-Type':'application/json'}
        path='/api/admin/direction'
        self.assertEqual(self.request('GET',path)[0],401)
        self.assertEqual(self.request('GET',path,headers=auth|{'Origin':'https://other.invalid'})[0],403)
        opp={'company':'Test','contact':'','email':'','title':'Analytics','mode':'REGIE','skills':'','consultant_id':'','next_action':'','followup':'2000-01-01','notes':'','status':'QUALIFIE'}
        _,body,_=self.request('POST','/api/admin/crm',opp,auth)
        v=dict(opportunity_id=json.loads(body)['id'],title='Analytics',scope='Audit',mode='REGIE',currency='EUR',days='10',rate='600',daily_cost='400',expenses='50',fixed_price='0',status='ACCEPTE')
        self.assertEqual(self.request('POST','/api/admin/quotes',v,auth)[0],201)
        d=json.loads(self.request('GET',path,headers=auth)[1]); self.assertEqual(d['overdue'],1); self.assertEqual(d['financial'][0]['margin'],'1950.00')
        self.assertEqual(self.request('POST','/api/admin/quotes',v|{'currency':'GNF'},auth)[0],201)
        d=json.loads(self.request('GET',path,headers=auth)[1]); self.assertEqual(d['ambiguous_opportunities'],1); self.assertEqual(d['financial'],[])
        target=Path(self.tmp.name)/'backup.sqlite3';server.backup_database(target)
        with server.sqlite3.connect(target) as db:self.assertEqual(db.execute('SELECT count(*) FROM quotes').fetchone()[0],2)
        with self.assertRaises(FileExistsError):server.backup_database(target)
        self.assertEqual(self.request('GET','/en.html')[0],200)
        self.assertEqual(self.request('GET','/direction.html')[0],200)

    def test_encrypted_backup_restore_and_readiness(self):
        import operations
        root=Path(self.tmp.name); encrypted=root/'snapshot.dsigbak'; restored=root/'restored.sqlite3'
        self.assertEqual(self.request('GET','/api/ready')[0],503)
        self.assertFalse(server.DB.exists())
        self.assertEqual(self.request('POST','/api/requests',self.payload)[0],201)
        self.assertEqual(self.request('GET','/api/ready')[0],200)
        with server.connect() as db:db.execute("INSERT INTO sessions VALUES('fake-hash','fictional-account',9999999999)")
        with patch.dict(os.environ,{'DSIG_BACKUP_KEY':Fernet.generate_key().decode()}):
            operations.encrypted_backup(server.DB,encrypted,server.ROOT/'dist')
            self.assertNotIn(b'SQLite format 3',encrypted.read_bytes())
            self.assertNotIn(b'Organisation fictive',encrypted.read_bytes())
            with self.assertRaises(FileExistsError):operations.encrypted_backup(server.DB,encrypted,server.ROOT/'dist')
            with self.assertRaises(ValueError):operations.restore_isolated(encrypted,server.DB,server.DB,server.ROOT/'dist')
            with self.assertRaises(ValueError):operations.restore_isolated(encrypted,server.ROOT/'dist'/'private.sqlite3',server.DB,server.ROOT/'dist')
            with patch.dict(os.environ,{'DSIG_BACKUP_KEY':Fernet.generate_key().decode()}):
                with self.assertRaises(ValueError):operations.restore_isolated(encrypted,restored,server.DB,server.ROOT/'dist')
            self.assertFalse(restored.exists())
            damaged=root/'damaged.dsigbak';damaged.write_bytes(encrypted.read_bytes()[:-4])
            with self.assertRaises(ValueError):operations.restore_isolated(damaged,restored,server.DB,server.ROOT/'dist')
            operations.restore_isolated(encrypted,restored,server.DB,server.ROOT/'dist')
            operations.verify(restored)
            with self.assertRaises(FileExistsError):operations.restore_isolated(encrypted,restored,server.DB,server.ROOT/'dist')
        with server.sqlite3.connect(restored) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM requests').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0],0)
        with server.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0],1)
        with patch.dict(os.environ,{'DSIG_BACKUP_KEY':''}):
            with self.assertRaises(ValueError):operations.encrypted_backup(server.DB,root/'no-key.dsigbak',server.ROOT/'dist')

    def test_quote_lifecycle(self):
        auth={"Authorization":"Bearer "+server.ADMIN_TOKEN,"Content-Type":"application/json"}
        path='/api/admin/quotes'
        self.assertEqual(self.request('GET',path)[0],401)
        opp={"company":"Test","contact":"","email":"","title":"Analytics","mode":"REGIE","skills":"","consultant_id":"","next_action":"","followup":"","notes":"","status":"PROSPECT"}
        status,body,_=self.request('POST','/api/admin/crm',opp,auth)
        self.assertEqual(status,201)
        v=dict(opportunity_id=json.loads(body)['id'],title='Analytics',scope='Audit',mode='REGIE',currency='EUR',days='10.50',rate='600.01',daily_cost='400',expenses='50',fixed_price='0',status='BROUILLON')
        self.assertEqual(self.request('POST',path,v|{'rate':'NaN'},auth)[0],400)
        self.assertEqual(self.request('POST',path,v|{'opportunity_id':'00000000-0000-0000-0000-000000000000'},auth)[0],400)
        self.assertEqual(self.request('POST',path,v|{'valid_until':'2027-02-30'},auth)[0],400)
        status,body,_=self.request('POST',path,v|{'valid_until':'2027-01-31','terms':'Acompte à confirmer'},auth)
        self.assertEqual(status,201)
        d=json.loads(body); self.assertEqual(d['revenue'],'6300.11'); self.assertEqual(d['margin'],'2050.11')
        item=path+'/'+d['id']
        self.assertEqual(self.request('PATCH',item,v|{'version':2},auth)[0],409)
        status,body,_=self.request('PATCH',item,v|{'version':1,'mode':'FORFAIT','fixed_price':'9000','status':'ACCEPTE'},auth)
        self.assertEqual(status,200); self.assertEqual(json.loads(body)['margin'],'4750.00')
        self.assertEqual(self.request('PATCH',item,v|{'version':2},auth)[0],409)
        self.assertEqual(json.loads(self.request('GET',path,headers=auth)[1])['total'],1)
        proposal=json.loads(self.request('GET',path,headers=auth)[1])['items'][0]
        self.assertEqual(proposal['valid_until'],'2027-01-31')
        for term,total in [('analytics',1),('EUR',1),('absent-test',0)]:
            result=json.loads(self.request('GET',path+'?page_size=10&q='+term,headers=auth)[1])
            self.assertEqual(result['total'],total);self.assertEqual(len(result['items']),total)
        self.assertEqual(proposal['terms'],'Acompte à confirmer')
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM quote_events').fetchone()[0],2)
            self.assertEqual(json.loads(db.execute('SELECT snapshot FROM quote_events ORDER BY version DESC LIMIT 1').fetchone()[0])['terms'],'Acompte à confirmer')

    def test_quote_transmission_tracking(self):
        auth={"Authorization":"Bearer "+server.ADMIN_TOKEN,"Content-Type":"application/json"}
        path='/api/admin/quotes'
        opp={"company":"Test","contact":"","email":"","title":"Analytics","mode":"REGIE","skills":"","consultant_id":"","next_action":"","followup":"","notes":"","status":"PROSPECT"}
        status,body,_=self.request('POST','/api/admin/crm',opp,auth)
        self.assertEqual(status,201)
        v=dict(opportunity_id=json.loads(body)['id'],title='Analytics',scope='Audit',mode='REGIE',currency='EUR',days='10',rate='600',daily_cost='400',expenses='50',fixed_price='0',status='PROPOSE',valid_until='2099-01-01',terms='Acompte')
        status,body,_=self.request('POST',path,v,auth)
        self.assertEqual(status,201)
        item=path+'/'+json.loads(body)['id']
        tracking=item+'/transmission'
        data={'version':1,'action':'TRANSMIS','evidence':'Référence interne'}
        self.assertEqual(self.request('POST',tracking,data)[0],401)
        self.assertEqual(self.request('POST',tracking,data,auth|{'Origin':'https://other.invalid'})[0],403)
        self.assertEqual(self.request('POST',tracking,data|{'action':'ACCEPTE'},auth)[0],409)
        self.assertEqual(self.request('POST',tracking,data|{'evidence':''},auth)[0],400)
        self.assertEqual(self.request('POST',tracking,data,auth)[0],200)
        self.assertEqual(self.request('POST',tracking,data,auth)[0],409)
        self.assertEqual(self.request('PATCH',item,v|{'version':1},auth)[0],409)
        self.assertEqual(self.request('POST',tracking,data|{'action':'ACCEPTE','version':2},auth)[0],409)
        self.assertEqual(self.request('POST',tracking,data|{'action':'ACCEPTE'},auth)[0],200)
        proposal=json.loads(self.request('GET',path,headers=auth)[1])['items'][0]
        self.assertEqual((proposal['status'],proposal['version']),('ACCEPTE',2))
        self.assertEqual(proposal['transmission']['version'],1)
        self.assertEqual(proposal['decision']['decision'],'ACCEPTE')
        contract=item+'/contract'
        signed={'version':2,'reference':'DSIG-TEST-001','signed_date':'2020-01-01','evidence':'Copie signée archivée'}
        self.assertEqual(self.request('GET','/api/admin/missions/eligible',headers=auth)[0],200)
        self.assertEqual(json.loads(self.request('GET','/api/admin/missions/eligible',headers=auth)[1])['items'],[])
        profile={'name':'Test','email':'qa@example.invalid','role':'Data Engineer','skills':'Python','location':'Guinée','experience':'5','availability':'Immédiate','notes':'','status':'DISPONIBLE'}
        status,body,_=self.request('POST','/api/admin/consultants',profile,auth)
        self.assertEqual(status,201)
        mission=dict(quote_id=proposal['id'],consultant_id=json.loads(body)['id'],contract_ref=signed['reference'],start_date='2020-01-01',end_date='2020-01-31')
        self.assertEqual(self.request('POST','/api/admin/missions',mission,auth)[0],409)
        self.assertEqual(self.request('POST',contract,signed)[0],401)
        self.assertEqual(self.request('POST',contract,signed|{'version':1},auth)[0],409)
        self.assertEqual(self.request('POST',contract,signed|{'signed_date':'2099-01-01'},auth)[0],400)
        self.assertEqual(self.request('POST',contract,signed,auth)[0],201)
        self.assertEqual(self.request('POST',contract,signed,auth)[0],409)
        eligible=json.loads(self.request('GET','/api/admin/missions/eligible',headers=auth)[1])['items']
        self.assertEqual(eligible[0]['contract_ref'],'DSIG-TEST-001')
        self.assertEqual(self.request('POST','/api/admin/missions',mission|{'contract_ref':'AUTRE'},auth)[0],409)
        self.assertEqual(self.request('POST','/api/admin/missions',mission,auth)[0],201)
        self.assertEqual(self.request('POST','/api/admin/missions',mission,auth)[0],409)
        proposal=json.loads(self.request('GET',path,headers=auth)[1])['items'][0]
        self.assertEqual(proposal['contract']['signed_date'],'2020-01-01')

    def test_organization_directory(self):
        path='/api/admin/crm/organizations'
        auth={'Authorization':'Bearer '+server.ADMIN_TOKEN,'Content-Type':'application/json'}
        org={'name':'Client fictif','kind':'CLIENT','country':'Guinée','notes':''}
        self.assertEqual(self.request('GET',path)[0],401)
        self.assertEqual(self.request('POST',path,org,auth|{'Origin':'https://other.invalid'})[0],403)
        status,body,_=self.request('POST',path,org,auth)
        self.assertEqual(status,201)
        oid=json.loads(body)['id']
        self.assertEqual(self.request('POST',path,org|{'name':' CLIENT  FICTIF '},auth)[0],409)
        self.assertEqual(self.request('PATCH',path+'/'+oid,org|{'kind':'PARTENAIRE','version':1},auth)[0],200)
        self.assertEqual(self.request('PATCH',path+'/'+oid,org|{'version':1},auth)[0],409)
        data={'company':'Libellé historique','contact':'','email':'','title':'Mission','mode':'REGIE','skills':'','consultant_id':'','next_action':'','followup':'','notes':'','status':'PROSPECT'}
        crm_path='/api/admin/crm'
        self.assertEqual(self.request('POST',crm_path,data|{'organization_id':'00000000-0000-0000-0000-000000000000'},auth)[0],400)
        status,body,_=self.request('POST',crm_path,data|{'organization_id':oid},auth)
        self.assertEqual(status,201)
        pid=json.loads(body)['id']
        self.assertEqual(self.request('PATCH',crm_path+'/'+pid,data|{'version':1},auth)[0],200)
        item=json.loads(self.request('GET',crm_path,headers=auth)[1])['items'][0]
        self.assertEqual((item['company'],item['organization_id']),('Libellé historique',oid))
        self.assertEqual(json.loads(self.request('GET',path+'?q=CLIENT',headers=auth)[1])['items'][0]['opportunities'],1)
        self.assertEqual(self.request('PATCH',crm_path+'/'+pid,data|{'version':2,'organization_id':''},auth)[0],200)
        self.assertEqual(json.loads(self.request('GET',path,headers=auth)[1])['items'][0]['opportunities'],0)

    def test_prospect_client_conversion(self):
        path='/api/admin/crm/organizations'
        auth={'Authorization':'Bearer '+server.ADMIN_TOKEN,'Content-Type':'application/json'}
        org={'name':'Prospect V126 fictif','kind':'PROSPECT','country':'Guinée','notes':'Historique'}
        status,body,_=self.request('POST',path,org,auth)
        self.assertEqual(status,201)
        oid=json.loads(body)['id']
        target=path+'/'+oid+'/convert'
        self.assertEqual(self.request('POST',target,{'version':1})[0],401)
        self.assertEqual(self.request('POST',target,{'version':1},auth|{'Origin':'https://invalid.example'})[0],403)
        self.assertEqual(self.request('POST',target,{'version':True},auth)[0],400)
        self.assertEqual(self.request('POST',target,{'version':1},auth)[0],409)
        self.assertEqual(self.request('PATCH',path+'/'+oid,org|{'kind':'CLIENT','version':1},auth)[0],409)
        crm_path='/api/admin/crm'
        data={'company':'Libellé historique','contact':'','email':'','title':'Mission','mode':'REGIE','skills':'','consultant_id':'','next_action':'','followup':'','notes':'','status':'QUALIFIE','organization_id':oid}
        status,body,_=self.request('POST',crm_path,data,auth)
        self.assertEqual(status,201)
        pid=json.loads(body)['id']
        self.assertEqual(self.request('POST',target,{'version':1},auth)[0],409)
        self.assertEqual(self.request('PATCH',crm_path+'/'+pid,data|{'version':1,'status':'GAGNE'},auth)[0],200)
        self.assertEqual(self.request('POST',target,{'version':2},auth)[0],409)
        self.assertEqual(self.request('POST',target,{'version':1},auth)[0],200)
        self.assertEqual(self.request('POST',target,{'version':2},auth)[0],409)
        item=json.loads(self.request('GET',path,headers=auth)[1])['items'][0]
        self.assertEqual((item['id'],item['kind'],item['notes'],item['won_opportunities']),(oid,'CLIENT','Historique',1))
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT organization_id,opportunity_id,version,actor FROM organization_conversions').fetchall(),[(oid,pid,2,'bootstrap')])
            self.assertEqual(db.execute('SELECT organization_id FROM organization_links WHERE opportunity_id=?',(pid,)).fetchone()[0],oid)

    def test_crm_lifecycle(self):
        path="/api/admin/crm"
        auth={"Authorization":"Bearer "+server.ADMIN_TOKEN,"Content-Type":"application/json"}
        profile={"name":"Consultant fictif","email":"qa@example.invalid","role":"Data Engineer","skills":"Python","location":"Guinée","experience":"5","availability":"Immédiate","notes":"","status":"DISPONIBLE"}
        status, result, _=self.request("POST","/api/admin/consultants",profile,auth)
        self.assertEqual(status,201)
        cid=json.loads(result)["id"]
        data={"company":"Client fictif","contact":"Test","email":"contact@example.invalid","title":"Mission Data","mode":"REGIE","skills":"Python","consultant_id":cid,"next_action":"Relancer","followup":"2027-01-15","notes":"","status":"PROSPECT"}
        self.assertEqual(self.request("GET",path)[0],401)
        self.assertEqual(self.request("POST",path,data)[0],401)
        self.assertEqual(self.request("POST",path,data|{"mode":"INVALID"},auth)[0],400)
        self.assertEqual(self.request("POST",path,data|{"consultant_id":"00000000-0000-0000-0000-000000000000"},auth)[0],400)
        self.assertEqual(self.request("POST",path,data,auth|{"Origin":"https://other.invalid"})[0],403)
        status,result,_=self.request("POST",path,data,auth)
        self.assertEqual(status,201)
        oid=json.loads(result)["id"]
        self.assertEqual(self.request("PATCH",path+"/"+oid,data|{"status":"EN_MISSION","version":1},auth)[0],200)
        self.assertEqual(self.request("PATCH",path+"/"+oid,data|{"status":"PERDU","version":1},auth)[0],409)
        status,result,_=self.request("GET",path+"?status=EN_MISSION&q=Python",headers=auth)
        self.assertEqual(status,200)
        self.assertEqual(json.loads(result)["items"][0]["consultant_name"],"Consultant fictif")
        with server.connect() as db:
            self.assertEqual(db.execute("SELECT status FROM opportunity_events WHERE opportunity_id=? ORDER BY id",(oid,)).fetchall(),[("PROSPECT",),("EN_MISSION",)])
        self.assertEqual(self.request("GET","/crm.html")[0],200)

    def test_crm_qualification(self):
        path = '/api/admin/crm'
        auth = {'Authorization':'Bearer '+server.ADMIN_TOKEN, 'Content-Type':'application/json'}
        data = {'company':'Prospect fictif','contact':'','email':'','title':'Démo','mode':'CONSEIL','skills':'','consultant_id':'','next_action':'','followup':'','notes':'','status':'PROSPECT'}
        status, body, _ = self.request('POST', path, data, auth)
        self.assertEqual(status, 201)
        oid = json.loads(body)['id']
        def current():
            return json.loads(self.request('GET', path, headers=auth)[1])['items'][0]
        self.assertEqual(current()['qualification_score'], 0)
        qualification = {'need':'YES','budget':'UNKNOWN','decision_maker':'YES','timeline':'NO','demo_status':'SCHEDULED','demo_date':'2027-01-15'}
        payload = data | {'version':1,'qualification':qualification}
        self.assertEqual(self.request('PATCH', path+'/'+oid, payload, auth|{'Origin':'https://other.invalid'})[0],403)
        self.assertEqual(self.request('PATCH', path+'/'+oid, payload|{'qualification':qualification|{'demo_date':''}}, auth)[0],400)
        self.assertEqual(self.request('PATCH', path+'/'+oid, payload|{'qualification':qualification|{'budget':'MAYBE'}}, auth)[0],400)
        self.assertEqual(self.request('PATCH', path+'/'+oid, payload, auth)[0],200)
        self.assertEqual(current()['qualification'], qualification)
        self.assertEqual(current()['qualification_score'],2)
        self.assertEqual(self.request('PATCH', path+'/'+oid, payload, auth)[0],409)
        self.assertEqual(self.request('PATCH', path+'/'+oid, data|{'version':2}, auth)[0],200)
        self.assertEqual(current()['qualification'], qualification)

    def test_consultant_lifecycle(self):
        path = "/api/admin/consultants"
        auth = {"Authorization": "Bearer " + server.ADMIN_TOKEN, "Content-Type": "application/json"}
        data = {"name":"Consultant fictif","email":"qa@example.invalid","role":"Data Architect",
                "skills":"Python, Snowflake","location":"Guinée","experience":"12",
                "availability":"Immédiate","notes":"Test","status":"A_QUALIFIER"}
        self.assertEqual(self.request("GET",path)[0],401)
        self.assertEqual(self.request("POST",path,data)[0],401)
        self.assertEqual(self.request("POST",path,data|{"email":"invalid"},auth)[0],400)
        self.assertEqual(self.request("POST",path,data|{"experience":"99"},auth)[0],400)
        self.assertEqual(self.request("POST",path,data|{"status":"INVALID"},auth)[0],400)
        self.assertEqual(self.request("POST",path,data,auth|{"Origin":"https://other.invalid"})[0],403)
        status, result, _ = self.request("POST",path,data,auth)
        self.assertEqual(status,201)
        cid=json.loads(result)["id"]
        self.assertEqual(self.request("PATCH",path+"/"+cid,data|{"status":"DISPONIBLE","version":1},auth)[0],200)
        self.assertEqual(self.request("PATCH",path+"/"+cid,data|{"status":"ARCHIVE","version":1},auth)[0],409)
        status, result, _ = self.request("GET",path+"?status=DISPONIBLE&q=Snowflake",headers=auth)
        self.assertEqual(status,200)
        self.assertEqual(json.loads(result)["total"],1)
        self.assertEqual(self.request("PATCH",path+"/"+cid,data|{"status":"ARCHIVE","version":2},auth)[0],200)
        with server.connect() as db:
            self.assertEqual(db.execute("SELECT status FROM consultant_events WHERE consultant_id=? ORDER BY id",(cid,)).fetchall(),[("A_QUALIFIER",),("DISPONIBLE",),("ARCHIVE",)])
        self.assertEqual(self.request("GET","/consultants.html")[0],200)

    def test_tender_lifecycle(self):
        path = "/api/admin/tenders"
        auth = {"Authorization": "Bearer " + server.ADMIN_TOKEN, "Content-Type": "application/json"}
        data = {"title":"Plateforme BI", "client":"Organisation fictive", "reference":"AO-001",
                "deadline":"2027-01-15", "owner":"Test", "notes":"Qualification",
                "currency":"GNF", "budget":"12000000", "stage":"VEILLE"}
        self.assertEqual(self.request("GET",path)[0],401)
        self.assertEqual(self.request("POST",path,data)[0],401)
        self.assertEqual(self.request("POST",path,data|{"deadline":"2027-02-30"},auth)[0],400)
        self.assertEqual(self.request("POST",path,data|{"budget":"-1"},auth)[0],400)
        self.assertEqual(self.request("POST",path,data,auth|{"Origin":"https://other.invalid"})[0],403)
        status, result, _ = self.request("POST",path,data,auth)
        self.assertEqual(status,201)
        tid=json.loads(result)["id"]
        self.assertEqual(self.request("PATCH",path+"/"+tid,data|{"stage":"GO","version":1},auth)[0],200)
        self.assertEqual(self.request("PATCH",path+"/"+tid,data|{"stage":"PERDU","version":1},auth)[0],409)
        status, result, _ = self.request("GET",path+"?stage=GO&q=BI",headers=auth)
        self.assertEqual(status,200)
        self.assertEqual(json.loads(result)["total"],1)
        with server.connect() as db:
            self.assertEqual(db.execute("SELECT stage FROM tender_events WHERE tender_id=? ORDER BY id",(tid,)).fetchall(),[("VEILLE",),("GO",)])
        self.assertEqual(self.request("GET","/tenders.html")[0],200)

    def test_cybersecurity_intake(self):
        from urllib.parse import urlencode
        need='Cybersécurité & résilience'
        self.assertEqual(self.request('POST','/api/requests',self.payload|{'besoin':need})[0],201)
        status,data,_=self.request('GET','/api/admin/requests?'+urlencode({'besoin':need}),headers={'Authorization':'Bearer '+server.ADMIN_TOKEN})
        self.assertEqual(status,200);self.assertEqual(json.loads(data)['total'],1)
        self.assertEqual(json.loads(data)['items'][0]['besoin'],need)
        self.assertEqual(self.request('GET','/expertise.html?id=audit-de-cybersecurite-grc')[0],200)

    def test_new_expertise_and_career_intake(self):
        from urllib.parse import urlencode
        for need in ("Conseil & expertise", "Contrôle de gestion & finance", "Audit & contrôle interne",
                     "Avant-vente & appels d’offres", "Candidature spontanée"):
            self.assertEqual(self.request("POST", "/api/requests", self.payload | {"besoin": need})[0], 201)
        auth = {"Authorization": "Bearer " + server.ADMIN_TOKEN}
        query = urlencode({"besoin": "Candidature spontanée"})
        status, data, _ = self.request("GET", "/api/admin/requests?" + query, headers=auth)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)["total"], 1)
        self.assertEqual(json.loads(data)["items"][0]["besoin"], "Candidature spontanée")
        self.assertEqual(self.request("GET", "/api/admin/requests?besoin=invalid", headers=auth)[0], 400)

    def test_admin_filter_workflow_and_audit(self):
        auth = {"Authorization":"Bearer "+server.ADMIN_TOKEN, "Content-Type":"application/json"}
        _, data, _ = self.request("POST", "/api/requests", self.payload)
        rid = json.loads(data)["id"]
        route = "/api/admin/requests/"+rid
        self.assertEqual(self.request("PATCH", route, {"status":"QUALIFIEE","previous":"NOUVELLE"})[0], 401)
        self.assertEqual(self.request("PATCH", route, {"status":"INVALID","previous":"NOUVELLE"}, auth)[0], 400)
        self.assertEqual(self.request("PATCH", route, {"status":"QUALIFIEE","previous":"NOUVELLE"}, auth)[0], 200)
        self.assertEqual(self.request("PATCH", route, {"status":"GAGNEE","previous":"NOUVELLE"}, auth)[0], 409)
        _, data, _ = self.request("GET", "/api/admin/requests?status=QUALIFIEE&q=MineFleet", headers=auth)
        self.assertEqual(json.loads(data)["total"], 1)
        self.assertEqual(json.loads(data)["counts"]["QUALIFIEE"], 1)
        with server.connect() as db:
            self.assertEqual(db.execute("SELECT previous_status,new_status FROM request_events WHERE request_id=?", (rid,)).fetchone(), ("NOUVELLE","QUALIFIEE"))


if __name__ == "__main__":
    unittest.main()

