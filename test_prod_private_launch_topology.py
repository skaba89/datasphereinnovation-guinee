import unittest
import prod_private_launch_topology as launch
import prod_compose
from test_prod_compose import fixture,IMAGE

def proposed():
    c=fixture()
    s=c['services']['app']
    s['entrypoint']=launch.ENTRYPOINT.copy()
    s['profiles']=['prod-private-launch']
    s['volumes'].append(dict(type='bind',source=launch.HOST_CHANNEL,target=launch.CHANNEL,
        read_only=True,bind={'create_host_path':False}))
    return c

class LaunchTopologyTests(unittest.TestCase):
    def test_distinct_contract(self):
        c=proposed()
        r=launch.validate(c,IMAGE)
        self.assertEqual(r['status'],'PASS')
        self.assertFalse(r['startup_authorized'])
        self.assertFalse(r['production_authorized'])
        self.assertEqual(prod_compose.validate(c,IMAGE,8320)['status'],'FAIL')
        self.assertEqual(launch.validate(fixture(),IMAGE)['status'],'FAIL')

    def test_channel_constraints(self):
        for key,value in [('source','/'),('read_only',False),('bind',{'create_host_path':True})]:
            c=proposed()
            c['services']['app']['volumes'][-1][key]=value
            self.assertEqual(launch.validate(c,IMAGE)['status'],'FAIL')

    def test_preserves_review_guards(self):
        for key,value in [('privileged',True),('user','0'),('restart','always'),('command',['sh'])]:
            c=proposed()
            c['services']['app'][key]=value
            self.assertEqual(launch.validate(c,IMAGE)['status'],'FAIL')
        self.assertEqual(launch.validate(proposed(),IMAGE,8310)['status'],'FAIL')
        c=proposed()
        c['services']['app']['environment']['DSIG_ADMIN_TOKEN']='synthetic'
        self.assertEqual(launch.validate(c,IMAGE)['status'],'FAIL')

if __name__=='__main__':
    unittest.main()
