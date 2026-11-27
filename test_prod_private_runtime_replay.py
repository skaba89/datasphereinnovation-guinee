import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from test_prod_private_runtime_contract import RuntimeContractTest
import prod_private_runtime_replay as replay

class RuntimeReplayTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/'runtime.sqlite3'
        self.fixture=RuntimeContractTest()
        self.fixture.setUp()
        self.envelope=self.fixture.envelope()

    def consume(self):
        return replay.consume(self.path,self.envelope,self.fixture.public,
            authority_pin=self.fixture.pin,expected=self.fixture.expected)

    def test_missing_ledger_not_created(self):
        self.assertEqual(self.consume()['status'],'FAIL')
        self.assertFalse(self.path.exists())

    def test_durable_single_use(self):
        replay.initialize(self.path)
        result=self.consume()
        self.assertEqual(result['status'],'PASS')
        self.assertTrue(result['nonce_consumed'])
        self.assertFalse(result['startup_authorized'])
        self.assertEqual(self.consume()['status'],'FAIL')
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT nonce,container_id FROM runtime_consumed').fetchall(),
                [(self.fixture.payload['nonce'],self.fixture.expected['container_id'])])

    def test_concurrent_consumption(self):
        replay.initialize(self.path)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:self.consume(),range(8)))
        self.assertEqual(sum(r['nonce_consumed'] for r in results),1)

    def test_invalid_signature_does_not_burn_nonce(self):
        replay.initialize(self.path)
        original=self.envelope['signature']
        self.envelope['signature']='invalid'
        self.assertEqual(self.consume()['status'],'FAIL')
        self.envelope['signature']=original
        self.assertEqual(self.consume()['status'],'PASS')

    def test_insecure_permissions(self):
        replay.initialize(self.path)
        os.chmod(self.path,0o644)
        self.assertEqual(self.consume()['status'],'FAIL')

    def test_no_reset(self):
        replay.initialize(self.path)
        self.assertEqual(self.consume()['status'],'PASS')
        with self.assertRaises(FileExistsError):
            replay.initialize(self.path)
        self.assertEqual(self.consume()['status'],'FAIL')

    def test_v1_ledger_rejected(self):
        import prod_private_replay
        prod_private_replay.initialize(self.path)
        self.assertEqual(self.consume()['status'],'FAIL')

if __name__=='__main__':
    unittest.main()
