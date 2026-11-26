"""Exercise real authentication handlers against an isolated SQLite account schema.

No PROD server start, network listener, real account or email.
"""
import io
import json
import os
import sqlite3
import unittest
from email.message import Message
from unittest.mock import patch

from cryptography.fernet import Fernet
import accounts
import authentication as auth
import prod_named_bootstrap


ORIGIN='https://app.dsig-consulting.com'


class Handler:
    def __init__(self, action, payload=None, *, token='', origin=ORIGIN, raw=False):
        self.path='/api/auth/'+action
        self.command='POST'
        self.headers=Message()
        self.headers['Origin']=origin
        self.headers['Content-Type']='application/json'
        self.headers['X-DSIG-Session']='cookie'
        data=json.dumps(payload or {}).encode()
        self.headers['Content-Length']=str(len(data))
        self.rfile=io.BytesIO(data)
        if token:
            self.headers['Authorization']='Bearer '+(token if raw else 'session')
            if not raw:
                self.headers['Cookie']='dsig_session='+token
        self.client_address=('127.0.0.1',12345)
        self.status=None
        self.body=None
        self.session_cookie_header=''
    def expected_origin(self):
        return ORIGIN
    def secure_cookie(self):
        return True
    def json_response(self,status,body):
        self.status=status
        self.body=body


class NamedMfaQualification(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        accounts.schema(self.db)
        self.db.commit()
        env=patch.dict(os.environ,{'DSIG_ENV':'PROD','DSIG_MFA_KEY':Fernet.generate_key().decode()})
        env.start()
        self.addCleanup(env.stop)
        attempts=patch.object(auth,'ATTEMPTS',{})
        attempts.start()
        self.addCleanup(attempts.stop)
        self.rows=prod_named_bootstrap.initialize_review(self.db,['alice.example','bob.example'])
        self.row=self.rows[0]
        self.password='synthetic-long-password-2026'

    def call(self,action,payload=None,**kwargs):
        h=Handler(action,payload,**kwargs)
        auth.handle(h,lambda:self.db)
        return h

    def login(self,**kwargs):
        return self.call('login',dict(username=self.row['username'],password=self.password,**kwargs))

    def token(self,h):
        self.assertEqual(h.status,200)
        self.assertNotIn('token',h.body)
        for attribute in ('HttpOnly','Secure','SameSite=Strict'):
            self.assertIn(attribute,h.session_cookie_header)
        return h.session_cookie_header.split(';',1)[0].split('=',1)[1]

    def activate(self):
        h=self.call('activate',dict(username=self.row['username'],password=self.password,key=self.row['activation_key']))
        self.assertEqual(h.status,200)

    def access(self,token,method='GET',origin=ORIGIN):
        h=Handler('unused',token=token,origin=origin)
        h.path='/api/admin/accounts'
        h.command=method
        return accounts.authorize(h,lambda:self.db,''),h

    def enroll(self):
        self.activate()
        token=self.token(self.login())
        permit,h=self.access(token)
        self.assertFalse(permit)
        self.assertEqual(h.status,403)
        setup=self.call('mfa-setup',{'password':self.password},token=token)
        self.assertEqual(setup.status,200)
        secret=setup.body['secret']
        step=int(auth.time.time())//30
        confirm=self.call('mfa-confirm',{'code':auth.totp(secret,step)},token=token)
        self.assertEqual(confirm.status,200)
        self.assertFalse(self.access(token)[0])
        return secret,step,confirm.body['recovery_codes']

    def test_full_named_flow(self):
        secret,step,codes=self.enroll()
        self.assertEqual(len(codes),8)
        self.assertEqual(self.login().status,401)
        self.assertEqual(self.login(otp=auth.totp(secret,step)).status,401)
        with patch.object(auth.time,'time',return_value=(step+1)*30):
            token=self.token(self.login(otp=auth.totp(secret,step+1)))
            self.assertTrue(self.access(token)[0])
            self.assertFalse(self.access(token,'POST','https://other.invalid')[0])
        stored=self.db.execute('SELECT secret FROM mfa WHERE account_id=?',(self.row['id'],)).fetchone()[0]
        self.assertTrue(stored.startswith('fernet:'))
        self.assertNotIn(secret,stored)

    def test_recovery_single_use(self):
        _,_,codes=self.enroll()
        token=self.token(self.login(otp=codes[0]))
        self.assertTrue(self.access(token)[0])
        self.assertEqual(self.login(otp=codes[0]).status,401)
        self.assertEqual(self.db.execute('SELECT count(*) FROM recovery_codes WHERE account_id=?',(self.row['id'],)).fetchone()[0],7)

    def test_activation_reuse(self):
        self.activate()
        h=self.call('activate',dict(username=self.row['username'],password=self.password,key=self.row['activation_key']))
        self.assertEqual(h.status,401)

    def test_logout_revokes_session(self):
        _,_,codes=self.enroll()
        token=self.token(self.login(otp=codes[0]))
        h=self.call('logout',{},token=token)
        self.assertEqual(h.status,200)
        self.assertFalse(self.access(token)[0])
