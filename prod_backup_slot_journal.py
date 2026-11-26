"""Signed, append-only qualification journal. No actual job execution or PROD authority."""
import base64
import hashlib
import hmac
import re
import os
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
import prod_authorization as auth
import prod_backup_slot_cycle as cycle
import prod_backup_orchestrator as guard
import operations

PURPOSE='DSIG-QUALIFICATION-SLOT-V2'
STAGES=cycle.STAGES


def read(state, *, now, public, pin):
    state=Path(state)
    guard.private_dir(state)
    if not isinstance(public,bytes) or len(public)!=32 or not isinstance(pin,str) or not hmac.compare_digest(hashlib.sha256(public).hexdigest(),pin):
        raise ValueError('untrusted journal signer')
    day=cycle.plan(now,{})['cycle']
    stamps={}
    previous='0'*64
    archive=None
    for stage in STAGES:
        path=state/f'{day}.{stage}.json'
        if not path.exists() and not path.is_symlink():
            continue
        record=guard.read_proof(path)
        if not isinstance(record,dict) or set(record)!={'payload','signature'}:
            raise ValueError('invalid journal envelope')
        p=record['payload']
        if not isinstance(p,dict) or set(p)!={'purpose','cycle','stage','completed_at','archive_sha256','previous','key_id'}:
            raise ValueError('invalid journal payload')
        if (p['purpose'],p['cycle'],p['stage'],p['previous'],p['key_id'])!=(PURPOSE,day,stage,previous,pin):
            raise ValueError('journal binding mismatch')
        if not isinstance(p['archive_sha256'],str) or not re.fullmatch(r'[0-9a-f]{64}',p['archive_sha256']):
            raise ValueError('invalid archive digest')
        if archive is not None and archive!=p['archive_sha256']:
            raise ValueError('archive changed')
        archive=p['archive_sha256']
        try:
            Ed25519PublicKey.from_public_bytes(public).verify(base64.b64decode(record['signature'],validate=True),auth.canonical(p))
        except (InvalidSignature,ValueError,TypeError):
            raise ValueError('invalid journal signature') from None
        stamps[stage]=auth.timestamp(p['completed_at'])
        previous=hashlib.sha256(auth.canonical(record)).hexdigest()
    result=cycle.plan(now,stamps)
    return dict(result,completion_authenticated=True,qualification_only=True,archive_sha256=archive,head=previous)


def append(state, *, now, stage, archive_sha256, signer, pin):
    """Records a caller-attested qualification result, not proof of actual job execution."""
    state=Path(state)
    guard.private_dir(state)
    if not isinstance(archive_sha256,str) or not re.fullmatch(r'[0-9a-f]{64}',archive_sha256):
        raise ValueError('invalid archive digest')
    public=signer.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    with guard.locked(state):
        result=read(state,now=now,public=public,pin=pin)
        if result['status']!='DUE' or result['next_stage']!=stage:
            raise ValueError('stage not due')
        if result['archive_sha256'] not in (None,archive_sha256):
            raise ValueError('archive changed')
        from datetime import timezone
        p=dict(purpose=PURPOSE,cycle=result['cycle'],stage=stage,
               completed_at=now.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
               archive_sha256=archive_sha256,previous=result['head'],key_id=pin)
        record=dict(payload=p,signature=base64.b64encode(signer.sign(auth.canonical(p))).decode('ascii'))
        operations.write_new(state/f"{result['cycle']}.{stage}.json",auth.canonical(record))
        fd=os.open(state,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
        return read(state,now=now,public=public,pin=pin)
