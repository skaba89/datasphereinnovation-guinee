import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('release_gates', Path(__file__).parent / 'scripts' / 'release-gates.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseGateTests(unittest.TestCase):
    def test_complete_and_incomplete(self):
        data = {'commit': 'a'*40, 'gates': {name: {'status': 'PASS', 'evidence': 'ref', 'reviewer': 'qa'} for name in release.GATES}}
        self.assertTrue(release.inspect(data))
        data['gates']['G01']['status'] = 'FAIL'
        self.assertFalse(release.inspect(data))
        data['gates']['G01']['status'] = 'PASS'
        data['gates']['G01']['evidence'] = ''
        self.assertFalse(release.inspect(data))
        del data['gates']['G01']
        self.assertFalse(release.inspect(data))

    def test_invalid_format(self):
        for value in (None, [], {}, {'commit': 'bad'}, {'commit': 'a'*40, 'gates': []}):
            self.assertFalse(release.inspect(value))
