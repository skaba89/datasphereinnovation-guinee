import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('notify_rec', Path(__file__).parent / 'scripts' / 'notify-rec.py')
notify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notify)


class NotifyTests(unittest.TestCase):
    def test_authenticated_tls_and_minimal_payload(self):
        env = {'DSIG_ALERT_SMTP_HOST': 'smtp.example.org', 'DSIG_ALERT_FROM': 'from@example.org',
               'DSIG_ALERT_TO': 'to@example.org', 'DSIG_ALERT_SMTP_USER': 'user',
               'DSIG_ALERT_SMTP_PASSWORD': 'private-test'}
        with patch.object(notify.smtplib, 'SMTP_SSL') as client:
            smtp = client.return_value.__enter__.return_value
            smtp.send_message.return_value = {}
            notify.notify('dsig-rec-monitor.service', env)
            self.assertEqual(client.call_args.args[:2], ('smtp.example.org', 465))
            smtp.login.assert_called_once_with('user', 'private-test')
            self.assertNotIn('private-test', smtp.send_message.call_args.args[0].as_string())

    def test_invalid_unit(self):
        with self.assertRaises(ValueError):
            notify.notify('other.service', {})

    def test_missing_configuration(self):
        with self.assertRaises(KeyError):
            notify.notify('test', {})
