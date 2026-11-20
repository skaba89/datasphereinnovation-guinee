import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('release_evidence', Path(__file__).parent / 'scripts' / 'release-evidence.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ReleaseEvidenceTests(unittest.TestCase):
    def test_private_network_binding(self):
        info = {'ports': {'8080/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '8310'}]}}
        self.assertTrue(mod.private_port(info, 8310))
        info['ports']['8080/tcp'][0]['HostIp'] = '0.0.0.0'
        self.assertFalse(mod.private_port(info, 8310))
        self.assertFalse(mod.private_port(None, 8310))

    def test_named_volume_only(self):
        self.assertEqual(mod.data_volume({'mounts': [{'Destination': '/app/data', 'Type': 'volume', 'Name': 'candidate-data'}]}), 'candidate-data')
        self.assertIsNone(mod.data_volume({'mounts': [{'Destination': '/app/data', 'Type': 'bind'}]}))
