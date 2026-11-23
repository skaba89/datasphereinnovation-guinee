import sqlite3
import unittest
from datetime import date
from unittest.mock import patch

import crm
import notifications


class AutomationTests(unittest.TestCase):
    def test_saas_reminders_and_history(self):
        db=sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        crm.schema(db)
        notifications.schema(db)
        db.execute('CREATE TABLE access_events(actor,action,resource)')
        db.execute("INSERT INTO saas_subscriptions(id,offer_id,starts_on,ends_on,reference,actor) VALUES('s','offer','2026-01-01','2026-12-01','SUB','test')")
        db.execute("INSERT INTO saas_billing_preparations(subscription_id,period_start,period_end,currency,recurring,one_off,actor) VALUES('s','2026-11-01','2026-12-01','EUR','100','20','test')")
        db.execute("INSERT INTO saas_invoice_register(subscription_id,period_start,reference,issued_on,due_on,tax,actor) VALUES('s','2026-11-01','INV','2026-11-01','2026-11-20','10','test')")
        db.commit()
        today=date(2026,11,22)
        with patch('notifications.alerts.snapshot',return_value=[]),patch('notifications.commercial_reminders',return_value=[]),patch('notifications.billing_automation.reminders',return_value=[]):
            self.assertEqual(notifications.run(db,today),2)
            self.assertEqual(notifications.run(db,today),0)
            self.assertEqual(db.execute('SELECT count(*) FROM notifications WHERE active=1').fetchone()[0],2)
            db.execute("INSERT INTO saas_receipts(id,invoice_id,reference,amount,paid_on,actor) VALUES('r',1,'PAY','130','2026-11-22','test')")
            db.execute("INSERT INTO saas_subscription_renewals VALUES('s','next')")
            db.commit()
            self.assertEqual(notifications.run(db,today),0)
            self.assertEqual(db.execute('SELECT count(*) FROM notifications WHERE active=1').fetchone()[0],0)
            with patch('notifications.saas_reminders',side_effect=ValueError('secret')):
                with self.assertRaises(ValueError):notifications.run(db,today)
        self.assertEqual(db.execute('SELECT status,created,active FROM notification_runs ORDER BY id').fetchall(), [('PASS',2,2),('PASS',0,2),('PASS',0,0),('FAIL',0,0)])
