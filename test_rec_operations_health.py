from contextlib import closing
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
import rec_b2
from rec_alert_outbox import open_db, observe
from rec_incident_state import CHECKS
from rec_operations_health import check_b2, check_outbox, inspect


class OperationsHealthTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.state, self.backups, self.proofs = [root / p for p in ("state", "backups", "proofs")]
        for path in (self.state, self.backups, self.proofs):
            path.mkdir(mode=0o700)
        self.now = datetime(2026, 11, 27, 5, tzinfo=timezone.utc)

    def observation(self, age=0, failed=False):
        report = {"status": "FAIL" if failed else "PASS",
                  "checks": {k: "FAIL" if failed and k == "api_ready" else "PASS" for k in CHECKS}}
        with closing(open_db(self.state)) as db:
            observe(db, report, int(self.now.timestamp()) - age)

    def proof(self, mode="scheduled", day="20261127"):
        archive = self.backups / ("dsig-rec-" + day + "T021500Z.dsigbak")
        archive.write_bytes(b"encrypted synthetic archive")
        archive.chmod(0o600)
        rec_b2.write_proof(self.proofs, archive.name, rec_b2.sha256(archive), mode)
        marker = rec_b2.proof_path(self.proofs, archive.name, mode)
        stamp = datetime.strptime(day + "031000", "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc).timestamp()
        os.utime(marker, (stamp, stamp))
        return archive

    def test_healthy(self):
        self.observation()
        self.proof()
        result = inspect(self.state, self.backups, self.proofs, self.now)
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["remote_b2_verified"])
        self.assertFalse(result["production_authorized"])

    def test_missing_database_not_created(self):
        result = inspect(self.state, self.backups, self.proofs, self.now)
        self.assertEqual(result["checks"]["outbox_readable"], "FAIL")
        self.assertFalse((self.state / "outbox.sqlite3").exists())

    def test_stale_and_pending(self):
        self.observation(age=901, failed=True)
        checks, metrics = check_outbox(self.state, self.now)
        self.assertEqual(checks["monitor_freshness"], "FAIL")
        self.assertEqual(checks["pending_age"], "FAIL")
        self.assertEqual(metrics["pending"], 1)

    def test_manual_proof_not_accepted(self):
        self.proof("manual")
        self.assertEqual(check_b2(self.backups, self.proofs, self.now)[0], "FAIL")

    def test_tamper(self):
        self.proof().write_bytes(b"changed")
        self.assertEqual(check_b2(self.backups, self.proofs, self.now)[0], "FAIL")

    def test_previous_cycle_before_cutoff(self):
        self.proof(day="20261126")
        now = self.now.replace(hour=4, minute=10)
        self.assertEqual(check_b2(self.backups, self.proofs, now), ("PASS", "20261126"))

    def test_read_only(self):
        self.observation()
        path = self.state / "outbox.sqlite3"
        before = path.read_bytes()
        check_outbox(self.state, self.now)
        self.assertEqual(path.read_bytes(), before)
