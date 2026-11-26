"""Authenticate daily backup claims and verify actual remote bytes.

The pinned public key must be provisioned independently by the operator.
No production authorization, automatic signing, or remote writes.
"""
import base64
import hashlib
import hmac
import re
from datetime import datetime, timezone
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
import prod_authorization
import prod_backup_monitor
import prod_b2_export

PURPOSE='DSIG-PROD-DAILY-BACKUP-V1'


def verify(envelope, public_key, *, pinned_key_id, expected_bucket_id, remote, backup_key, now=None):
    checks=dict.fromkeys(('key_pin','signature','daily_claim','remote_policy','remote_digest','restore'),'NOT_RUN')
    try:
        checks['key_pin']='FAIL'
        if (not isinstance(public_key,bytes) or len(public_key)!=32
                or not isinstance(pinned_key_id,str) or not re.fullmatch(r'[0-9a-f]{64}',pinned_key_id)
                or not hmac.compare_digest(hashlib.sha256(public_key).hexdigest(),pinned_key_id)):
            raise ValueError('untrusted backup signer')
        checks['key_pin']='PASS'
        checks['signature']='FAIL'
        if not isinstance(envelope,dict) or set(envelope)!={'purpose','key_id','proof','signature'}:
            raise ValueError('invalid envelope')
        if envelope['purpose']!=PURPOSE or envelope['key_id']!=pinned_key_id:
            raise ValueError('invalid signature domain')
        if not isinstance(envelope['proof'],dict) or set(envelope['proof'])!=prod_backup_monitor.FIELDS:
            raise ValueError('invalid proof')
        signature=base64.b64decode(envelope['signature'],validate=True)
        if len(signature)!=64:
            raise ValueError('invalid signature')
        payload={k:envelope[k] for k in ('purpose','key_id','proof')}
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature,prod_authorization.canonical(payload))
        checks['signature']='PASS'
        checks['daily_claim']='FAIL'
        proof=envelope['proof']
        current=now if now is not None else datetime.now(timezone.utc)
        if prod_backup_monitor.evaluate(proof,expected_bucket_id=expected_bucket_id,now=current)['status']!='PASS':
            raise ValueError('invalid daily claim')
        checks['daily_claim']='PASS'
        checks['remote_policy']='FAIL'
        b=remote.bucket_info(prod_b2_export.BUCKET)
        if (b.get('bucketName')!=prod_b2_export.BUCKET or b.get('bucketId')!=expected_bucket_id
                or b.get('bucketType')!='allPrivate' or b.get('encryption')!='SSE-B2'
                or b.get('lock_mode')!='compliance' or type(b.get('lock_days')) is not int or b['lock_days']<30):
            raise ValueError('invalid bucket policy')
        checks['remote_policy']='PASS'
        checks['remote_digest']='FAIL'
        data=remote.read(prod_b2_export.BUCKET,proof['object'])
        if (not isinstance(data,bytes) or not 0<len(data)<=128*1024*1024
                or not hmac.compare_digest(hashlib.sha256(data).hexdigest(),proof['sha256'])):
            raise ValueError('remote digest mismatch')
        checks['remote_digest']='PASS'
        checks['restore']='FAIL'
        prod_b2_export.verify_archive(data,backup_key)
        checks['restore']='PASS'
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,InvalidSignature,OSError,RecursionError):
        pass
    return {'status':'PASS' if all(v=='PASS' for v in checks.values()) else 'FAIL',
            'checks':checks,'evidence_authenticated':checks['signature']=='PASS',
            'remote_verified':checks['remote_digest']=='PASS' and checks['restore']=='PASS',
            'production_authorized':False}
