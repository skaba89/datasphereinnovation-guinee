import os
import unittest
from unittest.mock import patch, MagicMock
import prod_private_runtime_preflight as runtime

class RuntimePreflightTest(unittest.TestCase):
    def setUp(self):
        self.env={'DSIG_CONTAINER':'1','DSIG_DB':str(runtime.DB)}
        p=patch.dict(os.environ,self.env,clear=True)
        p.start()
        self.addCleanup(p.stop)
        for name in ('getuid','getgid'):
            p=patch.object(runtime.os,name,return_value=10001)
            p.start()
            self.addCleanup(p.stop)
        for module,name,value in ((runtime.prod_config,'inspect',{'status':'PASS'}),
                (runtime.lifecycle,'inspect',{'state':'EXISTING_SCHEMA'}),
                (runtime.named,'readiness',{'status':'PASS'}),
                (runtime.scanner,'inspect',{'status':'PASS'}),
                (runtime.authentication,'decrypt_secret','A'*32)):
            p=patch.object(module,name,return_value=value)
            setattr(self,module.__name__.split('.')[-1]+'_'+name,p.start())
            self.addCleanup(p.stop)
        p=patch.object(runtime.volume,'exclusive')
        lock=p.start()
        self.lock=lock.return_value
        lock.return_value.__enter__.return_value=(runtime.DATA,1)
        self.addCleanup(p.stop)
        p=patch.object(runtime.sqlite3,'connect')
        db=p.start().return_value
        db.execute.return_value.fetchall.return_value=[('fernet:synthetic',),('fernet:synthetic2',)]
        self.addCleanup(p.stop)

    def test_success_does_not_authorize_start(self):
        report=runtime.inspect({}, {})
        self.assertEqual(report['status'],'PASS')
        self.assertFalse(report['startup_authorized'])
        self.assertFalse(report['production_authorized'])

    def test_lock_retained_until_context_exit(self):
        with runtime.locked_preflight({}, {}) as report:
            self.assertEqual(report['status'],'PASS')
            self.lock.__exit__.assert_not_called()
        self.lock.__exit__.assert_called_once()

    def test_failed_scanner_releases_lock_before_return(self):
        self.prod_private_scanner_inspect.return_value={'status':'FAIL'}
        with runtime.locked_preflight({}, {}) as report:
            self.assertEqual(report['status'],'FAIL')
            self.lock.__exit__.assert_called_once()

    def test_caller_exception_releases_lock(self):
        with self.assertRaisesRegex(RuntimeError,'caller failure'):
            with runtime.locked_preflight({}, {}) as report:
                self.assertEqual(report['status'],'PASS')
                raise RuntimeError('caller failure')
        self.lock.__exit__.assert_called_once()

    def test_bootstrap_token_rejected(self):
        with patch.dict(os.environ,{'DSIG_ADMIN_TOKEN':'synthetic'}):
            self.assertEqual(runtime.inspect({}, {})['status'],'FAIL')
        self.prod_config_inspect.assert_not_called()

    def test_invalid_configuration_stops_before_data(self):
        self.prod_config_inspect.return_value={'status':'FAIL'}
        self.assertEqual(runtime.inspect({}, {})['status'],'FAIL')
        self.prod_private_data_lifecycle_inspect.assert_not_called()

    def test_mfa_key_mismatch_stops_before_scanner(self):
        self.authentication_decrypt_secret.side_effect=runtime.authentication.InvalidToken()
        self.assertEqual(runtime.inspect({}, {})['status'],'FAIL')
        self.prod_private_scanner_inspect.assert_not_called()

    def test_scanner_failure_rejected(self):
        self.prod_private_scanner_inspect.return_value={'status':'FAIL'}
        self.assertEqual(runtime.inspect({}, {})['status'],'FAIL')

if __name__=='__main__':
    unittest.main()
