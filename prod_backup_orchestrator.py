"""Explicit review export orchestration; no timer, no server startup."""
import fcntl
import json
import os
import stat
from pathlib import Path
from datetime import datetime, timezone
from contextlib import contextmanager
import prod_b2_export
import operations


def private_dir(path):
    info=path.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o700 or info.st_uid!=os.getuid():
        raise ValueError('unsafe review directory')


@contextmanager
def locked(state):
    fd=os.open(state/'.export.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK,0o600)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o600 or info.st_uid!=os.getuid() or info.st_nlink!=1:
            raise ValueError('unsafe export lock')
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('export already running') from None
        yield
    finally:
        os.close(fd)


def read_proof(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as handle:
        info=os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o600 or info.st_uid!=os.getuid() or info.st_nlink!=1 or info.st_size>8192:
            raise ValueError('unsafe proof')
        return json.loads(handle.read(8193))


def review_export(name, *, backups, state, expected_bucket_id, remote, backup_key):
    if not isinstance(name,str) or not prod_b2_export.NAME.fullmatch(name):
        raise ValueError('invalid archive name')
    backups,state=Path(backups),Path(state)
    private_dir(backups)
    private_dir(state)
    a,b=backups.resolve(),state.resolve()
    if a==b or a in b.parents or b in a.parents:
        raise ValueError('overlapping review directories')
    marker=state/(name+'.review.json')
    with locked(state):
        previous=None
        if marker.exists() or marker.is_symlink():
            previous=read_proof(marker)
            # Existing proof is never refreshed or replaced.
            if not isinstance(previous,dict) or previous.get('archive')!=name or previous.get('bucket_id')!=expected_bucket_id:
                raise ValueError('proof identity mismatch')
            import hashlib
            path=backups/name
            info=path.lstat()
            if not stat.S_ISREG(info.st_mode) or not 0<info.st_size<=operations.MAX_ENCRYPTED_BYTES:
                raise ValueError('invalid archive')
            with path.open('rb') as handle:
                data=handle.read(operations.MAX_ENCRYPTED_BYTES+1)
            digest=hashlib.sha256(data).hexdigest()
            if previous.get('sha256')!=digest:
                raise ValueError('proof digest mismatch')
            # A previously proven archive must not be re-created if missing remotely.
            stamp=prod_b2_export.NAME.fullmatch(name).group(1)
            obj=f'prod/{stamp[:4]}/{stamp[4:6]}/{name}'
            if previous.get('object')!=obj:
                raise ValueError('proof object mismatch')
            remote.bucket_info(prod_b2_export.BUCKET)
            existing=remote.read(prod_b2_export.BUCKET,obj)
            if not isinstance(existing,bytes) or hashlib.sha256(existing).hexdigest()!=digest:
                raise ValueError('previously proven remote archive missing or changed')
        result=prod_b2_export.export_review(backups/name,expected_bucket_id=expected_bucket_id,remote=remote,backup_key=backup_key)
        if previous is not None:
            if previous['sha256']!=result['sha256'] or previous['object']!=result['object']:
                raise ValueError('proof mismatch')
        else:
            proof=dict(schema=1,kind='isolated-review',archive=name,bucket_id=expected_bucket_id,
                       object=result['object'],sha256=result['sha256'],
                       verified_at=datetime.now(timezone.utc).isoformat(),
                       production_authorized=False)
            operations.write_new(marker,(json.dumps(proof,sort_keys=True)+'\n').encode())
            dfd=os.open(state,os.O_RDONLY|os.O_DIRECTORY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        return dict(result,proof_created=previous is None)
