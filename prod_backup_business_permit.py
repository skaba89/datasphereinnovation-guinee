"""Independent, short-lived business backup permit. Never grants app deployment.

This is a preflight gate, not a backup producer or a scheduler.
"""
import base64
import hashlib
import hmac
import re
from datetime import datetime,timedelta,timezone
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
import prod_authorization as auth
import prod_backup_acquisition as acquisition
import prod_backup_review_signing as keys
import prod_backup_cadence as cadence
from prod_b2_cli import B2ReviewAdapter
from prod_b2_export import BUCKET
from cryptography.hazmat.primitives import serialization

PURPOSE='DSIG-PROD-BUSINESS-BACKUP-PERMIT-V1'
FIELDS={'purpose','schema','container_id','image_id','bucket_id','signer_pin','backup_key_id','slot','issued_at','expires_at'}
MAX_VALIDITY=timedelta(hours=3)

def verify(envelope,public,*,authority_pin,now):
    now=cadence.utc(now)
    if not isinstance(public,bytes) or len(public)!=32 or not isinstance(authority_pin,str) or not hmac.compare_digest(hashlib.sha256(public).hexdigest(),authority_pin):
        raise ValueError('untrusted backup authority')
    if not isinstance(envelope,dict) or set(envelope)!={'payload','signature'}:
        raise ValueError('invalid backup permit')
    p=envelope['payload']
    if not isinstance(p,dict) or set(p)!=FIELDS or p['purpose']!=PURPOSE or type(p['schema']) is not int or p['schema']!=1:
        raise ValueError('invalid permit domain')
    for name,pattern in (('container_id','[0-9a-f]{64}'),('image_id','sha256:[0-9a-f]{64}'),('bucket_id','[A-Za-z0-9_-]{8,128}'),('signer_pin','[0-9a-f]{64}'),('backup_key_id','[0-9a-f]{64}')):
        if not isinstance(p[name],str) or not re.fullmatch(pattern,p[name]):
            raise ValueError('invalid permit identity')
    if p['signer_pin']==authority_pin:
        raise ValueError('backup signer must differ from authority')
    issued,expires=auth.timestamp(p['issued_at']),auth.timestamp(p['expires_at'])
    if not issued<=now<expires or not timedelta(0)<expires-issued<=MAX_VALIDITY:
        raise ValueError('expired or invalid backup permit')
    slot=cadence.plan(now)
    if p['slot']!=slot['current_slot'] or slot['phase'] not in ('snapshot','export','audit'):
        raise ValueError('permit not valid in current slot')
    try:
        signature=base64.b64decode(envelope['signature'],validate=True)
        Ed25519PublicKey.from_public_bytes(public).verify(signature,auth.canonical(p))
    except (InvalidSignature,ValueError,TypeError):
        raise ValueError('invalid backup permit signature') from None
    return dict(p)

def preflight(envelope,authority_public,*,authority_pin,backup_path,signer_path,forbidden_backup_ids,expected_bucket_id):
    """Use real wall clock, pinned local Docker inspection and dedicated B2 session.

    Paths and trust pins must come from operator-controlled configuration.
    Does not open a database or write proof, archive or remote object.
    """
    now=datetime.now(timezone.utc)
    p=verify(envelope,authority_public,authority_pin=authority_pin,now=now)
    if p['bucket_id']!=expected_bucket_id:
        raise ValueError('unexpected business bucket')
    observation=acquisition.acquire(expected_container_id=p['container_id'],expected_image_id=p['image_id'])
    if observation['status']!='PASS' or observation['local_daemon_used'] is not True:
        raise ValueError('business source rejected')
    backup,signer=keys.load_keys(backup_path,signer_path,pinned_signer_id=p['signer_pin'],forbidden_backup_ids=forbidden_backup_ids)
    raw=base64.urlsafe_b64decode(backup)
    if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(),p['backup_key_id']):
        raise ValueError('backup key not bound to permit')
    B2ReviewAdapter(expected_bucket_id).bucket_info(BUCKET)
    confirmed = acquisition.acquire(expected_container_id=p['container_id'], expected_image_id=p['image_id'],
                                    expected_started_at=observation['source_started_at'])
    if confirmed['status'] != 'PASS' or confirmed['local_daemon_used'] is not True:
        raise ValueError('business source changed during preflight')
    verify(envelope,authority_public,authority_pin=authority_pin,now=datetime.now(timezone.utc))
    return dict(status='PASS',slot=p['slot'],source_started_at=observation['source_started_at'],source_preflight_verified=True,
                keys_preflight_verified=True,remote_policy_verified=True,
                business_backup_created=False,business_provenance_verified=False,
                production_authorized=False,execution_authorized=False)
