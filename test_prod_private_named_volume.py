import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
import prod_private_named_volume as named

@unittest.skipIf(os.getuid()==0 or os.getgid()==0,'non-root operator required')
class NamedVolumeTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.data=Path(temp.name)/'data'
        self.data.mkdir(mode=0o700)
        self.db=self.data/'requests.sqlite3'
        self.names=['alice.example','bob.example']

    def test_requires_schema(self):
        with self.assertRaises(ValueError):
            named.initialize_review(self.data,self.names)
        self.assertEqual(list(self.data.iterdir()),[])

    def test_bootstrap_and_mfa_not_ready(self):
        named.volume.initialize_isolated(self.data)
        rows=named.initialize_review(self.data,self.names)
        self.assertEqual(len(rows),2)
        with closing(sqlite3.connect(self.db)) as db:
            for row in rows:
                self.assertEqual(db.execute('SELECT key_hash FROM accounts WHERE id=?',(row['id'],)).fetchone(),
                                 (named.bootstrap.accounts.digest(row['activation_key']),))
        report=named.readiness(self.data)
        self.assertEqual(report['status'],'FAIL')
        self.assertFalse(report['production_authorized'])
        self.assertEqual(report['checks']['named_admins'],'PASS')
        self.assertEqual(report['checks']['mfa'],'FAIL')

    def test_repeat_rejected(self):
        named.volume.initialize_isolated(self.data)
        named.initialize_review(self.data,self.names)
        with self.assertRaises(ValueError):
            named.initialize_review(self.data,self.names)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM accounts').fetchone(),(2,))

    def test_locked_volume_rejected(self):
        named.volume.initialize_isolated(self.data)
        with named.volume.exclusive(self.data):
            with self.assertRaises(BlockingIOError):
                named.initialize_review(self.data,self.names)

if __name__=='__main__':
    unittest.main()
