import sqlite3
import unittest
import accounts
import appointments as a


class AppointmentTests(unittest.TestCase):
    def test_overlap_and_cancel(self):
        with sqlite3.connect(':memory:') as db:
            accounts.schema(db);a.schema(db);db.execute('CREATE TABLE opportunities(id TEXT PRIMARY KEY)');db.execute("INSERT INTO opportunities VALUES ('opp')")
            v={'opportunity_id':'opp','title':'Fictif','starts':'2027-01-01T10:00:00+01:00','ends':'2027-01-01T11:00:00+01:00'}
            aid=a.create(db,v,'test')
            with self.assertRaises(sqlite3.IntegrityError):a.create(db,v,'test')
            with self.assertRaises(ValueError):a.create(db,v|{'starts':'2027-01-01T10:00:00'},'test')
            a.finish(db,aid,{'status':'ANNULE','version':1},'test')
            with self.assertRaises(sqlite3.IntegrityError):a.finish(db,aid,{'status':'TERMINE','version':1},'test')
            self.assertNotEqual(a.create(db,v,'test'),aid)
            self.assertEqual(db.execute('SELECT count(*) FROM appointment_events').fetchone()[0],3)
        self.assertTrue(accounts.allowed('COMMERCIAL','crm','POST'))
        self.assertFalse(accounts.allowed('DIRECTION','crm','POST'))
