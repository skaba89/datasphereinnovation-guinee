import base64
import json
import os
import tempfile
import unittest
from pathlib import Path

import prod_authorization
import prod_checkpoint
import prod_operator
import test_prod_review


class OperatorReviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_prod_review.CombinedReviewTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory=Path(tmp.name)
        f=self.fixture
        payload=dict(schema=1,purpose=prod_checkpoint.PURPOSE,sequence=1,
                     registry_sha256=f.args['pinned_sha256'],
                     ledger_sha256=prod_checkpoint.ledger_digest(f.ledger),
                     issued_at='2026-11-26T06:00:00Z',expires_at='2026-11-26T07:00:00Z')
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        key=Ed25519PrivateKey.generate()
        checkpoint=dict(payload=payload,signature=base64.b64encode(
            key.sign(prod_authorization.canonical(payload))).decode())
        files={'compose.json':f.args['compose_bytes'],'evidence.json':f.args['evidence_bytes'],
               'registry.json':f.registry,'rec.json':json.dumps(f.rec).encode(),
               'candidate.json':json.dumps(f.candidate).encode(),
               'envelope.json':json.dumps(f.args['envelope']).encode(),
               'checkpoint.json':json.dumps(checkpoint).encode()}
        for name,data in files.items():
            path=self.directory/name
            path.write_bytes(data)
            path.chmod(0o600)
        self.args=dict(expected_commit=f.commit,expected_image=f.args['expected_image'],
                       expected_port=8320,pinned_sha256=f.args['pinned_sha256'],
                       anchor_public_key=key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw),
                       expected_sequence=1,ledger_path=f.ledger,now=f.trust.now)

    def test_dry_run_no_consumption(self):
        before=prod_checkpoint.ledger_digest(self.fixture.ledger)
        for _ in range(2):
            result=prod_operator.inspect_bundle(self.directory,**self.args)
            self.assertEqual(result['status'],'PASS')
            self.assertFalse(result['authorization_consumed'])
            self.assertFalse(result['production_authorized'])
        self.assertEqual(before,prod_checkpoint.ledger_digest(self.fixture.ledger))
        self.assertEqual(self.fixture.review()['status'],'PASS')

    def test_unsafe_permissions(self):
        (self.directory/'rec.json').chmod(0o644)
        self.assertEqual(prod_operator.inspect_bundle(self.directory,**self.args)['status'],'FAIL')

    def test_symlink(self):
        path=self.directory/'rec.json'
        path.rename(self.directory/'other')
        path.symlink_to(self.directory/'other')
        self.assertEqual(prod_operator.inspect_bundle(self.directory,**self.args)['status'],'FAIL')

    def test_old_sequence(self):
        self.args['expected_sequence']=2
        self.assertEqual(prod_operator.inspect_bundle(self.directory,**self.args)['checks']['checkpoint'],'FAIL')

    def test_missing_file(self):
        (self.directory/'evidence.json').unlink()
        self.assertEqual(prod_operator.inspect_bundle(self.directory,**self.args)['status'],'FAIL')
