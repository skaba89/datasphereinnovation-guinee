import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import prod_private_data_lifecycle as lifecycle

@unittest.skipIf(os.getuid()==0 or os.getgid()==0,'non-root operator required')
class DataLifecycleTest(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.path=Path(t.name)/'data'
        self.path.mkdir(mode=0o700)
        self.db=self.path/'requests.sqlite3'

    def create_db(self):
        with sqlite3.connect(self.db) as conn:
            for name in lifecycle.operations.REQUIRED_TABLES:
                conn.execute('CREATE TABLE "'+name+'" (id INTEGER)')
        conn.close()
        self.db.chmod(0o600)

    def test_empty(self):
        result=lifecycle.inspect(self.path)
        self.assertEqual(result['state'],'EMPTY')
        self.assertEqual(result['status'],'PASS')
        self.assertFalse(result['startup_authorized'])
        self.assertEqual(list(self.path.iterdir()),[])

    def test_persistent(self):
        self.create_db()
        before=self.db.read_bytes()
        result=lifecycle.inspect(self.path)
        self.assertEqual(result['state'],'EXISTING_SCHEMA')
        self.assertFalse(result['database_initialized'])
        self.assertEqual(self.db.read_bytes(),before)

    def test_read_induced_atime_change(self):
        self.create_db()
        info = self.db.stat()
        os.utime(self.db, ns=(0, info.st_mtime_ns))
        self.assertEqual(lifecycle.inspect(self.path)['state'], 'EXISTING_SCHEMA')

    def test_modification_metadata_rejected(self):
        self.create_db()
        original = lifecycle.sqlite3.connect
        def changed(*args, **kwargs):
            conn = original(*args, **kwargs)
            info = self.db.stat()
            os.utime(self.db, ns=(info.st_atime_ns, info.st_mtime_ns + 1000000000))
            return conn
        with patch.object(lifecycle.sqlite3, 'connect', side_effect=changed):
            self.assertEqual(lifecycle.inspect(self.path)['status'], 'FAIL')

    def test_sidecar_rejected(self):
        self.create_db()
        (self.path/'requests.sqlite3-wal').touch()
        self.assertEqual(lifecycle.inspect(self.path)['status'],'FAIL')

    def test_corrupt_database(self):
        self.db.write_bytes(b'not sqlite')
        self.db.chmod(0o600)
        self.assertEqual(lifecycle.inspect(self.path)['status'],'FAIL')

    def test_symlink_rejected(self):
        other=self.path.parent/'other'
        other.touch()
        self.db.symlink_to(other)
        self.assertEqual(lifecycle.inspect(self.path)['status'],'FAIL')

    def test_insecure_directory(self):
        self.path.chmod(0o755)
        self.assertEqual(lifecycle.inspect(self.path)['status'],'FAIL')

if __name__=='__main__':
    unittest.main()
