import os
import socket
import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from test_prod_private_runtime_contract import RuntimeContractTest
import prod_private_handoff_transport as transport
import prod_private_qualification_entrypoint as entry

@unittest.skipUnless(hasattr(socket,'SO_PEERCRED'),'Linux peer credentials required')
class QualificationEntrypointTest(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ledger=Path(tmp.name)/'runtime.sqlite3'
        transport.issuer.replay.initialize(self.ledger)
        self.fixture=RuntimeContractTest()
        self.fixture.setUp()
        self.envelope=self.fixture.envelope()

    def host(self,sock):
        return transport.host_exchange(sock,expected_uid=os.getuid(),ledger_path=self.ledger,
            envelope=self.envelope,signing_key=self.fixture.key,authority_pin=self.fixture.pin,
            expected=self.fixture.expected)

    def prepare(self,sock):
        return entry.prepare(sock,expected_uid=os.getuid(),envelope=self.envelope,
            public=self.fixture.public,authority_pin=self.fixture.pin,expected=self.fixture.expected)

    def test_handoff_to_real_http(self):
        a,b=socket.socketpair()
        with patch.dict(os.environ,{'DSIG_ENV':'DEV'}), ThreadPoolExecutor(max_workers=1) as pool:
            host=pool.submit(self.host,a)
            http=self.prepare(b)
            self.addCleanup(http.server_close)
            self.assertEqual(host.result(timeout=15)['status'],'PASS')
        thread=threading.Thread(target=http.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(thread.join,5)
        self.addCleanup(http.shutdown)
        base='http://127.0.0.1:'+str(http.server_port)
        with urllib.request.urlopen(base+'/api/ready',timeout=3) as response:
            self.assertTrue(json.load(response)['qualification_only'])
        with self.assertRaises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(base+'/api/admin/accounts',timeout=3)
        self.assertEqual(exc.exception.code,404)
        a,b=socket.socketpair()
        with patch.dict(os.environ,{'DSIG_ENV':'DEV'}), ThreadPoolExecutor(max_workers=1) as pool:
            host=pool.submit(self.host,a)
            with patch.object(entry,'create_isolated') as create:
                with self.assertRaises(ValueError):
                    self.prepare(b)
                create.assert_not_called()
            self.assertEqual(host.result(timeout=15)['status'],'FAIL')

    def test_production_refused_before_exchange(self):
        for mode in ('PROD','REC',''):
            a,b=socket.socketpair()
            with a,patch.dict(os.environ,{'DSIG_ENV':mode}),patch.object(entry,'recipient_exchange') as exchange:
                with self.assertRaises(ValueError):
                    self.prepare(b)
                exchange.assert_not_called()

if __name__=='__main__':
    unittest.main()
