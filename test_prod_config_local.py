import unittest
from cryptography.fernet import Fernet
import prod_config as config


class LocalConfigTests(unittest.TestCase):
    def setUp(self):
        self.prod = dict(DSIG_ENV='PROD', DSIG_HTTPS_ORIGIN=config.ORIGIN,
            DSIG_DB='/app/data/requests.sqlite3',
            DSIG_MFA_REQUIRED_ROLES=','.join(sorted(config.ROLES)),
            DSIG_CLAMD_SOCKET='/run/dsig-clamav/clamd.ctl')
        self.prod.update({key: Fernet.generate_key().decode() for key in config.KEYS})

    def test_local_valid_without_references(self):
        report = config.inspect_local(self.prod)
        self.assertEqual(report['status'], 'PASS')
        self.assertFalse(report['reference_secrets_checked'])
        self.assertFalse(report['production_authorized'])

    def test_local_rejects_reused_keys_and_bootstrap(self):
        self.assertEqual(config.inspect_local(dict(self.prod,
            DSIG_BACKUP_KEY=self.prod['DSIG_MFA_KEY']))['status'], 'FAIL')
        self.assertEqual(config.inspect_local(dict(self.prod,
            DSIG_ADMIN_TOKEN='x'*43))['status'], 'FAIL')

    def test_host_still_requires_references(self):
        self.assertEqual(config.inspect(self.prod, {}, {})['status'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
