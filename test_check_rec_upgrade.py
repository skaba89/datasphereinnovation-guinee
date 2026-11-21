import copy
import importlib.util
import unittest
from pathlib import Path

from test_rec_config import configuration

spec = importlib.util.spec_from_file_location('check_rec_upgrade',Path(__file__).parent/'scripts/check-rec-upgrade.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
SHA = 'a'*40


def configs():
    before = configuration()
    before['networks'] = {'default':{'name':'dsig-rec_default'},'edge':{'name':'edge','external':True}}
    app = before['services']['dsig']
    app['networks'] = {'default':None,'edge':None}
    app['environment']['DSIG_HTTPS_ORIGIN'] = 'https://rec.dsig-consulting.com'
    app['image'] = 'dsig-rec-previous'
    after = copy.deepcopy(before)
    after['services']['dsig']['image'] = 'dsig-rec-candidate:'+SHA
    return before,after


class UpgradeChecks(unittest.TestCase):
    def test_only_image_changes(self):
        report = module.check(*configs(),SHA)
        self.assertEqual(report['status'],'PASS')
        self.assertFalse(report['production_authorized'])
        self.assertNotIn('fictional',str(report))

    def test_configuration_drift_refused(self):
        for change in (
            lambda c:c['services']['dsig']['environment'].update(DSIG_ADMIN_TOKEN='changed'),
            lambda c:c['services']['dsig']['ports'][0].update(published='8310'),
            lambda c:c['services']['dsig']['environment'].update(DSIG_HTTPS_ORIGIN='https://other.invalid'),
            lambda c:c['services']['dsig'].update(image='unknown:latest'),
            lambda c:c['services']['dsig']['networks'].pop('edge'),
            lambda c:c['networks']['edge'].update(external=False),
            lambda c:c['volumes']['dsig-data'].update(name='other-data'),
            lambda c:c['services'].update(other={}),
        ):
            before,after = configs()
            change(after)
            self.assertEqual(module.check(before,after,SHA)['status'],'FAIL')
        self.assertEqual(module.check(*configs(),'bad')['status'],'FAIL')
        self.assertEqual(module.check(None,None,SHA)['status'],'FAIL')
