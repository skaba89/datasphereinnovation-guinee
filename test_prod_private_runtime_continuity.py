import copy
import json
import unittest
from unittest.mock import patch
import prod_private_runtime_continuity as continuity


class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.created = dict(Id='a'*64, Image='sha256:'+'b'*64,
            State='created', Config=dict(Env=['DSIG_ENV=PROD']),
            HostConfig=dict(Privileged=False), Mounts=[dict(Name='prod-data')],
            Networks={continuity.NETWORK: dict(NetworkID='c'*64, EndpointID='',
                IPAddress='', IPPrefixLen=0, Gateway='', GlobalIPv6Address='',
                GlobalIPv6PrefixLen=0, IPv6Gateway='', MacAddress='', Aliases=['app'])})
        self.running = copy.deepcopy(self.created)
        self.running['State'] = 'running'
        self.running['Networks'][continuity.NETWORK].update(
            EndpointID='d'*64, IPAddress='172.20.0.2', IPPrefixLen=16,
            MacAddress='02:42:ac:14:00:02')
        self.pin = continuity.digest(self.created)

    def compare(self):
        return continuity.compare(self.created, self.running, approved_digest=self.pin)

    def test_valid_transition(self):
        self.assertTrue(self.compare())

    def test_configuration_and_mount_changes(self):
        for field in ('Config', 'HostConfig', 'Mounts', 'Image', 'Id'):
            with self.subTest(field=field):
                original = self.running[field]
                self.running[field] = 'changed'
                self.assertFalse(self.compare())
                self.running[field] = original

    def test_network_identity_and_gateway(self):
        network = self.running['Networks'][continuity.NETWORK]
        for field, value in (('NetworkID', 'e'*64), ('Gateway', '172.20.0.1'),
                             ('Aliases', ['other']), ('IPAddress', 'invalid')):
            with self.subTest(field=field):
                original = network[field]
                network[field] = value
                self.assertFalse(self.compare())
                network[field] = original

    def test_approved_digest_required(self):
        self.pin = '0'*64
        self.assertFalse(self.compare())

    def test_actual_inspection_stability(self):
        kw = dict(created=self.created, approved_digest=self.pin, container_id='a'*64)
        with patch.object(continuity.os, 'geteuid', return_value=0):
            with patch.object(continuity.acquisition, 'command', return_value=json.dumps(self.running)):
                result = continuity.inspect(**kw)
                self.assertEqual(result['status'], 'PASS')
                self.assertFalse(result['production_authorized'])
            changed = copy.deepcopy(self.running)
            changed['Config']['Env'].append('OTHER=changed')
            with patch.object(continuity.acquisition, 'command',
                              side_effect=[json.dumps(self.running), json.dumps(changed)]):
                self.assertEqual(continuity.inspect(**kw)['status'], 'FAIL')

    def test_nonroot_refused(self):
        with patch.object(continuity.os, 'geteuid', return_value=10001):
            with patch.object(continuity.acquisition, 'command') as command:
                result = continuity.inspect(created=self.created,
                    approved_digest=self.pin, container_id='a'*64)
                self.assertEqual(result['status'], 'FAIL')
                command.assert_not_called()


if __name__ == '__main__':
    unittest.main()
