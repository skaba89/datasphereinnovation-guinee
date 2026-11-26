"""External checkpoint for a completed qualification cycle, never business evidence."""
import base64
import hashlib
import hmac
import re
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
import prod_authorization as auth
import prod_backup_cycle_journal as journal
import prod_backup_orchestrator as guard
import prod_backup_remote_qualification as qualification
from prod_b2_export import BUCKET

PURPOSE='DSIG-QUALIFICATION-ANCHOR-V1'


def object_name(run_id):
    if not isinstance(run_id,str) or not re.fullmatch(r'[0-9a-f]{32}',run_id):
        raise ValueError('invalid qualification id')
    return f'prod/qualification/v232/{run_id}/journal-anchor.json'


def policy_check(remote,bucket_id):
    p=remote.bucket_info(BUCKET)
    if (p.get('bucketName')!=BUCKET or p.get('bucketId')!=bucket_id
            or p.get('bucketType')!='allPrivate' or p.get('encryption')!='SSE-B2'
            or p.get('lock_mode')!='compliance' or type(p.get('lock_days')) is not int or p['lock_days']<30):
        raise ValueError('invalid anchor policy')


def verify(*, state, now, public, pin, run_id, bucket_id, remote):
    import json
    obj=object_name(run_id)
    policy_check(remote,bucket_id)
    raw=remote.read(BUCKET,obj)
    if not isinstance(raw,bytes) or not 0<len(raw)<=8192:
        raise ValueError('missing or invalid external anchor')
    record=json.loads(raw)
    if not isinstance(record,dict) or set(record)!={'payload','signature'} or auth.canonical(record)!=raw:
        raise ValueError('invalid anchor envelope')
    local=journal.read(state,now=now,public=public,pin=pin)
    if local['status']!='COMPLETE':
        raise ValueError('local journal incomplete')
    name=f"dsig-prod-{local['cycle'].replace('-','')}T011500Z.dsigbak"
    expected=dict(purpose=PURPOSE,run_id=run_id,bucket_id=bucket_id,
        archive=f'prod/qualification/v232/{run_id}/{name}',archive_sha256=local['archive_sha256'],
        journal_head=local['head'],cycle=local['cycle'],key_id=pin,qualification_only=True)
    if auth.canonical(record['payload'])!=auth.canonical(expected):
        raise ValueError('anchor binding mismatch')
    try:
        Ed25519PublicKey.from_public_bytes(public).verify(
            base64.b64decode(record['signature'],validate=True),auth.canonical(expected))
    except (InvalidSignature,ValueError,TypeError):
        raise ValueError('invalid anchor signature') from None
    return dict(status='PASS',external_journal_anchor_verified=True,
        anchor_sha256=hashlib.sha256(raw).hexdigest(),object=obj,
        journal_head=local['head'],qualification_only=True,production_authorized=False)


def publish(*, root, now, signer, pin, key, run_id, bucket_id, remote):
    root=Path(root)
    obj=object_name(run_id)
    public=signer.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    guard.private_dir(root)
    guard.private_dir(root/'locks')
    guard.private_dir(root/'state')
    # Requalify archive before publishing; verify existing checkpoint first
    # so a missing local suffix cannot cause a new anchor.
    policy_check(remote,bucket_id)
    existing=remote.read(BUCKET,obj)
    if existing is not None:
        with guard.locked(root/'locks'):
            verify(state=root/'state',now=now,public=public,pin=pin,run_id=run_id,bucket_id=bucket_id,remote=remote)
    result=qualification.verify_remote(root=root,now=now,public=public,pin=pin,key=key,run_id=run_id,bucket_id=bucket_id,remote=remote)
    with guard.locked(root/'locks'):
        local=journal.read(root/'state',now=now,public=public,pin=pin)
        if local['status']!='COMPLETE' or local['head']!=result['journal_head'] or local['archive_sha256']!=result['sha256']:
            raise ValueError('journal changed during qualification')
        p=dict(purpose=PURPOSE,run_id=run_id,bucket_id=bucket_id,archive=result['object'],
            archive_sha256=result['sha256'],journal_head=result['journal_head'],cycle=local['cycle'],
            key_id=pin,qualification_only=True)
        raw=auth.canonical(dict(payload=p,signature=base64.b64encode(signer.sign(auth.canonical(p))).decode('ascii')))
        existing=remote.read(BUCKET,obj)
        created=existing is None
        if created:
            remote.create_only(BUCKET,obj,raw)
        elif not isinstance(existing,bytes) or not hmac.compare_digest(existing,raw):
            raise ValueError('existing anchor differs')
        out=verify(state=root/'state',now=now,public=public,pin=pin,run_id=run_id,bucket_id=bucket_id,remote=remote)
        return dict(out,created=created,remote_restore_verified=True)
