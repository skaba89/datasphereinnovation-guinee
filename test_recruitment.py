import sqlite3
import unittest
import uuid
import accounts
import consultants
import recruitment


class RecruitmentTests(unittest.TestCase):
    def test_conversion_is_idempotent_and_restricted(self):
        with sqlite3.connect(':memory:') as db:
            accounts.schema(db);consultants.schema(db);recruitment.schema(db)
            db.execute('CREATE TABLE requests(id TEXT PRIMARY KEY,nom TEXT,email TEXT,besoin TEXT)')
            rid=str(uuid.uuid4());other=str(uuid.uuid4())
            db.executemany('INSERT INTO requests VALUES (?,?,?,?)',[(rid,'Fictif','qa@example.invalid','Candidature spontanée'),(other,'Fictif','qa@example.invalid','Partenariat')])
            first,created=recruitment.qualify(db,rid,'Data Engineer','Python','rh-test')
            self.assertTrue(created)
            self.assertEqual(recruitment.qualify(db,rid,'Data Engineer','Python','rh-test'),(first,False))
            self.assertEqual(db.execute('SELECT count(*) FROM consultants').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT status FROM consultants').fetchone()[0],'A_QUALIFIER')
            with self.assertRaises(ValueError):recruitment.qualify(db,other,'Data','Python','rh-test')
        self.assertTrue(accounts.allowed('RH','recruitment','POST'))
        self.assertFalse(accounts.allowed('COMMERCIAL','recruitment','GET'))
