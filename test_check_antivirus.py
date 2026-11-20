import os
import unittest
from unittest.mock import patch
import antivirus
import check_antivirus


class AntivirusAcceptanceTests(unittest.TestCase):
    @patch.dict(os.environ, {'DSIG_ENV': 'REC'})
    def test_clean_and_detection(self):
        with patch.object(antivirus, 'scan', side_effect=[None, antivirus.Infected()]) as scan:
            self.assertEqual(check_antivirus.inspect(), {'clean': 'PASS', 'eicar_rejected': 'PASS'})
            self.assertEqual(scan.call_count, 2)
            self.assertEqual(len(check_antivirus.EICAR), 68)

    @patch.dict(os.environ, {'DSIG_ENV': 'REC'})
    def test_unavailable_or_no_detection(self):
        with patch.object(antivirus, 'scan', side_effect=[antivirus.Unavailable(), None]):
            self.assertEqual(check_antivirus.inspect(), {'clean': 'FAIL', 'eicar_rejected': 'FAIL'})

    @patch.dict(os.environ, {'DSIG_ENV': 'PROD'})
    def test_not_rec(self):
        with patch.object(antivirus, 'scan') as scan:
            self.assertEqual(check_antivirus.inspect(), {'clean': 'FAIL', 'eicar_rejected': 'FAIL'})
            scan.assert_not_called()
