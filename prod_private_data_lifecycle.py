"""Read-only classification of a dedicated data directory before initialization.
No database creation, migrations, authorization or recovery is performed.
"""
import os
import stat
import sqlite3
from pathlib import Path
from contextlib import closing
import operations

def inspect(data_dir):
    result=dict(status='FAIL',state='UNKNOWN',database_initialized=False,
                startup_authorized=False,production_authorized=False)
    try:
        path=Path(data_dir)
        uid,gid=os.getuid(),os.getgid()
        d=path.lstat()
        if not uid or not gid or not stat.S_ISDIR(d.st_mode) or (
                d.st_uid,d.st_gid,stat.S_IMODE(d.st_mode))!=(uid,gid,0o700):
            return result
        names={p.name for p in path.iterdir()}
        if not names:
            return dict(result,status='PASS',state='EMPTY')
        # Never guess whether journal recovery is safe, or create a missing DB.
        if names!={'requests.sqlite3'}:
            return result
        db=path/'requests.sqlite3'
        info=db.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or (
                info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))!=(uid,gid,0o600):
            return result
        # Immutable read avoids creating SQLite sidecars; only valid for a
        # quiescent directory under an independently enforced exclusive lock.
        with closing(sqlite3.connect(db.absolute().as_uri()+'?mode=ro&immutable=1',uri=True)) as conn:
            conn.execute('PRAGMA trusted_schema=OFF')
            tables={row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not operations.REQUIRED_TABLES<=tables:
                return result
            if conn.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:
                return result
        if {p.name for p in path.iterdir()}!=names or db.lstat()!=info:
            return result
        return dict(result,status='PASS',state='EXISTING_SCHEMA')
    except (OSError,ValueError,TypeError,sqlite3.Error):
        return result
