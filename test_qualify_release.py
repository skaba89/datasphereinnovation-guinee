import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path

from release_evidence import template

spec = importlib.util.spec_from_file_location('qualify_release', Path(__file__).parent/'scripts/qualify-release.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
SHA = 'a'*40
NOW = datetime(2026,11,21,12,tzinfo=timezone.utc)


def fixtures():
    preflight = {'commit':SHA,'timestamp_utc':'2026-11-21T11:00:00+00:00','production_authorized':False,
                 'technical_status':'PASS','checks':dict.fromkeys(('release','preflight','monitor','antivirus'),'PASS')}
    register = template(SHA)
    for item in register['checks'].values():
        item.update(status='PASS',date_utc='2026-11-21T10:00:00Z',reviewer='private-reviewer',evidence_ref='private-evidence')
    gates = {'commit':SHA,'gates':{name:{'status':'PASS','evidence':'private-evidence','reviewer':'private-reviewer'} for name in module.gates.GATES}}
    return preflight, register, gates


class QualificationTests(unittest.TestCase):
    def test_complete_is_review_only_and_redacted(self):
        report = module.qualify(SHA,*fixtures(),now=NOW)
        self.assertEqual(report['status'],'REVIEW_REQUIRED')
        self.assertFalse(report['production_authorized'])
        self.assertEqual(len(report['gates']),10)
        self.assertEqual(len(report['register']),18)
        self.assertNotIn('private-',str(report))

    def test_reject_missing_stale_or_failed_evidence(self):
        for change in (
            lambda p,r,g:p.update(commit='b'*40),
            lambda p,r,g:p.update(timestamp_utc='2026-11-20T11:00:00Z'),
            lambda p,r,g:p.update(timestamp_utc='2026-11-21T13:00:00Z'),
            lambda p,r,g:p.update(timestamp_utc='2026-11-21T11:00:00'),
            lambda p,r,g:p.update(production_authorized=True),
            lambda p,r,g:p['checks'].update(antivirus='FAIL'),
            lambda p,r,g:p['checks'].pop('monitor'),
            lambda p,r,g:r['checks']['backup_offsite_restore'].update(status='NOT_RUN'),
            lambda p,r,g:g['gates']['G04'].update(status='NOT_RUN'),
            lambda p,r,g:g['gates'].update(extra={}),
            lambda p,r,g:g.update(commit='b'*40),
        ):
            args = fixtures()
            change(*args)
            with self.subTest(change=change):
                self.assertEqual(module.qualify(SHA,*args,now=NOW)['status'],'NO_GO')
        self.assertEqual(module.qualify(SHA,None,None,None,now=NOW)['status'],'NO_GO')
