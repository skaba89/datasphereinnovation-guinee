import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import contact_mail


class ContactMailTests(unittest.TestCase):
    def test_resend_request_identifies_client(self):
        cfg={'api_key':'re_test','sender':'alerts@dsig-consulting.com','test_recipient':'qa@example.invalid'}
        with patch('contact_mail.urllib.request.build_opener') as opener:
            response=opener.return_value.open.return_value.__enter__.return_value
            response.read.return_value=b'{"id":"test-provider-id"}'
            self.assertEqual(contact_mail.send(cfg,'request-id','ack','en'),'test-provider-id')
            req=opener.return_value.open.call_args.args[0]
            self.assertEqual(req.get_header('User-agent'),'DSIG-REC/1.0')
            self.assertEqual(req.get_header('Idempotency-key'),'dsig-rec/request-id/ack')
            self.assertEqual(req.get_method(),'POST')

    def test_retry_and_no_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            def connect():
                db=sqlite3.connect(Path(tmp)/'test.sqlite')
                contact_mail.schema(db)
                return db
            cfg={'api_key':'re_test','sender':'alerts@dsig-consulting.com','test_recipient':'qa@example.invalid'}
            with connect() as db:contact_mail.enqueue(db,'id','en')
            with patch('contact_mail.time.time',return_value=10**10):
                with connect() as db:db.execute('UPDATE contact_mail SET created=?,next_attempt=?',(10**10,10**10))
                def fail(*args):raise OSError('network')
                self.assertEqual(contact_mail.run(connect,cfg,fail)['retry'],2)
                self.assertEqual(contact_mail.run(connect,cfg,fail)['retry'],0)
            with patch('contact_mail.time.time',return_value=10**10+301):
                calls=[]
                def deliver(*args):calls.append(args);return 'provider-id'
                self.assertEqual(contact_mail.run(connect,cfg,deliver)['accepted'],2)
                self.assertEqual(contact_mail.run(connect,cfg,deliver)['accepted'],0)
                self.assertEqual({c[2] for c in calls},{'internal','ack'})
                self.assertTrue(all(c[3]=='en' for c in calls))
                with connect() as db:self.assertEqual(db.execute("SELECT count(*) FROM contact_mail WHERE state='ACCEPTED'").fetchone()[0],2)

    def test_config_rejects_unverified_sender(self):
        with self.assertRaises(ValueError):contact_mail.config({'api_key':'re_test','sender':'a@example.com','test_recipient':'qa@example.invalid'})
