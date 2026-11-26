"""Dedicated PROD export primitive, no CLI or automatic execution.

Adapter must be bound to independently verified dedicated B2 credentials.
"""
import hashlib
import re
import stat
import os
from datetime import datetime
from pathlib import Path

BUCKET='dsig-prod-backups'
NAME=re.compile(r'dsig-prod-(\d{8}T\d{6}Z)\.dsigbak')


def export_review(archive, *, expected_bucket_id, remote):
    path=Path(archive)
    match=NAME.fullmatch(path.name)
    if not match:
        raise ValueError('invalid PROD archive name')
    stamp=datetime.strptime(match.group(1),'%Y%m%dT%H%M%SZ')
    info=path.lstat()
    if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o600
            or info.st_uid!=os.getuid() or info.st_nlink!=1 or not 0<info.st_size<=128*1024*1024):
        raise ValueError('invalid archive')
    if not isinstance(expected_bucket_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,128}',expected_bucket_id):
        raise ValueError('invalid bucket identity')
    bucket=remote.bucket_info(BUCKET)
    if (bucket.get('bucketName')!=BUCKET or bucket.get('bucketId')!=expected_bucket_id
            or bucket.get('bucketType')!='allPrivate'
            or bucket.get('encryption')!='SSE-B2'
            or bucket.get('lock_mode')!='compliance'
            or type(bucket.get('lock_days')) is not int or bucket['lock_days']<30):
        raise ValueError('invalid remote policy')
    obj=f'prod/{stamp:%Y/%m}/{path.name}'
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as handle:
        current=os.fstat(handle.fileno())
        if (current.st_dev,current.st_ino,current.st_size,current.st_mtime_ns)!=(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns):
            raise ValueError('archive changed')
        data=handle.read(128*1024*1024+1)
    if len(data)!=info.st_size:
        raise ValueError('archive changed')
    digest=hashlib.sha256(data).hexdigest()
    # Adapter must refuse ambiguous versions and provide create-only semantics.
    existing=remote.read(BUCKET,obj)
    uploaded=False
    if existing is None:
        remote.create_only(BUCKET,obj,data)
        uploaded=True
        existing=remote.read(BUCKET,obj)
    if not isinstance(existing,bytes) or hashlib.sha256(existing).hexdigest()!=digest:
        raise ValueError('remote archive mismatch')
    if path.lstat()!=info:
        # Reading can update atime, so compare only stable identity below.
        end=path.lstat()
        if (end.st_dev,end.st_ino,end.st_size,end.st_mtime_ns)!=(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns):
            raise ValueError('archive changed')
    return {'object':obj,'sha256':digest,'uploaded':uploaded,
            'adapter_verified':True,'production_authorized':False}
