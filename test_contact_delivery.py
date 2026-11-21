import sqlite3
import unittest
import contact_mail
import contact_delivery as d


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        contact_mail.schema(self.db)
        contact_mail.enqueue(self.db,'rid','en')
        self.db.execute("UPDATE contact_mail SET state='ACCEPTED',provider_id='pid' WHERE kind='ack'")

    def tearDown(self):self.db.close()

    def test_acceptance_is_not_delivery(self):
        row=d.status(self.db)[0]
        self.assertEqual(row['queue_state'],'ACCEPTED')
        self.assertEqual(row['delivery'],'unverified')

    def test_idempotence_and_late_events(self):
        self.assertTrue(d.record(self.db,'pid','delivered'))
        self.assertFalse(d.record(self.db,'pid','delivered'))
        d.record(self.db,'pid','delivery_delayed')
        self.assertEqual(d.status(self.db)[0]['delivery'],'delivered')
        d.record(self.db,'pid','complained')
        self.assertEqual(d.status(self.db)[0]['delivery'],'complained')

    def test_unknown_provider_or_event_rejected(self):
        for provider,event in [('other','sent'),('pid','unknown')]:
            with self.assertRaises(ValueError):d.record(self.db,provider,event)

    def test_per_request_history_is_scoped_and_redacted(self):
        contact_mail.enqueue(self.db,'other','fr')
        d.record(self.db,'pid','delivered')
        result=d.for_requests(self.db,['rid','missing'])
        self.assertEqual(set(result),{'rid','missing'})
        self.assertEqual(result['missing'],[])
        self.assertEqual(len(result['rid']),2)
        ack=next(row for row in result['rid'] if row['kind']=='ack')
        self.assertEqual(ack,{'kind':'ack','language':'en','queue_state':'ACCEPTED','delivery':'delivered'})
        self.assertEqual(d.for_requests(self.db,[]),{})
        self.assertEqual(len(d.status(self.db)),4)
