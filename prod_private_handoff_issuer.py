"""Host-only handoff issuer and process-local one-shot verifier.
Trusted callers must supply independently measured executable runtime bindings.
No Docker operations or HTTP startup occur here.
"""
import base64
import hashlib
import hmac
import json
import re
import threading
from datetime import datetime, timedelta, timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import prod_authorization as auth
import prod_private_runtime_contract as contract
import prod_private_runtime_replay as replay
import prod_private_launch_channel as channel

def issue(*, ledger_path, envelope, signing_key, authority_pin, expected, challenge_value):
    """Consume before signing; any subsequent failure burns the permit."""
    result=dict(status='FAIL',nonce_consumed=False,startup_authorized=False,
                production_authorized=False)
    try:
        if not isinstance(signing_key,Ed25519PrivateKey):
            return result
        if not isinstance(challenge_value,str) or not re.fullmatch('[0-9a-f]{64}',challenge_value):
            return result
        public=signing_key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        if not isinstance(authority_pin,str) or not hmac.compare_digest(hashlib.sha256(public).hexdigest(),authority_pin):
            return result
        envelope=json.loads(auth.canonical(envelope))
        expected=json.loads(auth.canonical(expected))
        if contract.verify(envelope,public,authority_pin=authority_pin,expected=expected)['status']!='PASS':
            return result
        reserved=replay.consume(ledger_path,envelope,public,authority_pin=authority_pin,expected=expected)
        if reserved['status']!='PASS' or reserved['nonce_consumed'] is not True:
            return result
        result['nonce_consumed']=True
        now=datetime.now(timezone.utc).replace(microsecond=0)
        expires=min(now+timedelta(seconds=60),auth.timestamp(envelope['payload']['expires_at']))
        if expires<=datetime.now(timezone.utc):
            return result
        payload=dict(purpose=channel.PURPOSE,challenge=challenge_value,
            contract_sha256=hashlib.sha256(auth.canonical(envelope)).hexdigest(),
            container_id=expected['container_id'],
            issued_at=now.strftime('%Y-%m-%dT%H:%M:%SZ'),
            expires_at=expires.strftime('%Y-%m-%dT%H:%M:%SZ'))
        receipt=dict(payload=payload,signature=base64.b64encode(signing_key.sign(auth.canonical(payload))).decode())
        if channel.verify(receipt,envelope,public,authority_pin=authority_pin,expected=expected,challenge_value=challenge_value)['status']!='PASS':
            return result
        result.update(status='PASS',receipt=receipt)
    except (ValueError,TypeError,KeyError,AttributeError,OSError,RuntimeError):
        pass
    return result

class Recipient:
    """One challenge per instance; the first verification attempt closes it."""
    def __init__(self):
        self._challenge=channel.challenge()
        self._closed=False
        self._lock=threading.Lock()

    @property
    def challenge(self):
        return self._challenge

    def accept(self,receipt,envelope,public,*,authority_pin,expected):
        with self._lock:
            if self._closed:
                return dict(status='FAIL',startup_authorized=False,production_authorized=False)
            self._closed=True
            return channel.verify(receipt,envelope,public,authority_pin=authority_pin,
                                  expected=expected,challenge_value=self._challenge)
