import unittest
import prod_backup_policy as p


class BackupPolicyTests(unittest.TestCase):
    def setUp(self):
        self.prod=dict(bucket=p.BUCKET,bucket_id='prod-bucket-id',prefix='prod/',
            local_dir='/home/ubuntu/dsig-prod-backups',state_dir='/home/ubuntu/dsig-prod-backup-state',
            credential_id='prod-key-id',bucket_type='allPrivate',encryption='SSE-B2',
            lock_mode='compliance',lock_days=30,local_days=7,remote_days=90,rpo_hours=24,rto_hours=4)
        self.rec=dict(bucket_id='rec-bucket-id',credential_id='rec-key-id',
            local_dir='/home/ubuntu/dsig-backups',state_dir='/home/ubuntu/dsig-b2-automation')
        self.candidate=dict(bucket_id='candidate-bucket-id',credential_id='candidate-key-id',
            local_dir='/home/ubuntu/dsig-prod-candidate-backups',state_dir='/home/ubuntu/dsig-prod-candidate-state')

    def check(self,expected='FAIL'):
        result=p.inspect(self.prod,self.rec,self.candidate)
        self.assertEqual(result['status'],expected)
        self.assertFalse(result['remote_verified'])
        self.assertFalse(result['production_authorized'])

    def test_valid(self):
        self.check('PASS')

    def test_reused_bucket(self):
        self.prod['bucket_id']=self.rec['bucket_id']
        self.check()

    def test_reused_credential(self):
        self.prod['credential_id']=self.candidate['credential_id']
        self.check()

    def test_nested_reference(self):
        self.rec['local_dir']=self.prod['local_dir']+'/old'
        self.check()

    def test_wrong_prefix(self):
        self.prod['prefix']='rec/'
        self.check()

    def test_retention(self):
        for key,value in [('lock_mode','governance'),('lock_days',29),('remote_days',20),
                          ('encryption','none'),('bucket_type','allPublic'),('local_days',True)]:
            old=self.prod[key]
            self.prod[key]=value
            self.check()
            self.prod[key]=old

    def test_recovery(self):
        self.prod['rto_hours']=5
        self.check()

    def test_missing_reference(self):
        del self.rec['bucket_id']
        self.check()
