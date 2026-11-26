import unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
import prod_backup_cadence as c
import prod_backup_monitor as m

class CadenceTests(unittest.TestCase):
    def at(self,h,minute=0,day=26):
        return datetime(2026,11,day,h,minute,tzinfo=timezone.utc)
    def test_slots(self):
        a,b=c.slots('2026-11-26')
        self.assertEqual(b['snapshot_start']-a['snapshot_start'],timedelta(hours=12))
        self.assertEqual(b['export_end'],self.at(15))
    def test_midnight(self):
        self.assertEqual(c.plan(self.at(0))['current_slot'],'2026-11-25T13:15Z')
    def test_phase(self):
        self.assertEqual(c.plan(self.at(13,15))['phase'],'snapshot')
        self.assertEqual(c.plan(self.at(14,5))['phase'],'export')
        self.assertEqual(c.plan(self.at(15))['phase'],'audit')
        self.assertEqual(c.plan(self.at(16))['phase'],'IDLE')
    def test_boundary(self):
        self.assertIsNone(c.slot_for_snapshot(self.at(14,5)))
        self.assertIsNotNone(c.slot_for_snapshot(self.at(13,15)))
    def test_naive(self):
        with self.assertRaises(ValueError):c.plan(self.at(13).replace(tzinfo=None))
    def proof(self):
        return dict(schema=1,kind='business-daily',archive='dsig-prod-20261126T131500Z.dsigbak',
            object='prod/2026/11/dsig-prod-20261126T131500Z.dsigbak',sha256='a'*64,bucket_id='prod-bucket-id',
            verified_at='2026-11-26T14:10:00+00:00',qualification_only=False,synthetic_data=False,
            ephemeral_key=False,remote_restore_verified=True,daily_backup_qualified=True,production_authorized=False)
    def test_afternoon_claim(self):
        self.assertEqual(m.evaluate(self.proof(),expected_bucket_id='prod-bucket-id',now=self.at(15))['status'],'PASS')
    def test_wrong_slot(self):
        p=self.proof();p['verified_at']='2026-11-27T02:10:00+00:00'
        self.assertEqual(m.evaluate(p,expected_bucket_id='prod-bucket-id',now=self.at(3,day=27))['status'],'FAIL')
    def evaluate(self,now,claims):
        return c.evaluate(claims,b'public',pinned_key_id='pin',expected_bucket_id='prod-bucket-id',remote=None,backup_key=b'key',now=now)
    def test_no_evidence(self):
        self.assertEqual(self.evaluate(self.at(15),[])['status'],'NO_VERIFIED_BACKUP')
    def test_rejected_claim(self):
        with patch('prod_backup_authenticated.verify',return_value=dict(status='FAIL',evidence_authenticated=False,remote_verified=False)):
            self.assertEqual(self.evaluate(self.at(15),[{'proof':self.proof()}])['status'],'NO_VERIFIED_BACKUP')
    def test_verified_and_risk(self):
        with patch('prod_backup_authenticated.verify',return_value=dict(status='PASS',evidence_authenticated=True,remote_verified=True)):
            claims=[{'proof':self.proof()}]*2
            result=self.evaluate(self.at(15),claims)
            self.assertEqual(result['status'],'WITHIN_RPO')
            self.assertEqual(result['verified_archives'],1)
            self.assertEqual(self.evaluate(self.at(4,day=27),claims)['status'],'AT_RISK')
            self.assertEqual(self.evaluate(self.at(14,day=27),claims)['status'],'BREACH')
