"""Offline qualification using real auth handlers and persistent business schema."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from contextlib import closing, contextmanager
from unittest.mock import patch
from cryptography.fernet import Fernet
import authentication as auth
import accounts
import prod_private_named_volume as named
from test_prod_named_mfa import Handler

@unittest.skipIf(os.getuid()==0 or os.getgid()==0,'non-root operator required')
class PersistentMfaTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.data=Path(temp.name)/'data'
        self.data.mkdir(mode=0o700)
        self.db=self.data/'requests.sqlite3'
        env=patch.dict(os.environ,{'DSIG_ENV':'PROD','DSIG_MFA_KEY':Fernet.generate_key().decode(),
            'DSIG_MFA_REQUIRED_ROLES':'ADMIN,CLIENT,DIRECTION,CONTROLE,COMPTABLE,AUDITEUR'})
        env.start()
        self.addCleanup(env.stop)
        attempts=patch.object(auth,'ATTEMPTS',{})
        attempts.start()
        self.addCleanup(attempts.stop)
        named.volume.initialize_isolated(self.data)
        self.rows=named.initialize_review(self.data,['alice.example','bob.example'])

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.db)) as db:
            with db:
                yield db

    def call(self,action,payload,token=''):
        h=Handler(action,payload,token=token)
        auth.handle(h,self.connect)
        return h

    def token(self,h):
        self.assertEqual(h.status,200)
        self.assertNotIn('token',h.body)
        return h.session_cookie_header.split(';',1)[0].split('=',1)[1]

    def access(self,token):
        h=Handler('unused',token=token)
        h.path='/api/admin/accounts'
        h.command='GET'
        return accounts.authorize(h,self.connect,'')

    def test_two_named_admins_persist_and_require_mfa(self):
        self.assertEqual(named.readiness(self.data)['status'],'FAIL')
        for index,row in enumerate(self.rows):
            auth.ATTEMPTS.clear()
            credentials=dict(username=row['username'],password='synthetic-qualification-password-'+str(index))
            self.assertEqual(self.call('activate',dict(credentials,key=row['activation_key'])).status,200)
            token=self.token(self.call('login',credentials))
            self.assertFalse(self.access(token))
            setup=self.call('mfa-setup',{'password':credentials['password']},token)
            self.assertEqual(setup.status,200)
            step=int(auth.time.time())//30
            confirm=self.call('mfa-confirm',{'code':auth.totp(setup.body['secret'],step)},token)
            self.assertEqual(confirm.status,200)
            self.assertFalse(self.access(token))
            self.assertEqual(self.call('login',credentials).status,401)
            token=self.token(self.call('login',dict(credentials,otp=confirm.body['recovery_codes'][0])))
            self.assertTrue(self.access(token))
            self.assertEqual(self.call('login',dict(credentials,otp=confirm.body['recovery_codes'][0])).status,401)
            self.assertEqual(self.call('logout',{},token).status,200)
            self.assertFalse(self.access(token))
        report=named.readiness(self.data)
        self.assertEqual(report['status'],'PASS')
        self.assertFalse(report['production_authorized'])

if __name__=='__main__':
    unittest.main()
