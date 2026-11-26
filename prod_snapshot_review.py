"""Isolated encrypted snapshot primitive; not a production execution entrypoint."""
import hashlib
import os
import sqlite3
import stat
import tempfile
from contextlib import closing
from pathlib import Path
from cryptography.fernet import Fernet
import operations
import prod_b2_export
import prod_backup_orchestrator


def identity(path):
    st=path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1 or st.st_uid!=os.getuid():
        raise ValueError('unsafe database source')
    return st.st_dev,st.st_ino


def create_review_snapshot(active, destination, *, backup_key, source_check):
    """Caller supplies source check. A PASS is not proof of business provenance."""
    active,destination=Path(active),Path(destination)
    if not prod_b2_export.NAME.fullmatch(destination.name):
        raise ValueError('invalid review archive name')
    prod_backup_orchestrator.private_dir(active.parent)
    prod_backup_orchestrator.private_dir(destination.parent)
    a,b=active.parent.resolve(),destination.parent.resolve()
    if a==b or a in b.parents or b in a.parents:
        raise ValueError('overlapping source and backup directories')
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('archive exists')
    if not isinstance(backup_key,bytes):
        raise ValueError('invalid backup key')
    cipher=Fernet(backup_key)
    before=identity(active)
    if source_check().get('status')!='PASS':
        raise ValueError('source precheck failed')
    with tempfile.TemporaryDirectory(prefix='dsig-snapshot-',dir=destination.parent) as tmp:
        snapshot=Path(tmp)/'snapshot.sqlite3'
        with closing(operations.readonly(active)) as src, closing(sqlite3.connect(snapshot)) as dst:
            if src.execute('PRAGMA page_count').fetchone()[0]*src.execute('PRAGMA page_size').fetchone()[0]>operations.MAX_DB_BYTES:
                raise ValueError('database too large')
            src.backup(dst)
        operations.verify(snapshot)
        if not 0<snapshot.stat().st_size<=operations.MAX_DB_BYTES:
            raise ValueError('snapshot too large')
        encrypted=cipher.encrypt(snapshot.read_bytes())
        prod_b2_export.verify_archive(encrypted,backup_key)
        if identity(active)!=before or source_check().get('status')!='PASS':
            raise ValueError('source postcheck failed')
        # Publish without replacement only after the complete restore check.
        staged=Path(tmp)/'archive'
        operations.write_new(staged,encrypted)
        os.link(staged,destination,follow_symlinks=False)
        staged.unlink()
        fd=os.open(destination.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    return {'archive':destination.name,'sha256':hashlib.sha256(encrypted).hexdigest(),
            'restore_verified':True,'qualification_only':True,
            'business_provenance_verified':False,'production_authorized':False}
