import sqlite3
import unittest

import accounts
import prod_named_bootstrap as b


class NamedBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        accounts.schema(self.db)
        self.db.commit()

    def create(self):
        return b.initialize_review(self.db,['alice.example','bob.example'])

    def test_named_keys_and_mfa_block(self):
        rows=self.create()
        self.assertEqual(len(rows),2)
        for r in rows:
            self.assertEqual(self.db.execute('SELECT key_hash,role FROM accounts WHERE id=?',(r['id'],)).fetchone(),
                             (accounts.digest(r['activation_key']),'ADMIN'))
            self.assertEqual(accounts.effective_permissions('ADMIN',False),{})
        self.assertEqual(b.readiness(self.db)['status'],'FAIL')
        self.assertFalse(b.readiness(self.db)['production_authorized'])

    def test_repeat_refused(self):
        self.create()
        with self.assertRaises(ValueError):self.create()
        self.assertEqual(self.db.execute('SELECT count(*) FROM accounts').fetchone()[0],2)

    def test_marker_survives_account_deletion(self):
        self.create()
        self.db.execute('DELETE FROM accounts')
        self.db.execute('DELETE FROM access_events')
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):self.create()

    def test_bad_names(self):
        for names in (['admin','root'],['alice.example','ALICE.EXAMPLE'],['alice.example']):
            with self.assertRaises(ValueError):b.initialize_review(self.db,names)
        self.assertEqual(self.db.execute('SELECT count(*) FROM accounts').fetchone()[0],0)

    def test_existing_audit_refused(self):
        accounts.event(self.db,'old','test','test')
        self.db.commit()
        with self.assertRaises(ValueError):self.create()

    def test_rollback(self):
        self.db.execute("CREATE TRIGGER reject_second BEFORE INSERT ON accounts WHEN NEW.username='bob.example' BEGIN SELECT RAISE(ABORT,'test'); END")
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):self.create()
        self.assertEqual(self.db.execute('SELECT count(*) FROM accounts').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM access_events').fetchone()[0],0)
        self.db.execute('DROP TRIGGER reject_second')
        self.db.commit()
        self.create()
