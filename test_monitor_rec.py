import importlib.util
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('monitor_rec', Path(__file__).parent / 'scripts' / 'monitor-rec.py')
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


class MonitorTests(unittest.TestCase):
    def test_recent_private_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            folder.chmod(0o700)
            archive = folder / 'dsig-rec-test.dsigbak'
            archive.write_bytes(b'example')
            archive.chmod(0o600)
            self.assertTrue(monitor.backup_recent(folder, time.time()))
            self.assertFalse(monitor.backup_recent(folder, time.time() + 27 * 3600))
            archive.chmod(0o644)
            self.assertFalse(monitor.backup_recent(folder, time.time()))

    def test_failure_report(self):
        with patch.object(monitor, 'command', return_value=None), patch.object(monitor, 'endpoint', return_value=False), patch.object(monitor, 'backup_recent', return_value=False):
            report = monitor.inspect()
            self.assertEqual(report['status'], 'FAIL')
            self.assertEqual(report['checks']['antivirus_clean_scan'], 'FAIL')
