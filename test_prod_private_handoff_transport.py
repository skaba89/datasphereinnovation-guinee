import os
import socket
import struct
import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from test_prod_private_runtime_contract import RuntimeContractTest
import prod_private_handoff_transport as transport

@unittest.skipUnless(hasattr(socket,'SO_PEERCRED'),'Linux peer credentials required')
class HandoffTransportTest(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ledger=Path(tmp.name)/'runtime.sqlite3'
        transport.issuer.replay.initialize(self.ledger)
        self.fixture=RuntimeContractTest()
        self.fixture.setUp()
        self.envelope=self.fixture.envelope()

    def host(self,sock,uid=None):
        return transport.host_exchange(sock,expected_uid=os.getuid() if uid is None else uid,
            ledger_path=self.ledger,envelope=self.envelope,signing_key=self.fixture.key,
            authority_pin=self.fixture.pin,expected=self.fixture.expected)

    def recipient(self,sock):
        return transport.recipient_exchange(sock,expected_uid=os.getuid(),
            envelope=self.envelope,public=self.fixture.public,
            authority_pin=self.fixture.pin,expected=self.fixture.expected)

    def exchange(self):
        a,b=socket.socketpair()
        with ThreadPoolExecutor(max_workers=2) as pool:
            h=pool.submit(self.host,a)
            c=pool.submit(self.recipient,b)
            return h.result(timeout=15),c.result(timeout=15)

    def test_real_exchange_and_replay(self):
        host,client=self.exchange()
        self.assertEqual(host['status'],'PASS')
        self.assertTrue(host['nonce_consumed'])
        self.assertEqual(client['status'],'PASS')
        self.assertFalse(client['startup_authorized'])
        host,client=self.exchange()
        self.assertEqual(host['status'],'FAIL')
        self.assertEqual(client['status'],'FAIL')

    def test_wrong_uid(self):
        a,b=socket.socketpair()
        with b:
            self.assertEqual(self.host(a,os.getuid()+1)['status'],'FAIL')
        self.assertEqual(self.exchange()[0]['status'],'PASS')

    def test_oversized_frame(self):
        a,b=socket.socketpair()
        with b:
            b.sendall(struct.pack('!I',transport.MAX_FRAME+1))
            self.assertEqual(self.host(a)['status'],'FAIL')
        self.assertEqual(self.exchange()[0]['status'],'PASS')

    def test_duplicate_keys(self):
        a,b=socket.socketpair()
        with b:
            raw=b'{"challenge":"a","challenge":"b"}'
            b.sendall(struct.pack('!I',len(raw))+raw)
            self.assertEqual(self.host(a)['status'],'FAIL')

    def test_truncated_frame(self):
        a,b=socket.socketpair()
        b.sendall(struct.pack('!I',100)+b'{}')
        b.close()
        self.assertEqual(self.host(a)['status'],'FAIL')

if __name__=='__main__':
    unittest.main()
