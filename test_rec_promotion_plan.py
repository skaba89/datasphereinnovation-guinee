import copy
import json
import unittest

from rec_promotion_plan import plan, digest


def raw(value):
    return json.dumps(value, sort_keys=True).encode()


class PromotionPlanTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b = 'a'*40, 'b'*40
        self.old, self.new = 'sha256:'+'c'*64, 'sha256:'+'d'*64
        config = {'name':'dsig-rec', 'services':{'dsig':{
            'image':'dsig-rec-suite:'+self.a, 'read_only':True,
            'cap_drop':['ALL'], 'security_opt':['no-new-privileges:true'],
            'environment':{'DSIG_ENV':'REC','DSIG_HTTPS_ORIGIN':'https://rec.dsig-consulting.com',
                           'DSIG_CLAMD_SOCKET':'/run/dsig-clamav/clamd.ctl'},
            'ports':[{'host_ip':'127.0.0.1','target':8080,'published':'8300'}],
            'networks':{'default':{},'edge':{'aliases':['dsig-rec']}},
            'volumes':[{'type':'volume','source':'data','target':'/app/data'},
                       {'type':'bind','source':'/run/clamav','target':'/run/dsig-clamav','read_only':True}]
        }},'volumes':{'data':{'name':'dsig-rec_dsig-data'}},
        'networks':{'default':{'name':'dsig-rec_default'},'edge':{'name':'edge','external':True}}}
        self.before=raw(config)
        self.active=self.manifest(self.a,self.old,self.before,{})
        config['services']['dsig']['image']='dsig-rec-suite:'+self.b
        self.after=raw(config)
        flags=dict(activation_authorized=False,production_authorized=False,startup_authorized=False)
        self.local=dict(flags,git_commit=self.b,image_id=self.new,baseline_image_id=self.old,
                        qualification_status='LOCAL_PASS',checks=dict.fromkeys(
                        ('local_regression','image_integrity','forward_restore','backward_restore',
                         'sqlite_compatibility','application_startup','business_api_write','business_rollback'),True))
        self.ci=dict(flags,git_commit=self.b,exact_commit_ci_verified=True,run_id=12,branch='main',
                     event='push',workflow='ci.yml',jobs_verified=5,
                     jobs=[{'id':i,'conclusion':'success'} for i in range(5)])
        self.q=dict.fromkeys(('local_regression_verified','image_content_verified','exact_commit_ci_verified',
            'forward_restore_verified','backward_restore_verified','application_startup_verified',
            'business_api_write_verified','business_rollback_verified','revision_label_verified'),True)
        self.q.update(type='isolated_candidate',status='QUALIFIED_INACTIVE',
                      new_release_activation_authorized=False,ci_run_id=12)
        self.candidate=self.manifest(self.b,self.new,self.after,self.q)
        self.report=dict(status='PASS',git_commit=self.b,image_id=self.new,qualification_local=True,
            ci_local=False,revision_required=True,production_authorized=False,
            checks=dict.fromkeys(('source_manifest','immutable_reference','image_identity','content_matches','revision'),'PASS'))
        self.bind()

    def manifest(self,sha,image,config,q):
        return dict(schema_version=1,release_id=sha,release_name='test',environment='REC',
                    git_commit=sha,image_id=image,image_reference='dsig-rec-suite:'+sha,
                    configuration_file='compose.approved.json',configuration_sha256=digest(config),
                    qualification=q,production_authorized=False,startup_authorized=False)

    def bind(self):
        self.q['evidence']={'qualification_sha256':digest(raw(self.local)), 'ci_proof_sha256':digest(raw(self.ci))}

    def run_plan(self):
        result=plan(self.active,self.before,self.candidate,self.after,raw(self.local),raw(self.ci),self.report)
        for flag in ('activation_authorized','activation_executed','startup_authorized','production_authorized','live_state_verified'):
            self.assertIs(result[flag],False)
        return result

    def test_valid_simulation(self):
        self.assertEqual(self.run_plan()['status'],'PASS')

    def test_missing_revision(self):
        self.q['revision_label_verified']=False
        self.assertEqual(self.run_plan()['status'],'FAIL')

    def test_wrong_image(self):
        self.report['image_id']=self.old
        self.assertEqual(self.run_plan()['status'],'FAIL')

    def test_tampered_evidence(self):
        self.local['extra']='tampered'
        self.assertEqual(self.run_plan()['status'],'FAIL')

    def test_wrong_baseline_even_with_hash(self):
        self.local['baseline_image_id']=self.new
        self.bind()
        self.assertEqual(self.run_plan()['status'],'FAIL')

    def test_failed_ci_even_with_hash(self):
        self.ci['jobs'][0]['conclusion']='failure'
        self.bind()
        self.assertEqual(self.run_plan()['status'],'FAIL')

    def test_duplicate_ci_job(self):
        self.ci['jobs'][0]['id']=self.ci['jobs'][1]['id']
        self.bind()
        self.assertEqual(self.run_plan()['status'],'FAIL')

    def test_config_drift_even_with_hash(self):
        config=json.loads(self.after)
        config['services']['dsig']['environment']['OTHER']='changed'
        self.after=raw(config)
        self.candidate['configuration_sha256']=digest(self.after)
        self.assertEqual(self.run_plan()['status'],'FAIL')

    def test_prod_refused(self):
        self.candidate['production_authorized']=True
        self.assertEqual(self.run_plan()['status'],'FAIL')

    def test_extra_manifest_field(self):
        self.candidate['unexpected']=True
        self.assertEqual(self.run_plan()['status'],'FAIL')
