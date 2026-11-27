"""Private production release authorization, separate from isolated review.

Pure verification only: the host must independently measure the image and
configuration and provision the trust pin. Never opens a DB or starts a server.
"""
import base64
import hashlib
import hmac
import re
from datetime import datetime, timezone, timedelta
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
import prod_authorization as auth

PURPOSE = 'DSIG-PROD-PRIVATE-START-V1'
FIELDS = auth.FIELDS | {'nonce', 'scope'}
SCOPE = 'loopback-private-no-commercial-access'

def verify(envelope, public, *, authority_pin, commit, image_digest,
           config_sha256, evidence_sha256, now=None):
    checks = dict.fromkeys(('authority', 'format', 'binding', 'validity', 'signature'), False)
    try:
        if (not isinstance(public, bytes) or len(public) != 32
                or not isinstance(authority_pin, str)
                or not hmac.compare_digest(hashlib.sha256(public).hexdigest(), authority_pin)):
            raise ValueError('untrusted authority')
        checks['authority'] = True
        if not isinstance(envelope, dict) or set(envelope) != {'payload', 'signature'}:
            raise ValueError('invalid envelope')
        p = envelope['payload']
        if (not isinstance(p, dict) or set(p) != FIELDS or type(p['schema']) is not int
                or p['schema'] != 1 or p['purpose'] != PURPOSE or p['scope'] != SCOPE):
            raise ValueError('invalid private release domain')
        for name, pattern in (('commit', '[0-9a-f]{40}'), ('image_digest', 'sha256:[0-9a-f]{64}'),
                              ('config_sha256', '[0-9a-f]{64}'), ('evidence_sha256', '[0-9a-f]{64}'),
                              ('nonce', '[0-9a-f]{64}')):
            if not isinstance(p[name], str) or not re.fullmatch(pattern, p[name]):
                raise ValueError('invalid binding')
        checks['format'] = True
        checks['binding'] = (p['commit'], p['image_digest'], p['config_sha256'], p['evidence_sha256']) == (commit, image_digest, config_sha256, evidence_sha256)
        current = datetime.now(timezone.utc) if now is None else now
        if current.utcoffset() != timedelta(0):
            raise ValueError('UTC required')
        issued, expires = auth.timestamp(p['issued_at']), auth.timestamp(p['expires_at'])
        checks['validity'] = issued <= current < expires and timedelta(0) < expires-issued <= timedelta(hours=1)
        signature = base64.b64decode(envelope['signature'], validate=True)
        Ed25519PublicKey.from_public_bytes(public).verify(signature, auth.canonical(p))
        checks['signature'] = True
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, InvalidSignature, RecursionError):
        pass
    return {'status': 'PASS' if all(checks.values()) else 'FAIL',
            'checks': checks, 'production_authorized': False, 'startup_authorized': False}
