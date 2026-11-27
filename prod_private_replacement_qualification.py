"""Disposable DEV qualification only; no production volume or credentials."""
import os
import json
import sqlite3
from pathlib import Path
from contextlib import closing
import prod_private_volume_init as volume
import prod_named_bootstrap as named
import prod_private_data_lifecycle as lifecycle
import operations
import server

DATA=Path('/qualification-data')

def exercise(phase,marker):
    if (os.environ.get('DSIG_ENV')!='DEV' or os.environ.get('DSIG_CONTAINER')!='1'
            or (os.getuid(),os.getgid())!=(10001,10001)
            or not DATA.is_mount() or os.environ.get('DSIG_ADMIN_TOKEN')):
        raise ValueError('isolated nonroot qualification mount required')
    if phase not in ('create','replace'):
        raise ValueError('unexpected phase')
    report=volume.initialize_isolated(DATA)
    if report['created']!=(phase=='create'):
        raise ValueError('unexpected schema lifecycle')
    with volume.exclusive(DATA):
        if lifecycle.inspect(DATA)['state']!='EXISTING_SCHEMA':
            raise ValueError('invalid persisted schema')
        dbpath=DATA/'requests.sqlite3'
        with closing(sqlite3.connect(dbpath)) as db:
            if phase=='create':
                named.initialize_review(db,['alice.example','bob.example'])
                with db:
                    db.execute("INSERT INTO requests(id,nom,org,email,besoin,solution,message) VALUES (?,?,?,?,?,?,?)",
                        (marker,'Synthetic','Qualification','qa@example.invalid','test','test','synthetic marker'))
            else:
                rows=db.execute("SELECT username FROM accounts WHERE role='ADMIN' ORDER BY username").fetchall()
                if rows!=[('alice.example',),('bob.example',)]:
                    raise ValueError('named accounts not persisted')
                if db.execute('SELECT id FROM requests').fetchall()!=[(marker,)]:
                    raise ValueError('business marker not persisted')
        operations.verify(dbpath)
    return {'status':'PASS','qualification_only':True,'production_authorized':False}
