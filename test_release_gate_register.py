from datetime import datetime, timezone
import unittest
from release_evidence import GATES, evaluate, template

SHA='a'*40
NOW=datetime(2026,11,21,12,tzinfo=timezone.utc)

def filled():
    data=template(SHA)
    for item in data['checks'].values():
        item.update(status='PASS',date_utc='2026-11-21T10:00:00Z',reviewer='QA fictif',evidence_ref='preuve-fictive')
    return data

class ReleaseGateRegisterTests(unittest.TestCase):
    def test_template_never_approves(self):
        result=evaluate(template(SHA),SHA,NOW)
        self.assertEqual(result['status'],'NO_GO')
        self.assertEqual(result['declared_pass_count'],0)

    def test_complete_only_review_required(self):
        result=evaluate(filled(),SHA,NOW)
        self.assertEqual(result['declared_pass_count'],len(GATES))
        self.assertEqual(result['status'],'REVIEW_REQUIRED')
        self.assertFalse(result['production_authorized'])
        self.assertNotIn('preuve-fictive',str(result))

    def test_invalid_or_missing_gate(self):
        for change in (
            lambda d:d['checks'].pop(GATES[0]),
            lambda d:d['checks'].update(extra={}),
            lambda d:d['checks'][GATES[0]].update(status='FAIL'),
            lambda d:d['checks'][GATES[0]].update(status='NOT_RUN'),
            lambda d:d['checks'][GATES[0]].update(commit='b'*40),
            lambda d:d['checks'][GATES[0]].update(reviewer=' '),
            lambda d:d['checks'][GATES[0]].update(evidence_ref=''),
            lambda d:d['checks'][GATES[0]].update(date_utc='2027-01-01T00:00:00Z'),
            lambda d:d.update(environment='PROD'),
            lambda d:d.update(commit='b'*40),
        ):
            data=filled()
            change(data)
            self.assertEqual(evaluate(data,SHA,NOW)['status'],'NO_GO')
        self.assertEqual(evaluate(None,SHA,NOW)['status'],'NO_GO')
