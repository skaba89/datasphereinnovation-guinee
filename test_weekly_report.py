"""Weekly management report: period boundaries, aggregates, privacy, idempotent sending."""
import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from datetime import date
from pathlib import Path

import server
import weekly_report

TODAY = date(2026, 11, 23)  # Monday, ISO week 2026-W48; period 2026-11-16 → 2026-11-23 (excluded)
CFG = {'api_key': 're_test_key', 'sender': 'rapport@dsig-consulting.com', 'test_recipient': 'test@example.invalid'}


class WeeklyReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original = server.DB
        server.DB = Path(self.tmp.name) / 'report.sqlite3'
        with server.connect() as db:
            req = "INSERT INTO requests(id,created_at,nom,org,email,besoin,solution,message,status) VALUES (?,?,?,?,?,?,'','Message privé fictif',?)"
            db.execute(req, ('r-in', '2026-11-16 08:00:00', 'Nom privé', 'Org A fictive', 'prive@example.invalid', 'Mission en régie', 'NOUVELLE'))
            db.execute(req, ('r-in2', '2026-11-22 23:59:00', 'Nom B', 'Org B fictive', 'b@example.invalid', 'Data & IA', 'QUALIFIEE'))
            db.execute(req, ('r-old', '2026-11-15 23:59:59', 'Nom C', 'Org C fictive', 'c@example.invalid', 'Data & IA', 'NOUVELLE'))
            db.execute(req, ('r-today', '2026-11-23 00:00:01', 'Nom D', 'Org D fictive', 'd@example.invalid', 'Data & IA', 'NOUVELLE'))
            opp = "INSERT INTO opportunities(id,company,contact,email,title,mode,skills,consultant_id,next_action,followup,notes,status) VALUES (?,?,'Contact privé','contact@example.invalid',?,'CONSEIL','','','',?,'',?)"
            db.execute(opp, ('o1', 'Client retard fictif', 'Audit en retard', '2026-11-20', 'QUALIFIE'))
            db.execute(opp, ('o2', 'Client gagné fictif', 'Mission gagnée', '', 'GAGNE'))
            db.execute(opp, ('o3', 'Client futur fictif', 'Relance future', '2026-12-01', 'PROSPECT'))
            db.execute(opp, ('o4', 'Client perdu fictif', 'Perdu ancien', '2026-11-01', 'PERDU'))
            db.execute("INSERT INTO opportunity_events(opportunity_id,status,version,created_at) VALUES ('o2','GAGNE',2,'2026-11-18 10:00:00')")
            db.execute("INSERT INTO opportunity_events(opportunity_id,status,version,created_at) VALUES ('o4','PERDU',2,'2026-11-10 10:00:00')")
            db.execute("INSERT INTO request_leads(request_id,opportunity_id,outcome,created_at) VALUES ('r-in','o1','CREATED','2026-11-16 08:00:00')")
            db.execute("INSERT INTO request_leads(request_id,opportunity_id,outcome,created_at) VALUES ('r-in2','o1','DUPLICATE','2026-11-22 23:59:00')")
            db.execute("INSERT INTO quotes(id,opportunity_id,title,scope,mode,currency,days,rate,daily_cost,expenses,fixed_price,status) VALUES ('q1','o2','Devis fictif','x','REGIE','EUR','1','100','50','0','0','ACCEPTE')")
            db.execute("INSERT INTO quote_transmissions(quote_id,version,actor,evidence,created_at) VALUES ('q1',1,'a','e','2026-11-17 09:00:00')")
            db.execute("INSERT INTO missions(id,quote_id,opportunity_id,consultant_id,contract_ref,start_date,end_date) VALUES ('m1','q1','o2','c','REF-1','2026-01-01','2026-12-31')")
            db.execute("INSERT INTO invoices(id,mission_id,reference,amount,due_date) VALUES ('i1','m1','INV-1','1000','2026-11-01')")
            db.execute("INSERT INTO invoices(id,mission_id,reference,amount,due_date) VALUES ('i2','m1','INV-2','500','2026-12-30')")
            db.execute("INSERT INTO payments(id,invoice_id,reference,amount,paid_date) VALUES ('p1','i1','PAY-1','250','2026-11-05')")

    def tearDown(self):
        server.DB = self.original
        self.tmp.cleanup()

    def test_compute_respects_period_and_aggregates(self):
        with server.connect() as db:
            r = weekly_report.compute(db, TODAY)
        self.assertEqual((r['week'], r['start'], r['end']), ('2026-W48', '2026-11-16', '2026-11-23'))
        self.assertEqual(r['requests'], 2)
        self.assertEqual((r['auto_leads'], r['duplicates'], r['won'], r['lost'], r['quotes_sent']), (1, 1, 1, 0, 1))
        self.assertEqual(r['pipeline'], {'QUALIFIE': 1, 'GAGNE': 1, 'PROSPECT': 1, 'PERDU': 1})
        self.assertEqual(r['overdue_followups'], [['Client retard fictif', 'Audit en retard', '2026-11-20']])
        self.assertEqual(r['overdue_receivables'], {'EUR': '750'})
        # r-in and r-old are NOUVELLE without events and older than 48 h at the period end.
        self.assertEqual(r['untreated_48h'], 2)

    def test_render_contains_no_private_contact_data(self):
        with server.connect() as db:
            subject, text, body = weekly_report.render(weekly_report.compute(db, TODAY))
        self.assertEqual(subject, '[DSIG] Rapport hebdomadaire 2026-W48')
        self.assertIn('Prospect : 1', text)
        self.assertIn('Client retard fictif — Audit en retard', text)
        self.assertIn('750 EUR', text)
        for private in ('Nom privé', 'prive@example.invalid', 'Message privé', 'Contact privé', 'contact@example.invalid'):
            self.assertNotIn(private, text + body)
        self.assertNotIn('<script', body)

    def test_send_once_per_iso_week_and_recipients(self):
        sent = []
        def fake(cfg, week, subject, text, body):
            sent.append((week, weekly_report.recipients(cfg)))
            return 'provider-1'
        self.assertEqual(weekly_report.send(server.connect, CFG, TODAY, fake), 'SENT')
        self.assertEqual(weekly_report.send(server.connect, CFG, date(2026, 11, 26), fake), 'ALREADY_SENT')
        self.assertEqual(sent, [('2026-W48', ['test@example.invalid'])])
        cfg = CFG | {'report_recipients': ['direction@example.invalid']}
        self.assertEqual(weekly_report.send(server.connect, cfg, date(2026, 11, 30), fake), 'SENT')
        self.assertEqual(sent[-1], ('2026-W49', ['direction@example.invalid']))
        for bad in (['not-an-email'], 'direction@example.invalid', ['a@example.invalid'] * 11):
            with self.assertRaises(ValueError):
                weekly_report.send(server.connect, CFG | {'report_recipients': bad}, date(2026, 12, 7), fake)
        with self.assertRaises(ValueError):
            weekly_report.send(server.connect, {'sender': 'x@example.invalid'}, date(2026, 12, 7), fake)

    def test_failed_delivery_is_retried_next_run(self):
        def broken(*args):
            raise OSError('network')
        with self.assertRaises(OSError):
            weekly_report.send(server.connect, CFG, TODAY, broken)
        self.assertEqual(weekly_report.send(server.connect, CFG, TODAY, lambda *a: 'provider-2'), 'SENT')


class WeeklyReportPageTests(WeeklyReportTests):
    """Online report: GET /api/admin/direction/weekly-report (JSON / CSV), role filtering."""
    def setUp(self):
        super().setUp()
        self.original_token = server.ADMIN_TOKEN
        server.ADMIN_TOKEN = 'test-token-only-' + 'x' * 32
        self.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        server.ADMIN_TOKEN = self.original_token
        super().tearDown()

    def get(self, query, auth=True):
        conn = HTTPConnection('127.0.0.1', self.http.server_address[1], timeout=5)
        conn.request('GET', '/api/admin/direction/weekly-report' + query, headers={'Authorization': 'Bearer ' + server.ADMIN_TOKEN} if auth else {})
        res = conn.getresponse()
        body, headers = res.read(), dict(res.getheaders())
        conn.close()
        return res.status, body, headers

    def test_json_csv_and_validation(self):
        self.assertEqual(self.get('?date=2026-11-23', auth=False)[0], 401)
        for bad in ('?date=2026-13-01', '?date=23/11/2026', '?date=1999-01-01', '?format=pdf', '?date=2026-11-23&date=2026-11-24', '?other=1'):
            self.assertEqual(self.get(bad)[0], 400, bad)
        status, body, _ = self.get('?date=2026-11-23')
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual((data['week'], data['requests'], data['overdue_receivables']), ('2026-W48', 2, {'EUR': '750'}))
        self.assertEqual(data['overdue_followups'], [['Client retard fictif', 'Audit en retard', '2026-11-20']])
        status, body, headers = self.get('?date=2026-11-23&format=csv')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Disposition'], 'attachment; filename="rapport-direction-2026-W48.csv"')
        self.assertEqual(headers['Cache-Control'], 'no-store')
        text = body.decode('utf-8-sig')
        self.assertTrue(text.startswith('Section;Indicateur;Valeur'))
        self.assertIn('Activité;Demandes reçues;2', text)
        self.assertIn('Créances échues non encaissées;EUR;750', text)
        for private in ('Nom privé', 'prive@example.invalid', 'Message privé', 'Contact privé'):
            self.assertNotIn(private, text)

    def test_roles_without_crm_get_totals_only(self):
        class Fake:
            role, path = 'AUDITEUR', '/api/admin/direction/weekly-report?date=2026-11-23'
            def admin_authorized(self):
                return True
            def json_response(self, status, body):
                self.result = (status, body)
        fake = Fake()
        weekly_report.handle(fake, server.connect)
        status, body = fake.result
        self.assertEqual((status, body['overdue_followups'], body['overdue_followups_total']), (200, [], 1))

    def test_csv_neutralizes_formulas(self):
        with server.connect() as db:
            db.execute("UPDATE opportunities SET company='=HYPERLINK(1)' WHERE id='o1'")
        text = self.get('?date=2026-11-23&format=csv')[1].decode('utf-8-sig')
        self.assertIn("'=HYPERLINK(1) — Audit en retard", text)

    # Inherited tests are already run by WeeklyReportTests.
    test_compute_respects_period_and_aggregates = test_render_contains_no_private_contact_data = None
    test_send_once_per_iso_week_and_recipients = test_failed_delivery_is_retried_next_run = None


if __name__ == '__main__':
    unittest.main()
