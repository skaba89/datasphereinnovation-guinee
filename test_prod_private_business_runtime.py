import threading
import unittest
from unittest.mock import patch, MagicMock
import prod_private_business_runtime as runtime


class BusinessRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.stop = threading.Event()
        self.launch = dict(envelope={}, public=b'', authority_pin='', expected={})
        for p in (
            patch.dict(runtime.os.environ, {'DSIG_ENV':'PROD'}, clear=True),
            patch.object(runtime.server,'ADMIN_TOKEN',''),
            patch.object(runtime.server,'DB',runtime.preflight.DB),
        ):
            p.start()
            self.addCleanup(p.stop)
        for module, name in (
            (runtime.lifecycle,'termination_event'),
            (runtime.material,'load'),
            (runtime.preflight,'locked_local_preflight'),
            (runtime.contract,'verify'),
            (runtime.channel,'runtime_connection'),
            (runtime.transport,'recipient_exchange'),
            (runtime.lifecycle,'listener'),
            (runtime.lifecycle,'serve_until_stopped'),
        ):
            p=patch.object(module,name)
            setattr(self,name,p.start())
            self.addCleanup(p.stop)
        self.termination_event.return_value.__enter__.return_value=self.stop
        self.load.return_value=self.launch
        self.locked_local_preflight.return_value.__enter__.return_value={'status':'PASS'}
        self.verify.return_value={'status':'PASS'}
        self.recipient_exchange.return_value={'status':'PASS'}

    def test_listener_under_lock_after_handoff(self):
        lock=self.locked_local_preflight.return_value
        http=self.listener.return_value
        def serve(*args):
            lock.__exit__.assert_not_called()
            self.recipient_exchange.assert_called_once()
            self.assertEqual(self.verify.call_count,2)
            self.runtime_connection.return_value.__exit__.assert_called_once()
        self.serve_until_stopped.side_effect=serve
        def close(*args):
            lock.__exit__.assert_not_called()
        http.__exit__.side_effect=close
        runtime.run()
        self.listener.assert_called_once_with(('0.0.0.0',8080))
        lock.__exit__.assert_called_once()

    def test_bad_preflight(self):
        self.locked_local_preflight.return_value.__enter__.return_value={'status':'FAIL'}
        with self.assertRaises(ValueError):
            runtime.run()
        self.runtime_connection.assert_not_called()
        self.listener.assert_not_called()

    def test_bad_receipt(self):
        self.recipient_exchange.return_value={'status':'FAIL'}
        with self.assertRaises(ValueError):
            runtime.run()
        self.listener.assert_not_called()

    def test_expired_after_receipt(self):
        self.verify.side_effect=[{'status':'PASS'},{'status':'FAIL'}]
        with self.assertRaises(ValueError):
            runtime.run()
        self.listener.assert_not_called()

    def test_stop_before_handoff(self):
        self.stop.set()
        runtime.run()
        self.runtime_connection.assert_not_called()
        self.listener.assert_not_called()

    def test_bootstrap_rejected(self):
        with patch.dict(runtime.os.environ,{'DSIG_ADMIN_TOKEN':''}):
            with self.assertRaises(ValueError):
                runtime.run()
        self.load.assert_not_called()

    def test_handler_failure_releases_lock(self):
        self.serve_until_stopped.side_effect=RuntimeError('synthetic')
        with self.assertRaises(RuntimeError):
            runtime.run()
        self.listener.return_value.__exit__.assert_called_once()
        self.locked_local_preflight.return_value.__exit__.assert_called_once()


if __name__=='__main__':
    unittest.main()
