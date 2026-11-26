import copy
import secrets
import unittest
from cryptography.fernet import Fernet
import prod_config


def environment(mode, origin):
    return dict(DSIG_ENV=mode, DSIG_HTTPS_ORIGIN=origin,
                DSIG_DB='/app/data/requests.sqlite3',
                DSIG_MFA_REQUIRED_ROLES=','.join(sorted(prod_config.ROLES)),
                DSIG_CLAMD_SOCKET='/run/dsig-clamav/clamd.ctl',
                DSIG_ADMIN_TOKEN=secrets.token_urlsafe(48),
                **{k: Fernet.generate_key().decode() for k in prod_config.KEYS})


class ProdConfigTests(unittest.TestCase):
    def setUp(self):
        self.p = environment('PROD', prod_config.ORIGIN)
        self.r = environment('REC', 'https://rec.dsig-consulting.com')
        self.c = environment('REC', 'https://candidate.invalid')

    def check(self):
        result = prod_config.inspect(self.p, self.r, self.c)
        self.assertFalse(result['production_authorized'])
        for env in (self.p, self.r, self.c):
            for k in prod_config.SECRET_NAMES:
                if isinstance(env.get(k), str) and len(env[k]) >= 32:
                    self.assertNotIn(env[k], str(result))
        return result

    def test_valid(self):
        self.assertEqual(self.check()['status'], 'PASS')

    def test_missing_fields(self):
        original = self.p.copy()
        for key in original:
            self.p = original.copy()
            del self.p[key]
            self.assertEqual(self.check()['status'], 'FAIL', key)

    def test_cross_environment_key_reuse(self):
        for other in (self.r, self.c):
            for key in prod_config.SECRET_NAMES:
                original = self.p[key]
                self.p[key] = other[key]
                self.assertEqual(self.check()['status'], 'FAIL')
                self.p[key] = original

    def test_internal_reuse(self):
        self.p['DSIG_BACKUP_KEY'] = self.p['DSIG_MFA_KEY']
        self.assertEqual(self.check()['status'], 'FAIL')

    def test_token_key_reuse(self):
        self.p['DSIG_ADMIN_TOKEN'] = self.p['DSIG_MFA_KEY'].rstrip('=')
        self.assertEqual(self.check()['status'], 'FAIL')

    def test_invalid_key(self):
        self.p['DSIG_DOCUMENT_KEY'] = 'invalid'
        self.assertEqual(self.check()['status'], 'FAIL')

    def test_bad_reference(self):
        self.r['DSIG_ENV'] = 'PROD'
        self.assertEqual(self.check()['status'], 'FAIL')

    def test_wrong_origin(self):
        self.p['DSIG_HTTPS_ORIGIN'] = 'https://app.dsig-consulting.com.evil.invalid'
        self.assertEqual(self.check()['status'], 'FAIL')

    def test_mfa_missing(self):
        self.p['DSIG_MFA_REQUIRED_ROLES'] = 'ADMIN,CLIENT'
        self.assertEqual(self.check()['status'], 'FAIL')
