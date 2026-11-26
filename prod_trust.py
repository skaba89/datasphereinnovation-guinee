"""Offline pinned trust registry for production review signatures; never enables PROD."""
import base64
import hashlib
import hmac
import json
import re
from datetime import datetime, timezone

import prod_authorization as authorization

MAX_REGISTRY_BYTES = 65536
KEY_FIELDS = {'id', 'public_key', 'not_before', 'not_after', 'revoked'}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON field')
        result[key] = value
    return result


def verify(envelope, registry_bytes, pinned_sha256, *, now=None, **expected):
    checks = dict.fromkeys(('registry_pin', 'registry_format', 'signer_trusted',
                            'signer_validity', 'release_signature'), False)
    try:
        if (not isinstance(registry_bytes, bytes) or len(registry_bytes) > MAX_REGISTRY_BYTES
                or not isinstance(pinned_sha256, str)
                or not re.fullmatch(r'[0-9a-f]{64}', pinned_sha256)
                or not hmac.compare_digest(hashlib.sha256(registry_bytes).hexdigest(), pinned_sha256)):
            raise ValueError('invalid registry pin')
        checks['registry_pin'] = True
        registry = json.loads(registry_bytes.decode('utf-8'), object_pairs_hook=unique_object)
        if (not isinstance(registry, dict) or set(registry) != {'schema', 'keys'}
                or type(registry['schema']) is not int or registry['schema'] != 1
                or not isinstance(registry['keys'], list) or not 1 <= len(registry['keys']) <= 64):
            raise ValueError('invalid registry')
        keys = {}
        for item in registry['keys']:
            if not isinstance(item, dict) or set(item) != KEY_FIELDS or type(item['revoked']) is not bool:
                raise ValueError('invalid signer')
            raw = base64.b64decode(item['public_key'], validate=True)
            key_id = hashlib.sha256(raw).hexdigest()
            if len(raw) != 32 or item['id'] != key_id or key_id in keys:
                raise ValueError('invalid signer identity')
            start = authorization.timestamp(item['not_before'])
            end = authorization.timestamp(item['not_after'])
            if not start < end:
                raise ValueError('invalid signer period')
            keys[key_id] = (raw, start, end, item['revoked'])
        checks['registry_format'] = True
        if not isinstance(envelope, dict) or set(envelope) != {'key_id', 'payload', 'signature'}:
            raise ValueError('invalid signed envelope')
        raw, start, end, revoked = keys[envelope['key_id']]
        if revoked:
            raise ValueError('revoked signer')
        checks['signer_trusted'] = True
        current = datetime.now(timezone.utc) if now is None else now
        issued = authorization.timestamp(envelope['payload']['issued_at'])
        expires = authorization.timestamp(envelope['payload']['expires_at'])
        checks['signer_validity'] = start <= issued <= current < expires <= end
        report = authorization.verify(
            {'payload': envelope['payload'], 'signature': envelope['signature']},
            raw, now=current, **expected)
        checks['release_signature'] = report['status'] == 'PASS'
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError):
        pass
    return {'status': 'PASS' if all(checks.values()) else 'FAIL',
            'checks': {k: 'PASS' if v else 'FAIL' for k, v in checks.items()},
            'production_authorized': False}
