import unittest
from datetime import datetime,timezone,timedelta
import prod_backup_retry as r

class RetryTests(unittest.TestCase):
    def at(self,h,m,s=0):return datetime(2026,11,26,h,m,s,tzinfo=timezone.utc)
    def check(self,now,failures,stage='export'):
        return r.decide(now=now,cycle_day='2026-11-26',stage=stage,failures=failures)
    def failure(self,m,code='NETWORK_TIMEOUT'):
        return dict(at=self.at(2,m),code=code)
    def test_first_due(self):
        self.assertEqual(self.check(self.at(2,5),[])['status'],'DUE')
    def test_wait(self):
        self.assertEqual(self.check(self.at(2,10,30),[self.failure(10)])['status'],'WAIT')
    def test_due(self):
        result=self.check(self.at(2,11),[self.failure(10)])
        self.assertEqual(result['status'],'DUE')
        self.assertFalse(result['execution_authorized'])
    def test_backoff(self):
        self.assertEqual(self.check(self.at(2,12),[self.failure(10),self.failure(11)])['status'],'WAIT')
    def test_permanent(self):
        self.assertEqual(self.check(self.at(2,15),[self.failure(10,'DIGEST_MISMATCH')])['status'],'BLOCKED_PERMANENT')
    def test_exhausted(self):
        self.assertEqual(self.check(self.at(2,40),[self.failure(m) for m in (5,6,8,12,20)])['status'],'EXHAUSTED')
    def test_window(self):
        self.assertEqual(self.check(self.at(2,59),[self.failure(59)])['status'],'MISSED_WINDOW')
    def test_future(self):
        with self.assertRaises(ValueError):self.check(self.at(2,10),[self.failure(11)])
    def test_order(self):
        with self.assertRaises(ValueError):self.check(self.at(2,20),[self.failure(11),self.failure(10)])
    def test_utc(self):
        self.assertEqual(self.check(self.at(2,5).astimezone(timezone(timedelta(hours=1))),[])['status'],'DUE')
