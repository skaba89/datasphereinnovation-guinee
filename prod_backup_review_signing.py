"""Private key loading and domain-separated qualification signing.

Never emits a business-daily proof or authorizes production.
"""
import os
import stat
import base64
import hashlib
import hmac
import re
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import prod_authorization
import prod_b2_export

PURPOSE='DSIG-PROD-BACKUP-QUALIFICATION-V1'


def read_private(path, size):
    path=Path(path)
    parent=path.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or stat.S_IMODE(parent.st_mode)!=0o700 or parent.st_uid!=os.getuid():
        raise ValueError('unsafe key directory')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as handle:
        info=os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o600 or info.st_uid!=os.getuid() or info.st_nlink!=1 or info.st_size!=size:
            raise ValueError('unsafe key file')
        data=handle.read(size+1)
        if len(data)!=size:
            raise ValueError('invalid key length')
        return data


def load_keys(backup_path, signer_path, *, pinned_signer_id, forbidden_backup_ids):
    if not re.fullmatch(r'[0-9a-f]{64}',pinned_signer_id):
        raise ValueError('invalid signer pin')
    if not isinstance(forbidden_backup_ids,(set,frozenset)) or len(forbidden_backup_ids)<2 or any(not re.fullmatch(r'[0-9a-f]{64}',x) for x in forbidden_backup_ids):
        raise ValueError('missing independent REC and candidate key fingerprints')
    backup=read_private(backup_path,44)
    raw=base64.b64decode(backup,altchars=b'-_',validate=True)
    if len(raw)!=32 or base64.urlsafe_b64encode(raw)!=backup:
        raise ValueError('noncanonical backup key')
    Fernet(backup)
    if hashlib.sha256(raw).hexdigest() in forbidden_backup_ids:
        raise ValueError('backup key reused')
    signing=read_private(signer_path,32)
    if hmac.compare_digest(raw,signing):
        raise ValueError('key material reused')
    signer=Ed25519PrivateKey.from_private_bytes(signing)
    public=signer.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    if not hmac.compare_digest(hashlib.sha256(public).hexdigest(),pinned_signer_id):
        raise ValueError('signer pin mismatch')
    return backup,signer


def sign_qualification(result, signer, *, archive, archive_bytes, backup_key):
    if (not isinstance(result,dict) or result.get('qualification_only') is not True
            or result.get('business_provenance_verified') is not False
            or result.get('production_authorized') is not False
            or result.get('restore_verified') is not True
            or not isinstance(archive,str) or not prod_b2_export.NAME.fullmatch(archive)
            or result.get('archive')!=archive):
        raise ValueError('invalid qualification result')
    if not isinstance(archive_bytes,bytes) or not 0<len(archive_bytes)<=128*1024*1024:
        raise ValueError('invalid archive')
    digest=hashlib.sha256(archive_bytes).hexdigest()
    if result.get('sha256')!=digest:
        raise ValueError('archive digest mismatch')
    prod_b2_export.verify_archive(archive_bytes,backup_key)
    public=signer.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    payload=dict(purpose=PURPOSE,key_id=hashlib.sha256(public).hexdigest(),
                 proof=dict(schema=1,kind='isolated-review',archive=archive,sha256=digest,
                            qualification_only=True,business_provenance_verified=False,
                            restore_verified=True,production_authorized=False))
    return dict(payload,signature=base64.b64encode(signer.sign(prod_authorization.canonical(payload))).decode('ascii'))
