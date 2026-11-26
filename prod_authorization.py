"""Offline signed release evidence verification; never enables production."""
import base64
import binascii
import json
import re
from datetime import datetime, timezone, timedelta
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

FIELDS = {'schema', 'purpose', 'commit', 'image_digest', 'config_sha256',
          'evidence_sha256', 'issued_at', 'expires_at'}
PURPOSE = 'DSIG-PROD-ISOLATED-REVIEW'
MAX_VALIDITY = timedelta(hours=24)


def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


def timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z', value):
        raise ValueError('invalid timestamp')
    return datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)


def verify(envelope, public_key, *, commit, image_digest, config_sha256,
           evidence_sha256, now=None):
    """Caller must independently establish trusted key and expected digests."""
    checks = dict.fromkeys(('format', 'binding', 'validity', 'signature'), False)
    try:
        if not isinstance(envelope, dict) or set(envelope) != {'payload', 'signature'}:
            raise ValueError('invalid envelope')
        p = envelope['payload']
        if not isinstance(p, dict) or set(p) != FIELDS or type(p['schema']) is not int or p['schema'] != 1 or p['purpose'] != PURPOSE:
            raise ValueError('invalid payload')
        for name, pattern in (('commit', r'[0-9a-f]{40}'),
                              ('image_digest', r'sha256:[0-9a-f]{64}'),
                              ('config_sha256', r'[0-9a-f]{64}'),
                              ('evidence_sha256', r'[0-9a-f]{64}')):
            if not isinstance(p[name], str) or not re.fullmatch(pattern, p[name]):
                raise ValueError('invalid digest')
        issued, expires = timestamp(p['issued_at']), timestamp(p['expires_at'])
        signature = base64.b64decode(envelope['signature'], validate=True)
        if len(signature) != 64 or len(public_key) != 32:
            raise ValueError('invalid signature or key length')
        checks['format'] = True
        checks['binding'] = (p['commit'], p['image_digest'], p['config_sha256'],
                             p['evidence_sha256']) == (commit, image_digest,
                                                       config_sha256, evidence_sha256)
        current = now if now is not None else datetime.now(timezone.utc)
        checks['validity'] = issued <= current < expires and timedelta(0) < expires-issued <= MAX_VALIDITY
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, canonical(p))
        checks['signature'] = True
    except (ValueError, TypeError, KeyError, InvalidSignature, binascii.Error, OverflowError):
        pass
    return {'status': 'PASS' if all(checks.values()) else 'FAIL',
            'checks': {k: 'PASS' if v else 'FAIL' for k, v in checks.items()},
            'production_authorized': False}
