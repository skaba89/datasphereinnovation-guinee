import unittest
from datetime import datetime, timezone
import prod_backup_monitor as p


class BackupMonitorTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,27,3,0,tzinfo=timezone.utc)
        self.proof=dict(schema=1,kind='business-daily',archive='dsig-prod-20261127T011500Z.dsigbak',
            object='prod/2026/11/dsig-prod-20261127T011500Z.dsigbak',sha256='a'*64,
            bucket_id='prod-bucket-id',verified_at='2026-11-27T02:25:00+00:00',
            qualification_only=False,synthetic_data=False,ephemeral_key=False,
            remote_restore_verified=True,daily_backup_qualified=True,production_authorized=False)

    def check(self,expected='FAIL'):
        result=p.evaluate(self.proof,expected_bucket_id='prod-bucket-id',now=self.now)
        self.assertEqual(result['status'],expected)
        self.assertFalse(result['remote_verified'])
        self.assertFalse(result['evidence_authenticated'])
        self.assertFalse(result['production_authorized'])

    def test_valid_claim(self):
        self.check('PASS')

    def test_review_kind(self):
        self.proof['kind']='isolated-review'
        self.check()

    def test_synthetic_flags(self):
        for key in ('qualification_only','synthetic_data','ephemeral_key'):
            self.proof[key]=True
            self.check()
            self.proof[key]=False

    def test_known_synthetic(self):
        self.proof['archive']='dsig-prod-20261126T100822Z.dsigbak'
        self.check()

    def test_wrong_bucket(self):
        self.proof['bucket_id']='rec-bucket-id'
        self.check()

    def test_expired(self):
        self.now=datetime(2026,11,28,3,0,tzinfo=timezone.utc)
        self.check()

    def test_future_verification(self):
        self.proof['verified_at']='2026-11-27T04:00:00+00:00'
        self.check()

    def test_late_cycle(self):
        self.now=datetime(2026,11,27,5,0,tzinfo=timezone.utc)
        self.proof['verified_at']='2026-11-27T04:00:00+00:00'
        self.check()

    def test_missing_restore(self):
        self.proof['remote_restore_verified']=False
        self.check()

    def test_missing_fields(self):
        del self.proof['synthetic_data']
        self.check()

    def test_utc_offset(self):
        self.proof['verified_at']='2026-11-27T03:25:00+01:00'
        self.check('PASS')

    def test_offset_disguises_late_verification(self):
        self.now=datetime(2026,11,27,5,0,tzinfo=timezone.utc)
        self.proof['verified_at']='2026-11-27T02:25:00-02:00'
        self.check()

    def test_naive_clock(self):
        self.now=self.now.replace(tzinfo=None)
        self.check()

    def test_naive_verification(self):
        self.proof['verified_at']='2026-11-27T02:25:00'
        self.check()

    def test_exact_rpo(self):
        self.now=datetime(2026,11,28,1,15,tzinfo=timezone.utc)
        self.check('PASS')
        self.now=self.now.replace(second=1)
        self.check()

    def test_snapshot_window_end(self):
        self.proof['archive']='dsig-prod-20261127T020500Z.dsigbak'
        self.proof['object']='prod/2026/11/'+self.proof['archive']
        self.check()

    def test_early_export(self):
        self.proof['verified_at']='2026-11-27T02:04:59+00:00'
        self.check()

    def test_late_snapshot_in_window(self):
        self.proof['archive']='dsig-prod-20261127T020400Z.dsigbak'
        self.proof['object']='prod/2026/11/'+self.proof['archive']
        self.check('PASS')
