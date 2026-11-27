"""Offline named-account qualification on an exclusively owned isolated volume.
No runtime authorization; activation keys are returned only to the caller.
"""
import sqlite3
from contextlib import closing
import prod_private_volume_init as volume
import prod_private_data_lifecycle as lifecycle
import prod_named_bootstrap as bootstrap

def initialize_review(data_dir, usernames):
    """Trusted caller must verify isolated volume provenance and stop all writers."""
    with volume.exclusive(data_dir) as (path, _):
        if lifecycle.inspect(path)['state']!='EXISTING_SCHEMA':
            raise ValueError('initialized isolated schema required')
        target=path/'requests.sqlite3'
        with closing(sqlite3.connect(target.absolute().as_uri()+'?mode=rw',uri=True)) as db:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('PRAGMA foreign_keys=ON')
            return bootstrap.initialize_review(db,usernames)

def readiness(data_dir):
    """Read readiness without writing or revealing account identities."""
    with volume.exclusive(data_dir) as (path, _):
        if lifecycle.inspect(path)['state']!='EXISTING_SCHEMA':
            raise ValueError('initialized isolated schema required')
        target=path/'requests.sqlite3'
        with closing(sqlite3.connect(target.absolute().as_uri()+'?mode=ro&immutable=1',uri=True)) as db:
            db.execute('PRAGMA trusted_schema=OFF')
            return bootstrap.readiness(db)
