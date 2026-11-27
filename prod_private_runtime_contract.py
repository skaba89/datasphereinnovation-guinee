"""V2 private runtime contract verification; not a startup capability."""
import base64
import hashlib
import hmac
import re
from datetime import datetime, timedelta, timezone
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
import prod_authorization as auth

PURPOSE='DSIG-PROD-PRIVATE-RUNTIME-V2'
SCOPE='loopback-private-no-commercial-access'
PATTERNS={
    'commit':r'[0-9a-f]{40}',
    'image_digest':r'sha256:[0-9a-f]{64}',
    'image_id':r'sha256:[0-9a-f]{64}',
    'container_id':r'[0-9a-f]{64}',
    'config_sha256':r'[0-9a-f]{64}',
    'runtime_sha256':r'[0-9a-f]{64}',
    'evidence_sha256':r'[0-9a-f]{64}',
    'volume_identity_sha256':r'[0-9a-f]{64}',
    'host_identity_sha256':r'[0-9a-f]{64}',
}
FIELDS=set(PATTERNS)|{'schema','purpose','scope','nonce','issued_at','expires_at'}
MAX_VALIDITY=timedelta(minutes=10)

def verify(envelope, public, *, authority_pin, expected):
    """Expected bindings must be measured independently, not copied from payload.
    Uses real UTC clock. Does not consume nonce or authorize startup.
    """
    checks=dict.fromkeys(('authority','format','binding','validity','signature'),False)
    try:
        if (not isinstance(public,bytes) or len(public)!=32
                or not isinstance(authority_pin,str)
                or not hmac.compare_digest(hashlib.sha256(public).hexdigest(),authority_pin)):
            raise ValueError()
        checks['authority']=True
        if not isinstance(envelope,dict) or set(envelope)!={'payload','signature'}:
            raise ValueError()
        p=envelope['payload']
        if (not isinstance(p,dict) or set(p)!=FIELDS or type(p['schema']) is not int
                or p['schema']!=2 or p['purpose']!=PURPOSE or p['scope']!=SCOPE):
            raise ValueError()
        if not isinstance(expected,dict) or set(expected)!=set(PATTERNS):
            raise ValueError()
        for name,pattern in dict(PATTERNS,nonce=r'[0-9a-f]{64}').items():
            if not isinstance(p[name],str) or not re.fullmatch(pattern,p[name]):
                raise ValueError()
        checks['format']=True
        checks['binding']=all(p[k]==expected[k] for k in PATTERNS)
        issued,expires=auth.timestamp(p['issued_at']),auth.timestamp(p['expires_at'])
        checks['validity']=issued<=datetime.now(timezone.utc)<expires and timedelta(0)<expires-issued<=MAX_VALIDITY
        signature=base64.b64decode(envelope['signature'],validate=True)
        if len(signature)!=64:
            raise ValueError()
        Ed25519PublicKey.from_public_bytes(public).verify(signature,auth.canonical(p))
        checks['signature']=True
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,InvalidSignature,RecursionError):
        pass
    return dict(status='PASS' if all(checks.values()) else 'FAIL',checks=checks,
                nonce_consumed=False,startup_authorized=False,production_authorized=False)
