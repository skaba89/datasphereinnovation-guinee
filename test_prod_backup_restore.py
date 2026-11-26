"""Real encrypted backup and restore qualification on synthetic data only."""
import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

from cryptography.fernet import Fernet
import operations
import server


class ProdBackupRestoreTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.active=self.root/'active.sqlite3'
        self.archive=self.root/'dsig-prod-synthetic.dsigbak'
        self.restored=self.root/'restored.sqlite3'
        self.served=self.root/'public'
        self.served.mkdir()
        self.key=Fernet.generate_key().decode()
        env=patch.dict(os.environ,{'DSIG_BACKUP_KEY':self.key,'DSIG_ENV':'DEV'})
        env.start()
        self.addCleanup(env.stop)
        with patch.object(server,'DB',self.active):
            with closing(server.connect()) as db:
                db.execute("INSERT INTO accounts(id,username,role,key_hash) VALUES('qa','qa.example','ADMIN','synthetic-hash')")
                db.execute("INSERT INTO sessions(token_hash,account_id,expires) VALUES('synthetic-session','qa',4102444800)")
                db.execute("INSERT INTO requests(id,nom,org,email,besoin,solution,message) VALUES('qa','QA','QA','qa@example.invalid','QA','QA','synthetic-backup-marker')")
                db.commit()

    def backup(self):
        operations.encrypted_backup(self.active,self.archive,self.served)
        return hashlib.sha256(self.archive.read_bytes()).hexdigest()

    def restore(self):
        operations.restore_isolated(self.archive,self.restored,self.active,self.served)

    def test_round_trip(self):
        before=self.backup()
        self.assertNotIn(b'synthetic-backup-marker',self.archive.read_bytes())
        self.restore()
        self.assertEqual(hashlib.sha256(self.archive.read_bytes()).hexdigest(),before)
        with closing(operations.readonly(self.restored)) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchall(),[('ok',)])
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual(db.execute("SELECT message FROM requests WHERE id='qa'").fetchone(),('synthetic-backup-marker',))
            self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0],0)
        with closing(operations.readonly(self.active)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0],1)

    def test_wrong_key(self):
        self.backup()
        with patch.dict(os.environ,{'DSIG_BACKUP_KEY':Fernet.generate_key().decode()}):
            with self.assertRaises(ValueError):self.restore()
        self.assertFalse(self.restored.exists())

    def test_tampered_archive(self):
        self.backup()
        data=bytearray(self.archive.read_bytes())
        data[len(data)//2]^=1
        self.archive.write_bytes(data)
        with self.assertRaises(ValueError):self.restore()
        self.assertFalse(self.restored.exists())

    def test_no_overwrite_or_public_restore(self):
        self.backup()
        with self.assertRaises(FileExistsError):self.backup()
        for path in (self.active,self.served/'leak.sqlite3'):
            with self.assertRaises(ValueError):
                operations.restore_isolated(self.archive,path,self.active,self.served)
        self.restore()
        with self.assertRaises(FileExistsError):self.restore()
