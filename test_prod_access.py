import os
import sqlite3
import unittest
from unittest.mock import patch
import accounts


class Handler:
    path='/api/admin/accounts'
    command='GET'
    def __init__(self, header):
        self.headers={'Authorization':header}
        self.status=None
    def json_response(self,status,body):
        self.status=status


class ProdAccessTests(unittest.TestCase):
    def test_bootstrap_and_raw_bearer_rejected_before_db(self):
        def forbidden():
            self.fail('DB must not be opened')
        for mode in ('PROD','production',''):
            with patch.dict(os.environ,{'DSIG_ENV':mode}):
                for header in ('Bearer '+'x'*48,'Bearer dsig_'+'a'*43,''):
                    h=Handler(header)
                    self.assertFalse(accounts.authorize(h,forbidden,'x'*48))
                    self.assertEqual(h.status,401)

    def test_dev_rec_bootstrap_preserved(self):
        db=sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        accounts.schema(db)
        for mode in ('DEV','REC'):
            with patch.dict(os.environ,{'DSIG_ENV':mode}):
                h=Handler('Bearer '+'x'*48)
                self.assertTrue(accounts.authorize(h,lambda:db,'x'*48))
                self.assertEqual(h.actor,'bootstrap')

    def test_cross_site_cookie_rejected(self):
        with patch.dict(os.environ,{'DSIG_ENV':'PROD'}):
            h=Handler('Bearer session')
            h.headers['Sec-Fetch-Site']='cross-site'
            self.assertFalse(accounts.authorize(h,lambda:self.fail('DB access'),'x'*48))
            self.assertEqual(h.status,403)
