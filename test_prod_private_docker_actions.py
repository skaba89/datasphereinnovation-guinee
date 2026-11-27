import json
import unittest
from unittest.mock import patch
import prod_private_docker_actions as docker


class DockerActionTests(unittest.TestCase):
    def setUp(self):
        self.cid='a'*64
        self.image='sha256:'+'b'*64
        self.created=dict(Id=self.cid,Image=self.image,State='created',Mounts=[],
            Config={'Labels':{'com.docker.compose.project':'dsig-prod',
                              'com.docker.compose.service':'app'}})
        self.kw=dict(container_id=self.cid,image_id=self.image,
                     approved_digest=docker.continuity.digest(self.created))
        p=patch.object(docker.os,'geteuid',return_value=0)
        self.uid=p.start()
        self.addCleanup(p.stop)
        p=patch.object(docker.acquisition,'command',return_value=json.dumps(self.created))
        self.command=p.start()
        self.addCleanup(p.stop)

    def test_exact_start(self):
        start,_=docker.actions(**self.kw)
        start(self.cid)
        self.assertEqual(self.command.call_args.args[0],['container','start',self.cid])

    def test_wrong_target_no_docker_call(self):
        start,stop=docker.actions(**self.kw)
        for action in (start,stop):
            with self.assertRaises(ValueError):
                action('c'*64)
        self.command.assert_not_called()

    def test_changed_observation_no_start(self):
        start,_=docker.actions(**self.kw)
        self.command.return_value=json.dumps(dict(self.created,State='running'))
        with self.assertRaises(ValueError):
            start(self.cid)
        self.assertEqual(self.command.call_count,1)

    def test_foreign_project_refused(self):
        _,stop=docker.actions(**self.kw)
        self.command.return_value=json.dumps(dict(self.created,Config={'Labels':{
            'com.docker.compose.project':'dsig-rec','com.docker.compose.service':'app'}}))
        with self.assertRaises(ValueError):
            stop(self.cid)
        self.assertEqual(self.command.call_count,1)

    def test_stop_confirmed(self):
        _,stop=docker.actions(**self.kw)
        self.command.side_effect=[json.dumps(dict(self.created,State='running')),
            '',json.dumps(dict(self.created,State='exited'))]
        stop(self.cid)
        self.assertEqual(self.command.call_args_list[1].args[0],
                         ['container','stop','--time','15',self.cid])

    def test_stop_not_confirmed(self):
        _,stop=docker.actions(**self.kw)
        self.command.return_value=json.dumps(dict(self.created,State='running'))
        with self.assertRaises(ValueError):
            stop(self.cid)

    def test_created_needs_no_stop(self):
        _,stop=docker.actions(**self.kw)
        stop(self.cid)
        self.assertEqual(self.command.call_count,1)

    def test_nonroot_refused(self):
        self.uid.return_value=10001
        with self.assertRaises(PermissionError):
            docker.actions(**self.kw)
        self.command.assert_not_called()


if __name__=='__main__':
    unittest.main()
