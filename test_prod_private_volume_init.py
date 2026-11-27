import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import prod_private_volume_init as init

@unittest.skipIf(os.getuid()==0 or os.getgid()==0,'non-root operator required')
class VolumeInitTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.data=Path(temp.name)/'data'
        self.data.mkdir(mode=0o700)
        self.db=self.data/'requests.sqlite3'

    def test_initialize_real_schema_and_preserve(self):
        result=init.initialize_isolated(self.data)
        self.assertTrue(result['created'])
        self.assertFalse(result['production_authorized'])
        init.operations.verify(self.db)
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("INSERT INTO requests(id,nom,org,email,besoin,solution,message) VALUES ('test','n','o','e','b','s','m')")
            conn.commit()
        before=self.db.read_bytes()
        self.assertFalse(init.initialize_isolated(self.data)['created'])
        self.assertEqual(self.db.read_bytes(),before)

    def test_concurrent_lock(self):
        with init.exclusive(self.data):
            with self.assertRaises(BlockingIOError):
                init.initialize_isolated(self.data)
        self.assertEqual(list(self.data.iterdir()),[])

    def test_failure_before_publication(self):
        with patch.object(init.operations,'verify',side_effect=ValueError('invalid')):
            with self.assertRaises(ValueError):
                init.initialize_isolated(self.data)
        self.assertEqual(list(self.data.iterdir()),[])

    def test_unknown_volume_is_preserved(self):
        self.db.write_bytes(b'invalid')
        self.db.chmod(0o600)
        with self.assertRaises(ValueError):
            init.initialize_isolated(self.data)
        self.assertEqual(self.db.read_bytes(),b'invalid')

if __name__=='__main__':
    unittest.main()
