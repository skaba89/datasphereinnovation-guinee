import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from test_prod_private_runtime_contract import RuntimeContractTest
import prod_private_handoff_issuer as issuer

class HandoffIssuerTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ledger=Path(tmp.name)/'runtime.sqlite3'
        issuer.replay.initialize(self.ledger)
        self.fixture=RuntimeContractTest()
        self.fixture.setUp()
        self.envelope=self.fixture.envelope()
        self.recipient=issuer.Recipient()

    def issue(self,challenge=None):
        return issuer.issue(ledger_path=self.ledger,envelope=self.envelope,
            signing_key=self.fixture.key,authority_pin=self.fixture.pin,
            expected=self.fixture.expected,challenge_value=self.recipient.challenge if challenge is None else challenge)

    def accept(self,receipt):
        return self.recipient.accept(receipt,self.envelope,self.fixture.public,
            authority_pin=self.fixture.pin,expected=self.fixture.expected)

    def test_full_handoff(self):
        result=self.issue()
        self.assertEqual(result['status'],'PASS')
        self.assertTrue(result['nonce_consumed'])
        self.assertFalse(result['startup_authorized'])
        self.assertEqual(self.accept(result['receipt'])['status'],'PASS')
        self.assertEqual(self.accept(result['receipt'])['status'],'FAIL')
        self.assertEqual(self.issue()['status'],'FAIL')

    def test_invalid_challenge_does_not_consume(self):
        self.assertFalse(self.issue('invalid')['nonce_consumed'])
        self.assertEqual(self.issue()['status'],'PASS')

    def test_wrong_authority_does_not_consume(self):
        original=self.fixture.pin
        self.fixture.pin='0'*64
        self.assertFalse(self.issue()['nonce_consumed'])
        self.fixture.pin=original
        self.assertEqual(self.issue()['status'],'PASS')

    def test_invalid_receipt_closes_recipient(self):
        result=self.issue()
        self.assertEqual(self.accept({})['status'],'FAIL')
        self.assertEqual(self.accept(result['receipt'])['status'],'FAIL')

    def test_concurrent_issue(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:self.issue(),range(8)))
        self.assertEqual(sum(r['status']=='PASS' for r in results),1)

    def test_concurrent_accept(self):
        result=self.issue()
        self.assertEqual(result['status'],'PASS')
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:self.accept(result['receipt']),range(8)))
        self.assertEqual(sum(r['status']=='PASS' for r in results),1)

if __name__=='__main__':
    unittest.main()
