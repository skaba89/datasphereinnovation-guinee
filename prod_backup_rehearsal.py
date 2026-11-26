"""Persistent local rehearsal of the backup cycle; no Docker or B2 writes."""
import os
import json
import hashlib
import base64
import hmac
import re
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
import operations
import prod_authorization
import prod_b2_export
import prod_snapshot_review
import prod_backup_review_signing as signing
import prod_backup_orchestrator as guard


def read_archive(path):
    import stat
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        st=os.fstat(f.fileno())
        if (not stat.S_ISREG(st.st_mode) or stat.S_IMODE(st.st_mode)!=0o600
                or st.st_uid!=os.getuid() or st.st_nlink!=1
                or not 0<st.st_size<=operations.MAX_ENCRYPTED_BYTES):
            raise ValueError('unsafe rehearsal archive')
        data=f.read(operations.MAX_ENCRYPTED_BYTES+1)
        end=os.fstat(f.fileno())
        if len(data)!=st.st_size or (st.st_size,st.st_mtime_ns)!=(end.st_size,end.st_mtime_ns):
            raise ValueError('archive changed')
        return data


def sync_dir(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def validate_proof(envelope, public, pin, name, data, key):
    if not isinstance(envelope,dict) or set(envelope)!={'purpose','key_id','proof','signature'}:
        raise ValueError('invalid rehearsal proof')
    if hashlib.sha256(public).hexdigest()!=pin or envelope['key_id']!=pin or envelope['purpose']!=signing.PURPOSE:
        raise ValueError('unexpected signer or purpose')
    expected=dict(schema=1,kind='isolated-review',archive=name,
                  sha256=hashlib.sha256(data).hexdigest(),qualification_only=True,
                  business_provenance_verified=False,restore_verified=True,production_authorized=False)
    if prod_authorization.canonical(envelope['proof'])!=prod_authorization.canonical(expected):
        raise ValueError('proof mismatch')
    payload={k:envelope[k] for k in ('purpose','key_id','proof')}
    Ed25519PublicKey.from_public_bytes(public).verify(
        base64.b64decode(envelope['signature'],validate=True),prod_authorization.canonical(payload))
    prod_b2_export.verify_archive(data,key)


def run_rehearsal(*, active, root, name, backup_path, signer_path,
                  pinned_signer_id, forbidden_backup_ids, source_check):
    """All paths are explicit operator-owned rehearsal paths. No remote adapter."""
    root=Path(root)
    active=Path(active)
    if not isinstance(name,str) or not prod_b2_export.NAME.fullmatch(name):
        raise ValueError('invalid archive name')
    guard.private_dir(root)
    if active.resolve().is_relative_to(root.resolve()) or root.resolve().is_relative_to(active.parent.resolve()):
        raise ValueError('source and rehearsal paths overlap')
    archives=root/'archives'
    replica=root/'replica'
    state=root/'state'
    for p in (archives,replica,state):
        guard.private_dir(p)
    key,signer=signing.load_keys(backup_path,signer_path,
        pinned_signer_id=pinned_signer_id,forbidden_backup_ids=forbidden_backup_ids)
    from cryptography.hazmat.primitives import serialization
    public=signer.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    archive=archives/name
    copy=replica/name
    marker=state/(name+'.qualification.json')
    with guard.locked(state):
        if marker.exists() or marker.is_symlink():
            envelope=guard.read_proof(marker)
            data=read_archive(archive)
            validate_proof(envelope,public,pinned_signer_id,name,data,key)
            if not hmac.compare_digest(hashlib.sha256(read_archive(copy)).digest(),hashlib.sha256(data).digest()):
                raise ValueError('replica mismatch')
            created=False
        else:
            # Partial cycles require operator review, never silently replace or reuse.
            if any(p.exists() or p.is_symlink() for p in (archive,copy)):
                raise ValueError('incomplete rehearsal requires review')
            result=prod_snapshot_review.create_review_snapshot(active,archive,backup_key=key,source_check=source_check)
            data=read_archive(archive)
            operations.write_new(copy,data)
            sync_dir(replica)
            copied=read_archive(copy)
            if not hmac.compare_digest(hashlib.sha256(data).digest(),hashlib.sha256(copied).digest()):
                raise ValueError('replica mismatch')
            envelope=signing.sign_qualification(result,signer,archive=name,archive_bytes=copied,backup_key=key)
            validate_proof(envelope,public,pinned_signer_id,name,copied,key)
            operations.write_new(marker,(json.dumps(envelope,sort_keys=True)+'\n').encode())
            sync_dir(state)
            created=True
    return {'status':'PASS','created':created,'archive':name,'sha256':hashlib.sha256(data).hexdigest(),
            'local_replica_verified':True,'qualification_only':True,'remote_verified':False,
            'business_provenance_verified':False,'production_authorized':False}
