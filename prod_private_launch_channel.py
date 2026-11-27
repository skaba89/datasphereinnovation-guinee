"""Cryptographic handoff primitive, not a production entrypoint.

The operator must provision the independent authority pin and establish a
trusted channel to the exact container. No server is started by this module.
"""
import hashlib
import hmac
import secrets
import base64
import re
from datetime import datetime, timezone, timedelta
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
import prod_authorization as auth
import prod_private_runtime_contract as contract

PURPOSE='DSIG-PROD-LAUNCH-HANDOFF-V1'

def challenge():
    return secrets.token_hex(32)

def verify(receipt, envelope, public, *, authority_pin, expected, challenge_value):
    """Validate a signed, short-lived receipt bound to the current challenge.

    The receipt issuer must independently verify durable nonce consumption.
    This verifier alone cannot prove that the issuer did so.
    """
    result=dict(status='FAIL',startup_authorized=False,production_authorized=False)
    try:
        if contract.verify(envelope,public,authority_pin=authority_pin,expected=expected)['status']!='PASS':
            return result
        if not isinstance(challenge_value,str) or not re.fullmatch('[0-9a-f]{64}',challenge_value):
            return result
        if not isinstance(receipt,dict) or set(receipt)!={'payload','signature'}:
            return result
        p=receipt['payload']
        if not isinstance(p,dict) or set(p)!={'purpose','challenge','contract_sha256','container_id','issued_at','expires_at'}:
            return result
        if (p['purpose']!=PURPOSE or not hmac.compare_digest(p['challenge'],challenge_value)
                or p['contract_sha256']!=hashlib.sha256(auth.canonical(envelope)).hexdigest()
                or p['container_id']!=expected['container_id']):
            return result
        issued,expires=auth.timestamp(p['issued_at']),auth.timestamp(p['expires_at'])
        if not (issued<=datetime.now(timezone.utc)<expires
                and timedelta(0)<expires-issued<=timedelta(seconds=60)
                and expires<=auth.timestamp(envelope['payload']['expires_at'])):
            return result
        signature=base64.b64decode(receipt['signature'],validate=True)
        Ed25519PublicKey.from_public_bytes(public).verify(signature,auth.canonical(p))
        result['status']='PASS'
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,InvalidSignature,RecursionError):
        pass
    return result
