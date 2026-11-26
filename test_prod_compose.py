import copy
import unittest
import prod_compose as p

IMAGE = 'dsig.invalid/app@sha256:'+'a'*64


def fixture():
    return {'name':'dsig-prod','volumes':{'prod-data':{'name':'dsig-prod_prod-data'}},
            'networks':{'prod-private':{'name':'dsig-prod_prod-private','internal':True}},
            'services':{'app':dict(profiles=['prod-review'],image=IMAGE,pull_policy='never',
                user='10001:10001',environment=dict(p.ENV,**{k:'fake' for k in p.KEYS}),
                group_add=['109'],ports=[dict(host_ip='127.0.0.1',target=8080,published='8320',protocol='tcp')],
                volumes=[dict(type='volume',source='prod-data',target='/app/data',volume={}),
                         dict(type='bind',source='/run/clamav',target='/run/dsig-clamav',read_only=True)],
                networks={'prod-private':None},read_only=True,tmpfs=['/tmp:rw,noexec,nosuid,nodev,size=64m'],
                cap_drop=['ALL'],security_opt=['no-new-privileges:true'],mem_limit=536870912,
                mem_reservation=134217728,memswap_limit=536870912,cpus=2,pids_limit=128,
                restart='no',logging={'driver':'json-file','options':{'max-size':'10m','max-file':'5'}},
                entrypoint=p.STOP.copy())}}


class ComposeReviewTests(unittest.TestCase):
    def check(self,c,expected='FAIL'):
        r=p.validate(c,IMAGE,8320)
        self.assertEqual(r['status'],expected)
        self.assertFalse(r['production_authorized'])
        self.assertNotIn('fake',str(r))

    def test_valid(self):
        self.check(fixture(),'PASS')

    def test_dangerous_service_overrides(self):
        for key,value in [('privileged',True),('network_mode','host'),('cap_add',['SYS_ADMIN']),
                          ('devices',['/dev/sda']),('pid','host'),('command',['sh']),
                          ('user','0'),('entrypoint',['python','server.py']),('restart','always'),
                          ('image','dsig:latest'),('mem_limit',0),('read_only',False),
                          ('group_add',['0']),('tmpfs',['/tmp'])]:
            with self.subTest(key=key):
                c=fixture();c['services']['app'][key]=value;self.check(c)

    def test_mounts(self):
        for target,key,value in [(0,'source','rec-data'),(0,'read_only',True),
                                 (1,'source','/'),(1,'read_only',False),
                                 (1,'bind',{'create_host_path':True})]:
            c=fixture();c['services']['app']['volumes'][target][key]=value;self.check(c)

    def test_network_and_volume(self):
        c=fixture();c['networks']['prod-private']['internal']=False;self.check(c)
        c=fixture();c['volumes']['prod-data']['external']=True;self.check(c)
        c=fixture();c['networks']['edge']={};self.check(c)

    def test_port_and_environment(self):
        c=fixture();c['services']['app']['ports'][0]['host_ip']='0.0.0.0';self.check(c)
        c=fixture();c['services']['app']['environment']['DSIG_ENV']='REC';self.check(c)
        c=fixture();c['services']['app']['environment']['DSIG_DOCUMENT_PREVIOUS_KEY']='fake';self.check(c)

    def test_prod_token_forbidden(self):
        for token in ('', 'fake'):
            c=fixture();c['services']['app']['environment']['DSIG_ADMIN_TOKEN']=token;self.check(c)

    def test_missing_field(self):
        for k in p.SERVICE_FIELDS:
            c=fixture();del c['services']['app'][k];self.check(c)

    def test_compose_generated_defaults(self):
        for command in (None, []):
            for ipam in (None, {}, {'driver':'default'}, {'config':[]},
                         {'driver':'default','config':[]}):
                c=fixture()
                c['services']['app']['command']=command
                c['networks']['prod-private']['ipam']=ipam
                self.check(c,'PASS')

    def test_nondefault_command_and_ipam(self):
        for command in (['sh'], ['python','server.py'], 'sh'):
            c=fixture();c['services']['app']['command']=command;self.check(c)
        for ipam in ({'driver':'custom'}, {'config':[{'subnet':'10.0.0.0/24'}]},
                     {'options':{'foo':'bar'}}, {'config':[{}]}):
            c=fixture();c['networks']['prod-private']['ipam']=ipam;self.check(c)
