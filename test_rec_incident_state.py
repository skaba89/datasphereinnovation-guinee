import os
from pathlib import Path
import tempfile
import unittest
from scripts.rec_incident_state import CHECKS, parse_report, transition, record


def report(*failed):
    return {"status": "FAIL" if failed else "PASS",
            "checks": {key: "FAIL" if key in failed else "PASS" for key in CHECKS}}


class IncidentTests(unittest.TestCase):
    def test_healthy_initial(self):
        state, event = transition(None, [], 100)
        self.assertEqual(event, "NONE")

    def test_open_and_deduplicate(self):
        state, event = transition(None, ["api_ready"], 100)
        self.assertEqual(event, "OPEN")
        state, event = transition(state, ["api_ready"], 400)
        self.assertEqual(event, "NONE")
        self.assertEqual(state["last_event"], 100)

    def test_reminder(self):
        state, _ = transition(None, ["api_ready"], 100)
        state, event = transition(state, ["api_ready"], 3700)
        self.assertEqual(event, "REMINDER")
        self.assertEqual(state["opened"], 100)

    def test_changed(self):
        state, _ = transition(None, ["api_ready"], 100)
        state, event = transition(state, ["api_health", "api_ready"], 200)
        self.assertEqual(event, "CHANGED")
        self.assertEqual(state["opened"], 100)

    def test_recovered_and_reopened(self):
        state, _ = transition(None, ["api_ready"], 100)
        state, event = transition(state, [], 200)
        self.assertEqual(event, "RECOVERED")
        state, event = transition(state, [], 300)
        self.assertEqual(event, "NONE")
        state, event = transition(state, ["api_ready"], 400)
        self.assertEqual(event, "OPEN")

    def test_clock_regression(self):
        state, _ = transition(None, ["api_ready"], 100)
        with self.assertRaises(ValueError):
            transition(state, [], 99)

    def test_inconsistent_report(self):
        data = report("api_ready")
        data["status"] = "PASS"
        with self.assertRaises(ValueError):
            parse_report(data)

    def test_incomplete_report(self):
        data = report()
        del data["checks"]["api_ready"]
        with self.assertRaises(ValueError):
            parse_report(data)

    def test_persistent_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self.assertEqual(record(directory, report("api_ready"), 100)["event"], "OPEN")
            self.assertEqual(record(directory, report("api_ready"), 200)["event"], "NONE")
            result = record(directory, report(), 300)
            self.assertEqual(result["event"], "RECOVERED")
            self.assertFalse(result["notification_sent"])
            self.assertEqual((directory/"incident.json").stat().st_mode & 0o777, 0o600)

    def test_refuse_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory/"incident.json").symlink_to("/etc/passwd")
            with self.assertRaises(OSError):
                record(directory, report(), 100)

    def test_refuse_open_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            directory.chmod(0o755)
            with self.assertRaises(ValueError):
                record(directory, report(), 100)
