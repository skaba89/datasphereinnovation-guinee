import unittest
from unittest.mock import patch,MagicMock
import prod_private_runtime_entrypoint as entry

class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.sock=MagicMock()
        self.kw=dict(rec={},candidate={},envelope={},public=b'',authority_pin='',expected={})
        for p in (patch.dict(entry.os.environ,{'DSIG_ENV':'PROD'},clear=True),
                  patch.object(entry.server,'ADMIN_TOKEN','')):
            p.start()
            self.addCleanup(p.stop)
        for module,name,value in ((entry.contract,'verify',{'status':'PASS'}),
                                  (entry.transport,'recipient_exchange',{'status':'PASS'})):
            p=patch.object(module,name,return_value=value)
            setattr(self,name,p.start())
            self.addCleanup(p.stop)
        p=patch.object(entry.preflight,'locked_preflight')
        self.lock=p.start().return_value
        self.lock.__enter__.return_value={'status':'PASS'}
        self.addCleanup(p.stop)

    def test_success_retains_lock(self):
        with entry.admission(self.sock,**self.kw) as report:
            self.assertEqual(report['status'],'PASS')
            self.assertFalse(report['startup_authorized'])
            self.assertFalse(report['production_authorized'])
            self.lock.__exit__.assert_not_called()
            self.assertEqual(self.recipient_exchange.call_args.kwargs['expected_uid'],0)
        self.lock.__exit__.assert_called_once()
        self.sock.close.assert_called()

    def test_invalid_signature_stops_before_preflight(self):
        self.verify.return_value={'status':'FAIL'}
        with self.assertRaises(ValueError):
            with entry.admission(self.sock,**self.kw):
                self.fail('unexpected admission')
        self.lock.__enter__.assert_not_called()
        self.recipient_exchange.assert_not_called()

    def test_preflight_failure_stops_before_handoff(self):
        self.lock.__enter__.return_value={'status':'FAIL'}
        with self.assertRaises(ValueError):
            with entry.admission(self.sock,**self.kw):
                self.fail('unexpected admission')
        self.recipient_exchange.assert_not_called()

    def test_refused_handoff_and_expired_contract(self):
        for refused in (True,False):
            self.verify.side_effect=[{'status':'PASS'},{'status':'FAIL'}]
            self.recipient_exchange.return_value={'status':'FAIL' if refused else 'PASS'}
            with self.assertRaises(ValueError):
                with entry.admission(self.sock,**self.kw):
                    self.fail('unexpected admission')

    def test_cli_remains_locked(self):
        with patch.object(entry.os,'getpid',return_value=2):
            with self.assertRaises(SystemExit):
                entry.main()

    def test_pid1_delegates_to_business_admission(self):
        import prod_private_business_runtime as business
        with patch.object(entry.os,'getpid',return_value=1), \
             patch.object(entry.os,'getuid',return_value=10001), \
             patch.object(entry.os,'getgid',return_value=10001), \
             patch.dict(entry.os.environ,{'DSIG_CONTAINER':'1'}), \
             patch.object(business,'run') as run:
            entry.main()
            run.assert_called_once_with()

    def test_pid1_admission_failure_is_sanitized(self):
        import prod_private_business_runtime as business
        with patch.object(entry.os,'getpid',return_value=1), \
             patch.object(entry.os,'getuid',return_value=10001), \
             patch.object(entry.os,'getgid',return_value=10001), \
             patch.dict(entry.os.environ,{'DSIG_CONTAINER':'1'}), \
             patch.object(business,'run',side_effect=ValueError('synthetic secret')):
            with self.assertRaisesRegex(SystemExit,'^PROD runtime admission failed

if __name__=='__main__':
    unittest.main()
):
                entry.main()

if __name__=='__main__':
    unittest.main()
