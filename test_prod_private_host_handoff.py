import unittest
from unittest.mock import MagicMock, patch
import prod_private_host_handoff as bridge


class HostHandoffTests(unittest.TestCase):
    def setUp(self):
        self.sock = MagicMock()
        self.expected = dict(container_id='a'*64, image_id='sha256:'+'b'*64, runtime_sha256='d'*64)
        self.kw = dict(authority_path='/unused', approved_pin='c'*64,
                       approved_measurements=self.expected, envelope={}, created_observation={'Id':'a'*64})
        for module, name, value in (
            (bridge.os, 'geteuid', 0),
            (bridge.authority, 'load', ('key', b'public', 'ledger')),
            (bridge.contract, 'verify', dict(status='PASS')),
            (bridge.continuity, 'inspect', dict(status='PASS')),
            (bridge.binding, 'inspect', dict(status='PASS')),
            (bridge.transport, 'host_exchange', dict(status='PASS', nonce_consumed=True,
                startup_authorized=False, production_authorized=False)),
        ):
            p = patch.object(module, name, return_value=value)
            setattr(self, 'continuity_check' if module is bridge.continuity else name, p.start())
            self.addCleanup(p.stop)

    def test_peer_refused_before_consumption(self):
        self.inspect.return_value = dict(status='FAIL')
        self.assertEqual(bridge.exchange(self.sock, **self.kw)['status'], 'FAIL')
        self.host_exchange.assert_not_called()
        self.sock.close.assert_called_once()

    def test_signature_refused_before_peer(self):
        self.verify.return_value = dict(status='FAIL')
        self.assertEqual(bridge.exchange(self.sock, **self.kw)['status'], 'FAIL')
        self.inspect.assert_not_called()
        self.host_exchange.assert_not_called()

    def test_nonroot_refused(self):
        self.geteuid.return_value = 10001
        self.assertEqual(bridge.exchange(self.sock, **self.kw)['status'], 'FAIL')
        self.load.assert_not_called()

    def test_independent_pin_and_peer_forwarded(self):
        report = bridge.exchange(self.sock, **self.kw)
        self.assertEqual(report['status'], 'PASS')
        self.assertFalse(report['production_authorized'])
        self.load.assert_called_once_with('/unused', approved_pin='c'*64)
        self.assertEqual(self.continuity_check.call_count, 2)
        self.continuity_check.assert_called_with(created={'Id':'a'*64},
            approved_digest='d'*64, container_id='a'*64)
        self.inspect.assert_called_once_with(self.sock, container_id='a'*64,
            image_id='sha256:'+'b'*64, expected_uid=10001)
        self.assertEqual(self.host_exchange.call_args.kwargs['expected'], self.expected)
        self.assertEqual(self.host_exchange.call_args.kwargs['ledger_path'], 'ledger')

    def test_continuity_refused_before_peer(self):
        self.continuity_check.return_value = dict(status='FAIL')
        self.assertEqual(bridge.exchange(self.sock, **self.kw)['status'], 'FAIL')
        self.inspect.assert_not_called()
        self.host_exchange.assert_not_called()

    def test_continuity_changed_after_peer(self):
        self.continuity_check.side_effect = [dict(status='PASS'), dict(status='FAIL')]
        self.assertEqual(bridge.exchange(self.sock, **self.kw)['status'], 'FAIL')
        self.inspect.assert_called_once()
        self.host_exchange.assert_not_called()

    def test_missing_authority_refused(self):
        self.load.side_effect = FileNotFoundError()
        self.assertEqual(bridge.exchange(self.sock, **self.kw)['status'], 'FAIL')
        self.host_exchange.assert_not_called()


if __name__ == '__main__':
    unittest.main()
