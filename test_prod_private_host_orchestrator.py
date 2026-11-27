import json
import unittest
from unittest.mock import MagicMock, patch
import prod_private_host_orchestrator as orch


class OrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.created = {'Id':'a'*64,'State':'created'}
        self.expected = {'container_id':'a'*64,
                         'runtime_sha256':orch.continuity.digest(self.created)}
        self.kw = dict(authority_path='/unused', approved_pin='b'*64,
                       approved_measurements=self.expected,
                       measurement_inputs={'container_id':'a'*64})
        self.start = MagicMock()
        self.stop = MagicMock()
        for module,name,value in (
            (orch.os,'geteuid',0),
            (orch.authority,'load',('key',b'public','ledger')),
            (orch.permit,'issue',{'status':'PASS','envelope':{}}),
            (orch.acquisition,'command',json.dumps(self.created)),
            (orch.handoff,'exchange',{'status':'PASS','nonce_consumed':True}),
        ):
            p=patch.object(module,name,return_value=value)
            setattr(self,name,p.start())
            self.addCleanup(p.stop)
        for module,name in ((orch.channel,'host_listener'),(orch,'published')):
            p=patch.object(module,name)
            setattr(self,name,p.start())
            self.addCleanup(p.stop)
        self.listener=self.host_listener.return_value.__enter__.return_value
        self.sock=MagicMock()
        self.listener.accept.return_value=(self.sock,None)

    def run_exchange(self):
        return orch.exchange_prepared(**self.kw,start_created=self.start,
                                      stop_failed=self.stop)

    def test_success_order(self):
        def start(cid):
            self.assertEqual(cid,'a'*64)
            self.published.return_value.__enter__.assert_called_once()
            self.host_listener.return_value.__enter__.assert_called_once()
            self.exchange.assert_not_called()
        self.start.side_effect=start
        result=self.run_exchange()
        self.assertEqual(result['status'],'PASS')
        self.assertFalse(result['production_authorized'])
        self.stop.assert_not_called()
        self.assertEqual(self.command.call_count,2)
        self.exchange.assert_called_once()
        self.published.return_value.__exit__.assert_called_once()

    def test_drift_prevents_start(self):
        self.command.return_value=json.dumps(dict(self.created,State='running'))
        with self.assertRaises(ValueError):
            self.run_exchange()
        self.start.assert_not_called()
        self.stop.assert_not_called()

    def test_failed_start_requests_cleanup(self):
        self.start.side_effect=RuntimeError('synthetic start failure')
        with self.assertRaises(RuntimeError):
            self.run_exchange()
        self.stop.assert_called_once_with('a'*64)

    def test_failed_handoff_requests_cleanup(self):
        self.exchange.return_value={'status':'FAIL','nonce_consumed':False}
        with self.assertRaises(ValueError):
            self.run_exchange()
        self.stop.assert_called_once_with('a'*64')
        self.published.return_value.__exit__.assert_called_once()

    def test_accept_timeout_requests_cleanup(self):
        self.listener.accept.side_effect=TimeoutError()
        with self.assertRaises(TimeoutError):
            self.run_exchange()
        self.stop.assert_called_once_with('a'*64)

    def test_no_start_when_publication_fails(self):
        self.published.return_value.__enter__.side_effect=FileExistsError()
        with self.assertRaises(FileExistsError):
            self.run_exchange()
        self.start.assert_not_called()
        self.stop.assert_not_called()

    def test_nonroot_refused(self):
        self.geteuid.return_value=10001
        with self.assertRaises(PermissionError):
            self.run_exchange()
        self.load.assert_not_called()
        self.start.assert_not_called()


if __name__=='__main__':
    unittest.main()
