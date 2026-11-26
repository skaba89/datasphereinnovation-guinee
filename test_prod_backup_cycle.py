import unittest
from datetime import datetime, timezone, timedelta
from prod_backup_cycle import plan

def t(h,m=0):
    return datetime(2026,11,26,h,m,tzinfo=timezone.utc)

class CycleTests(unittest.TestCase):
    def test_snapshot_due(self):
        self.assertEqual(plan(t(1,15),{})['next_stage'],'snapshot')
        self.assertEqual(plan(t(1,15),{})['status'],'DUE')
    def test_wait_export(self):
        self.assertEqual(plan(t(1,30),{'snapshot':t(1,20)})['status'],'WAIT')
    def test_export_due(self):
        self.assertEqual(plan(t(2,5),{'snapshot':t(1,20)})['next_stage'],'export')
    def test_audit_due(self):
        self.assertEqual(plan(t(3),{'snapshot':t(1,20),'export':t(2,10)})['next_stage'],'audit')
    def test_complete(self):
        r=plan(t(4),{'snapshot':t(1,20),'export':t(2,10),'audit':t(3,10)})
        self.assertEqual(r['status'],'COMPLETE')
        self.assertFalse(r['execution_authorized'])
        self.assertFalse(r['production_authorized'])
        self.assertFalse(r['completion_authenticated'])
    def test_missing_snapshot(self):
        self.assertEqual(plan(t(2,5),{})['status'],'MISSED_WINDOW')
    def test_missing_previous_stage(self):
        with self.assertRaises(ValueError):plan(t(3),{'export':t(2,10)})
    def test_future(self):
        with self.assertRaises(ValueError):plan(t(1,20),{'snapshot':t(1,21)})
    def test_naive(self):
        with self.assertRaises(ValueError):plan(t(1,20).replace(tzinfo=None),{})
    def test_offset(self):
        self.assertEqual(plan(t(1,20).astimezone(timezone(timedelta(hours=1))),{}),plan(t(1,20),{}))
    def test_before_next_cycle(self):
        self.assertEqual(plan(t(0,30),{})['cycle'],'2026-11-25')
    def test_late_completion(self):
        with self.assertRaises(ValueError):plan(t(3),{'snapshot':t(2,6)})
