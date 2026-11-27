"""Host-side permit signing. No automatic approval, startup or key generation."""
import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import prod_authorization as auth
import prod_private_runtime_contract as contract
import prod_private_executable_supervisor as supervisor

def issue(*, signing_key, authority_pin, approved_measurements, measurement_inputs):
    """Trusted operator must approve exact measurements independently.
    Signing alone does not consume the nonce; host handoff does that atomically.
    Never log the private key or raw configuration.
    """
    result=dict(status='FAIL',nonce_consumed=False,startup_authorized=False,
                production_authorized=False)
    try:
        if not isinstance(signing_key,Ed25519PrivateKey):
            return result
        public=signing_key.public_key().public_bytes(serialization.Encoding.Raw,
            serialization.PublicFormat.Raw)
        if not isinstance(authority_pin,str) or not hmac.compare_digest(
                hashlib.sha256(public).hexdigest(),authority_pin):
            return result
        approved=dict(approved_measurements)
        if set(approved)!=set(contract.PATTERNS):
            return result
        measured=supervisor.inspect(**measurement_inputs)
        if (measured['status']!='PASS' or measured['domain']!=supervisor.DOMAIN
                or measured['runtime_measurements']!=approved):
            return result
        now=datetime.now(timezone.utc).replace(microsecond=0)
        payload=dict(approved,schema=2,purpose=contract.PURPOSE,scope=contract.SCOPE,
            nonce=secrets.token_hex(32),issued_at=now.strftime('%Y-%m-%dT%H:%M:%SZ'),
            expires_at=(now+timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M:%SZ'))
        envelope=dict(payload=payload,
            signature=base64.b64encode(signing_key.sign(auth.canonical(payload))).decode('ascii'))
        if contract.verify(envelope,public,authority_pin=authority_pin,expected=approved)['status']!='PASS':
            return result
        result.update(status='PASS',envelope=envelope)
    except (ValueError,TypeError,KeyError,AttributeError,OSError,RuntimeError):
        pass
    return result
