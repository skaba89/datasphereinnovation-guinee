"""Offline schema initialization primitive; not a production startup authority."""
import fcntl
import os
import stat
import tempfile
from pathlib import Path
from contextlib import closing, contextmanager
import operations
import prod_private_data_lifecycle as lifecycle
import server

@contextmanager
def exclusive(data_dir):
    path=Path(data_dir)
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        info=os.fstat(fd)
        if (not os.getuid() or not os.getgid() or
                (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))!=(os.getuid(),os.getgid(),0o700)):
            raise ValueError('unsafe data directory')
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        current=path.lstat()
        if (current.st_dev,current.st_ino)!=(info.st_dev,info.st_ino):
            raise ValueError('directory changed')
        yield path,fd
    finally:
        os.close(fd)

def initialize_isolated(data_dir):
    """Trusted caller must establish isolated volume provenance and no writers.
    No CLI or server integration. Existing databases are never migrated here.
    """
    with exclusive(data_dir) as (path,fd):
        report=lifecycle.inspect(path)
        if report['status']!='PASS':
            raise ValueError('unsafe data state')
        if report['state']=='EXISTING_SCHEMA':
            return dict(status='PASS',created=False,production_authorized=False)
        with tempfile.TemporaryDirectory(prefix='.schema-',dir=path) as stage:
            target=Path(stage)/'requests.sqlite3'
            with closing(server.connect(target)):
                pass
            operations.verify(target)
            if set(p.name for p in Path(stage).iterdir())!={'requests.sqlite3'}:
                raise ValueError('unexpected schema sidecars')
            with target.open('rb') as stream:
                os.fsync(stream.fileno())
            # Atomic publication that fails if another database already exists.
            os.link(target,path/'requests.sqlite3',follow_symlinks=False)
            os.fsync(fd)
        os.fsync(fd)
        if lifecycle.inspect(path)['state']!='EXISTING_SCHEMA':
            raise ValueError('published schema requires review')
        return dict(status='PASS',created=True,production_authorized=False)
