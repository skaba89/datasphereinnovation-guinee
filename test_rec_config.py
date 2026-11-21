import copy
import unittest
from verify_rec_config import validate

def configuration():
    return {'name':'dsig-rec','volumes':{'dsig-data':{'name':'dsig-rec_dsig-data'}},'services':{'dsig':{
        'environment':{'DSIG_ENV':'REC','DSIG_CLAMD_SOCKET':'/run/dsig-clamav/clamd.ctl','DSIG_ADMIN_TOKEN':'fictional'},
        'ports':[{'host_ip':'127.0.0.1','target':8080,'published':'8300'}],
        'read_only':True,'cap_drop':['ALL'],'security_opt':['no-new-privileges:true'],
        'volumes':[{'type':'volume','source':'dsig-data','target':'/app/data'},
            {'type':'bind','source':'/run/clamav','target':'/run/dsig-clamav','read_only':True,'bind':{'create_host_path':False}}]
    }}}

class RecConfigTests(unittest.TestCase):
    def test_valid(self):
        result=validate(configuration(),'rec','dsig-rec_dsig-data')
        self.assertEqual(result['status'],'PASS')
        self.assertFalse(result['production_authorized'])
        self.assertNotIn('fictional',str(result))

    def test_reject_unsafe_configurations(self):
        for label,change in (
            ('public port',lambda c:c['services']['dsig']['ports'][0].update(host_ip='0.0.0.0')),
            ('production',lambda c:c['services']['dsig']['environment'].update(DSIG_ENV='PROD')),
            ('root',lambda c:c['services']['dsig'].update(user='0')),
            ('privileged',lambda c:c['services']['dsig'].update(privileged=True)),
            ('host networking',lambda c:c['services']['dsig'].update(network_mode='host')),
            ('writable root',lambda c:c['services']['dsig'].update(read_only=False)),
            ('wrong volume',lambda c:c['volumes']['dsig-data'].update(name='prod-data')),
            ('docker socket',lambda c:c['services']['dsig']['volumes'].append({'type':'bind','source':'/var/run/docker.sock','target':'/var/run/docker.sock'})),
            ('writable scanner',lambda c:c['services']['dsig']['volumes'][1].update(read_only=False)),
            ('wrong project',lambda c:c.update(name='prod')),
        ):
            with self.subTest(label=label):
                c=configuration()
                change(c)
                self.assertEqual(validate(c,'rec','dsig-rec_dsig-data')['status'],'FAIL')
    def test_malformed(self):
        for c in (None,{},[],{'services':None}):
            self.assertEqual(validate(c,'rec','dsig-rec_dsig-data')['status'],'FAIL')

    def test_candidate_profile(self):
        c=copy.deepcopy(configuration())
        c['name']='dsig-prod-candidate'
        c['services']['candidate']=c['services'].pop('dsig')
        c['volumes']['dsig-data']['name']='dsig-prod-candidate_candidate-data'
        self.assertEqual(validate(c,'candidate','dsig-prod-candidate_candidate-data')['status'],'PASS')
