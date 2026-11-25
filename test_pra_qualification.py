import hashlib
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timezone
from scripts.pra_qualification import assess, GATES


class QualificationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.now = datetime(2026, 11, 26, tzinfo=timezone.utc)
        self.reg = {"environment": "REC", "commit": "a"*40,
                    "gates": {g: {"status": "NOT_RUN"} for g in GATES}, "timing": None}

    def complete(self):
        for gate in GATES:
            data = gate.encode()
            (self.root / gate).write_bytes(data)
            self.reg["gates"][gate] = {"status": "PASS", "reviewer": "operator",
                                       "file": gate, "sha256": hashlib.sha256(data).hexdigest()}
        self.reg["timing"] = {"snapshot_consistency_utc": "2026-11-25T08:00:00Z",
                              "exercise_start_utc": "2026-11-25T09:00:00Z",
                              "business_recovery_utc": "2026-11-25T10:00:00Z"}

    def test_empty(self):
        result = assess(self.reg, self.root, self.now)
        self.assertEqual(result["decision"], "NO_GO")
        self.assertIsNone(result["observed_rpo_seconds"])

    def test_complete_requires_review(self):
        self.complete()
        result = assess(self.reg, self.root, self.now)
        self.assertEqual(result["decision"], "REVIEW_REQUIRED")
        self.assertEqual(result["observed_rpo_seconds"], 3600)
        self.assertEqual(result["observed_rto_seconds"], 3600)
        self.assertFalse(result["production_authorized"])

    def test_tampered_evidence(self):
        self.complete()
        (self.root / "business_acceptance").write_text("changed")
        result = assess(self.reg, self.root, self.now)
        self.assertIn("business_acceptance", result["missing_or_unverified"])
        self.assertIsNone(result["observed_rto_seconds"])

    def test_path_traversal(self):
        self.complete()
        self.reg["gates"]["kits_verified"]["file"] = "../outside"
        self.assertIn("kits_verified", assess(self.reg, self.root, self.now)["missing_or_unverified"])

    def test_future_timing(self):
        self.complete()
        self.reg["timing"]["business_recovery_utc"] = "2026-11-27T00:00:00Z"
        with self.assertRaises(ValueError):
            assess(self.reg, self.root, self.now)

    def test_target_exceeded(self):
        self.complete()
        self.reg["timing"]["business_recovery_utc"] = "2026-11-25T15:00:00Z"
        self.assertIn("rto_target_exceeded", assess(self.reg, self.root, self.now)["missing_or_unverified"])

    def test_refuse_prod(self):
        self.reg["environment"] = "PROD"
        with self.assertRaises(ValueError):
            assess(self.reg, self.root, self.now)
