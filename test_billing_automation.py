"""Billing automation: internal "to invoice" reminders and automatic dunning emails (REC queue)."""
import tempfile
import unittest
from datetime import date
from pathlib import Path

import billing_automation
import contact_mail
import notifications
import server

TODAY = date(2026, 11, 23)
CFG = {'api_key': 're_test_key', 'sender': 'notifications@dsig-consulting.com', 'test_recipient': 'test@example.invalid'}


class BillingAutomationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original = server.DB
        server.DB = Path(self.tmp.name) / 'billing-automation.sqlite3'
        with server.connect() as db:
            self.client(db, 'web', 'client@example.invalid', 'en', ack=True)
            self.client(db, 'noack', 'noack@example.invalid', 'fr', ack=False)
            db.execute("""INSERT INTO opportunities(id,company,contact,email,title,mode,skills,consultant_id,next_action,followup,notes,status)
                VALUES ('o-direct','Client direct fictif','','','Sans formulaire','REGIE','','','','','','GAGNE')""")
            for key in ('web', 'noack', 'direct'):
                db.execute("""INSERT INTO quotes(id,opportunity_id,title,scope,mode,currency,days,rate,daily_cost,expenses,fixed_price,status)
                    VALUES (?,?,'Devis fictif','x','FORFAIT','EUR','0','0','0','0','1000','ACCEPTE')""", ('q-' + key, 'o-' + key))
                db.execute("""INSERT INTO missions(id,quote_id,opportunity_id,consultant_id,contract_ref,start_date,end_date)
                    VALUES (?,?,?,'c',?,'2026-01-01','2026-12-31')""", ('m-' + key, 'q-' + key, 'o-' + key, 'CTR-' + key.upper()))
            invoice = "INSERT INTO invoices(id,mission_id,reference,amount,due_date) VALUES (?,?,?,?,?)"
            db.execute(invoice, ('i-late', 'm-web', 'FAC-LATE', '400', '2026-11-10'))      # 13 days late
            db.execute(invoice, ('i-recent', 'm-web', 'FAC-RECENT', '100', '2026-11-20'))  # 3 days late
            db.execute(invoice, ('i-paid', 'm-web', 'FAC-PAID', '100', '2026-10-01'))
            db.execute("INSERT INTO payments(id,invoice_id,reference,amount,paid_date) VALUES ('p','i-paid','PAY','100','2026-10-02')")
            db.execute(invoice, ('i-noack', 'm-noack', 'FAC-NOACK', '100', '2026-10-01'))
            db.execute(invoice, ('i-direct', 'm-direct', 'FAC-DIRECT', '100', '2026-10-01'))

    def client(self, db, key, email, language, ack):
        rid = 'r-' + key
        db.execute("""INSERT INTO requests(id,created_at,nom,org,email,besoin,solution,message)
            VALUES (?,'2026-01-01 10:00:00','Contact fictif','Org fictive',?,'Mission au forfait','','Fictif')""", (rid, email))
        db.execute("""INSERT INTO opportunities(id,company,contact,email,title,mode,skills,consultant_id,next_action,followup,notes,status)
            VALUES (?,'Client fictif','Contact fictif',?,'Mission','FORFAIT','','','','','','GAGNE')""", ('o-' + key, email))
        db.execute("INSERT INTO request_leads(request_id,opportunity_id,outcome) VALUES (?,?,'CREATED')", (rid, 'o-' + key))
        if ack:
            db.execute("INSERT INTO contact_mail(request_id,kind,language,state,created,next_attempt) VALUES (?,'ack',?,'ACCEPTED',0,0)", (rid, language))

    def tearDown(self):
        server.DB = self.original
        self.tmp.cleanup()

    def schedule(self, day):
        with server.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            return billing_automation.schedule(db, day)

    def dunning(self):
        with server.connect() as db:
            return db.execute("SELECT request_id,kind,language FROM contact_mail WHERE kind LIKE 'dunning-%' ORDER BY created,kind").fetchall()

    def test_first_reminder_only_for_eligible_invoice_and_idempotent(self):
        self.assertEqual(self.schedule(TODAY), 1)
        self.assertEqual(self.schedule(TODAY), 0)
        self.assertEqual(self.dunning(), [('r-web', billing_automation.kind('i-late', 1), 'en')])
        with server.connect() as db:
            self.assertEqual(db.execute("SELECT channel,note FROM billing_reminders WHERE invoice_id='i-late'").fetchall(),
                             [('EMAIL', 'Relance automatique n°1 planifiée (file e-mail REC)')])
            self.assertEqual(db.execute("SELECT action FROM access_events WHERE actor=?", (billing_automation.ACTOR,)).fetchone()[0],
                             'RELANCE_FACTURE_PLANIFIEE')

    def test_second_reminder_needs_21_days_and_spacing(self):
        self.assertEqual(self.schedule(TODAY), 1)
        self.assertEqual(self.schedule(date(2026, 12, 2)), 1)  # i-recent reaches J+7 → its first reminder only
        with server.connect() as db:
            # i-late is now 22 days late but its first email is only minutes old: no second email yet.
            self.assertIsNone(db.execute("SELECT 1 FROM contact_mail WHERE kind=?", (billing_automation.kind('i-late', 2),)).fetchone())
            db.execute("UPDATE contact_mail SET created=created-15*86400 WHERE kind LIKE 'dunning-%'")
        self.assertEqual(self.schedule(date(2026, 12, 2)), 1)
        self.assertEqual(self.schedule(date(2027, 1, 30)), 1)  # i-recent level 2; nothing beyond level 2
        self.assertEqual(self.schedule(date(2027, 3, 30)), 0)
        self.assertEqual(len(self.dunning()), 4)

    def test_recent_manual_reminder_or_payment_suspends_automation(self):
        with server.connect() as db:
            db.execute("INSERT INTO billing_reminders(id,invoice_id,channel,note,created_at) VALUES ('man','i-late','TELEPHONE','Appel client','2026-11-20 09:00:00')")
        self.assertEqual(self.schedule(TODAY), 0)
        with server.connect() as db:
            db.execute("INSERT INTO payments(id,invoice_id,reference,amount,paid_date) VALUES ('p2','i-late','PAY-2','400','2026-11-22')")
        self.assertEqual(self.schedule(date(2026, 12, 10)), 1)  # only i-recent remains unpaid
        self.assertEqual(self.dunning()[0][1], billing_automation.kind('i-recent', 1))

    def test_worker_sends_reference_and_due_date_without_amount(self):
        self.schedule(TODAY)
        delivered = []
        def fake(cfg, request_id, kind, language, **kwargs):
            subject, plain, _ = billing_automation.render(request_id, language, *kwargs['details'])
            delivered.append((kwargs.get('recipient'), subject, plain))
            return 'provider-1'
        result = contact_mail.run(server.connect, CFG | {'rec_customer_recipients': ['client@example.invalid']}, deliver=fake)
        self.assertEqual(result['accepted'], 1)
        recipient, subject, plain = delivered[0]
        self.assertEqual(recipient, 'client@example.invalid')
        self.assertEqual(subject, '[REC TEST] DSIG — Payment reminder')
        self.assertIn('FAC-LATE', plain)
        self.assertIn('2026-11-10', plain)
        self.assertNotIn('400', plain)
        # Without the allowlist, the same kind of email goes to the REC test mailbox only.
        with server.connect() as db:
            db.execute("DELETE FROM contact_mail WHERE kind LIKE 'dunning-%'")
            db.execute('DELETE FROM billing_dunning')
            db.execute('DELETE FROM billing_reminders')
            db.execute('DELETE FROM contact_mail_recipient')
        self.schedule(TODAY)
        delivered.clear()
        contact_mail.run(server.connect, CFG | {'rec_customer_recipients': ['someone-else@example.invalid']}, deliver=fake)
        self.assertEqual(delivered[0][0], 'test@example.invalid')

    def test_render_bilingual_and_escaped(self):
        subject, plain, markup = billing_automation.render('ref', 'fr', 'FAC-<b>', '2026-11-10', 2)
        self.assertEqual(subject, '[REC TEST] DSIG — Rappel de règlement (second rappel)')
        self.assertIn('FAC-<b>', plain)
        self.assertIn('FAC-&lt;b&gt;', markup)

    def test_internal_to_invoice_notifications(self):
        with server.connect() as db:
            db.execute("""INSERT INTO billing_schedule(id,mission_id,label,kind,amount,due_date)
                VALUES ('s-late','m-direct','Acompte fictif','ACOMPTE','300','2026-11-01'),
                       ('s-soon','m-direct','Solde fictif','SOLDE','200','2026-11-28'),
                       ('s-far','m-direct','Plus tard','SOLDE','100','2027-03-01')""")
            db.execute("INSERT INTO milestones(id,mission_id,title,amount,status) VALUES ('j1','m-noack','Livrable fictif','600','VALIDE')")
            db.execute("INSERT INTO billing_events(entity_id,event,created_at) VALUES ('j1','JALON_VALIDE','2026-11-15 10:00:00')")
            items = {(x['kind'], x['id']): x for x in billing_automation.reminders(db, TODAY)}
        self.assertEqual(set(items), {('ECHEANCE_A_FACTURER', 's-late'), ('ECHEANCE_A_FACTURER', 's-soon'), ('JALON_A_FACTURER', 'm-noack')})
        self.assertEqual(items[('ECHEANCE_A_FACTURER', 's-late')]['priority'], 'URGENT')
        self.assertEqual(items[('ECHEANCE_A_FACTURER', 's-soon')]['priority'], 'A_TRAITER')
        # m-noack: 600 validated, 100 invoiced.
        self.assertEqual(items[('JALON_A_FACTURER', 'm-noack')]['details'], '500 EUR validés non facturés')
        self.assertEqual(items[('JALON_A_FACTURER', 'm-noack')]['due'], '2026-11-15')
        with server.connect() as db:
            notifications.run(db, TODAY)
            self.assertEqual(notifications.run(db, TODAY), 0)
            kinds = {r[0] for r in db.execute('SELECT kind FROM notifications WHERE active=1')}
        self.assertTrue({'ECHEANCE_A_FACTURER', 'JALON_A_FACTURER', 'FACTURE'} <= kinds)


if __name__ == '__main__':
    unittest.main()
