import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('rec_preflight', Path(__file__).parent/'scripts/rec-preflight.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class RecPreflightTests(unittest.TestCase):
    def test_pass_never_authorizes_production(self):
        sha = 'a'*40
        replies = iter([(True, {'status':'PASS','commit':sha,'production_authorized':False}),
                        (True, {'status':'PASS','production_authorized':False}),
                        (True, {'status':'PASS'}),
                        (True, {'clean':'PASS','eicar_rejected':'PASS'})])
        report = mod.inspect(sha, lambda _: next(replies))
        self.assertEqual(report['technical_status'], 'PASS')
        self.assertFalse(report['production_authorized'])

    def test_fail_closed(self):
        sha = 'a'*40
        replies = iter([(True, {'status':'PASS','commit':'b'*40,'production_authorized':False}),
                        (True, {'status':'WARN','production_authorized':False}),
                        (False, {'status':'PASS'}),
                        (True, {'clean':'PASS','eicar_rejected':'FAIL'})])
        report = mod.inspect(sha, lambda _: next(replies))
        self.assertEqual(report['technical_status'], 'FAIL')
        self.assertEqual(set(report['checks'].values()), {'FAIL'})
        self.assertFalse(report['production_authorized'])

    def test_missing_and_malformed(self):
        self.assertEqual(mod.inspect('a'*40, lambda _: (False,None))['technical_status'], 'FAIL')
        with self.assertRaises(ValueError):
            mod.inspect('main')
