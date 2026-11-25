from contextlib import closing
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
from rec_alert_outbox import open_db, observe, deliver_one, send
from rec_incident_state import CHECKS


def report(*failed):
    return {"status": "FAIL" if failed else "PASS",
            "checks": {k: "FAIL" if k in failed else "PASS" for k in CHECKS}}


class OutboxTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory = Path(tmp.name)
        self.db = open_db(self.directory)
        self.addCleanup(self.db.close)

    def count(self):
        return self.db.execute("SELECT count(*) FROM outbox WHERE accepted IS NULL").fetchone()[0]

    def test_observe_and_deduplicate(self):
        self.assertEqual(observe(self.db, report("api_ready"), 100), "OPEN")
        self.assertEqual(observe(self.db, report("api_ready"), 200), "NONE")
        self.assertEqual(self.count(), 1)

    def test_retry_and_ack(self):
        observe(self.db, report("api_ready"), 100)
        transport = Mock(side_effect=OSError)
        self.assertEqual(deliver_one(self.db, 100, transport), "RETRY")
        self.assertEqual(self.count(), 1)
        transport.side_effect = None
        self.assertEqual(deliver_one(self.db, 399, transport), "NONE")
        self.assertEqual(deliver_one(self.db, 400, transport), "SMTP_ACCEPTED")
        self.assertEqual(self.count(), 0)
        self.assertEqual(transport.call_args_list[0], transport.call_args_list[1])

    def test_recovery_order(self):
        observe(self.db, report("api_ready"), 100)
        observe(self.db, report(), 200)
        transport = Mock()
        deliver_one(self.db, 300, transport)
        deliver_one(self.db, 301, transport)
        self.assertEqual([c.args[0][1] for c in transport.call_args_list], ["OPEN", "RECOVERED"])

    def test_persistence(self):
        observe(self.db, report("api_ready"), 100)
        with closing(open_db(self.directory)) as second:
            self.assertEqual(deliver_one(second, 200, Mock()), "SMTP_ACCEPTED")
        self.assertEqual(self.count(), 0)

    def test_invalid_report_no_event(self):
        with self.assertRaises(ValueError):
            observe(self.db, {"status": "PASS", "checks": {}}, 100)
        self.assertEqual(self.count(), 0)

    @patch("rec_alert_outbox.MAX_PENDING", 1)
    def test_full_queue_rolls_back_state(self):
        observe(self.db, report("api_ready"), 100)
        with self.assertRaises(ValueError):
            observe(self.db, report(), 200)
        deliver_one(self.db, 300, Mock())
        self.assertEqual(observe(self.db, report(), 301), "RECOVERED")

    @patch("rec_alert_outbox.smtplib.SMTP_SSL")
    def test_tls_and_stable_message_id(self, client):
        smtp = client.return_value.__enter__.return_value
        smtp.send_message.return_value = {}
        env = {"DSIG_ALERT_SMTP_HOST": "smtp.example.org", "DSIG_ALERT_FROM": "from@example.org",
               "DSIG_ALERT_TO": "to@example.org", "DSIG_ALERT_SMTP_USER": "user",
               "DSIG_ALERT_SMTP_PASSWORD": "secret-test"}
        send(("a"*32, "OPEN", '["api_ready"]', 100), env)
        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message["Message-ID"], "<"+"a"*32+"@dsig-rec.invalid>")
        self.assertNotIn("secret-test", message.as_string())
        smtp.login.assert_called_once_with("user", "secret-test")
