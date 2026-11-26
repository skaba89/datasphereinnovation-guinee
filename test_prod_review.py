import base64
import hashlib
import json
import secrets
import tempfile
import unittest
from pathlib import Path

from cryptography.fernet import Fernet
import prod_authorization
import prod_config
import prod_review as p
import prod_replay
import test_prod_trust
import test_prod_compose


def keys(reference=True):
    return dict(**({'DSIG_ADMIN_TOKEN':secrets.token_urlsafe(48)} if reference else {}),
                **{k:Fernet.generate_key().decode() for k in prod_config.KEYS})


class CombinedReviewTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ledger = Path(tmp.name)/'review.sqlite'
        prod_replay.initialize(self.ledger)
        self.trust = test_prod_trust.ProdTrustTests()
        self.trust.setUp()
        self.compose = test_prod_compose.fixture()
        self.compose['services']['app']['environment'].update(keys(reference=False))
        self.rec = dict(DSIG_ENV='REC', DSIG_HTTPS_ORIGIN='https://rec.dsig-consulting.com', **keys())
        self.candidate = dict(DSIG_ENV='REC', DSIG_HTTPS_ORIGIN='https://candidate.invalid', **keys())
        self.commit = 'a'*40
        self.evidence = dict(commit=self.commit, gates={g:dict(status='PASS', reviewer='synthetic', evidence='synthetic') for g in p.GATES})
        self.registry = json.dumps(self.trust.registry).encode()
        self.args = dict(compose_bytes=json.dumps(self.compose).encode(),
                         evidence_bytes=json.dumps(self.evidence).encode(), rec=self.rec,
                         candidate=self.candidate, registry_bytes=self.registry,
                         pinned_sha256=p.digest(self.registry), expected_commit=self.commit,
                         expected_image=test_prod_compose.IMAGE, expected_port=8320,
                         ledger_path=self.ledger, now=self.trust.now)
        payload = self.trust.payload.copy()
        payload.update(commit=self.commit, image_digest=self.args['expected_image'].rsplit('@',1)[1],
                       config_sha256=p.digest(self.args['compose_bytes']),
                       evidence_sha256=p.digest(self.args['evidence_bytes']))
        self.args['envelope'] = dict(key_id=self.trust.item['id'], payload=payload,
                                     signature=base64.b64encode(self.trust.key.sign(prod_authorization.canonical(payload))).decode())

    def review(self, **overrides):
        result = p.review(**dict(self.args, **overrides))
        self.assertFalse(result['production_authorized'])
        self.assertNotIn(self.rec['DSIG_ADMIN_TOKEN'], str(result))
        return result

    def test_complete_and_replay(self):
        self.assertEqual(self.review()['status'],'PASS')
        self.assertEqual(self.review()['checks']['single_use'],'FAIL')

    def test_invalid_topology_does_not_consume(self):
        self.compose['services']['app']['privileged']=True
        self.assertEqual(self.review(compose_bytes=json.dumps(self.compose).encode())['checks']['topology'],'FAIL')
        self.assertEqual(self.review()['status'],'PASS')

    def test_incomplete_gates_does_not_consume(self):
        self.evidence['gates']['G10']['status']='NOT_RUN'
        self.assertEqual(self.review(evidence_bytes=json.dumps(self.evidence).encode())['checks']['evidence_completeness'],'FAIL')
        self.assertEqual(self.review()['status'],'PASS')

    def test_modified_evidence_bytes(self):
        self.assertEqual(self.review(evidence_bytes=self.args['evidence_bytes']+b' ')['checks']['signed_binding'],'FAIL')
        self.assertEqual(self.review()['status'],'PASS')

    def test_modified_config_bytes(self):
        self.assertEqual(self.review(compose_bytes=self.args['compose_bytes']+b' ')['checks']['signed_binding'],'FAIL')
        self.assertEqual(self.review()['status'],'PASS')

    def test_reused_secret(self):
        self.rec['DSIG_MFA_KEY']=self.compose['services']['app']['environment']['DSIG_MFA_KEY']
        self.assertEqual(self.review()['checks']['configuration'],'FAIL')

    def test_duplicate_json(self):
        self.assertEqual(self.review(compose_bytes=b'{"name":"a","name":"b"}')['checks']['input'],'FAIL')
