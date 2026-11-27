import json
import os
import socket
import unittest
from unittest.mock import patch
import prod_private_peer_binding as binding

@unittest.skipUnless(hasattr(os,'pidfd_open') and hasattr(socket,'SO_PEERCRED'),'Linux pidfd and peer credentials required')
class PeerBindingTest(unittest.TestCase):
    def setUp(self):
        self.a,self.b=socket.socketpair()
        self.addCleanup(self.a.close)
        self.addCleanup(self.b.close)
        self.cid='a'*64
        self.iid='sha256:'+'b'*64
        self.obs=dict(Id=self.cid,Image=self.iid,Running=True,Pid=os.getpid(),StartedAt='generation')
        p=patch.object(binding.acquisition,'command',side_effect=lambda args:json.dumps(self.obs))
        self.command=p.start()
        self.addCleanup(p.stop)
    def inspect(self,uid=None):
        return binding.inspect(self.a,container_id=self.cid,image_id=self.iid,
            expected_uid=os.getuid() if uid is None else uid)
    def test_matching_peer(self):
        result=self.inspect()
        self.assertEqual(result['status'],'PASS')
        self.assertFalse(result['startup_authorized'])
    def test_same_uid_wrong_pid(self):
        self.obs['Pid']+=1
        self.assertEqual(self.inspect()['status'],'FAIL')
    def test_wrong_uid(self):
        self.assertEqual(self.inspect(os.getuid()+1)['status'],'FAIL')
        self.command.assert_not_called()
    def test_stopped(self):
        self.obs['Running']=False
        self.assertEqual(self.inspect()['status'],'FAIL')
    def test_generation_changed(self):
        self.command.side_effect=[json.dumps(self.obs),json.dumps(dict(self.obs,StartedAt='changed'))]
        self.assertEqual(self.inspect()['status'],'FAIL')
