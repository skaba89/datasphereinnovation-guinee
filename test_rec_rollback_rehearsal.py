import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
from rec_release_bundle import GROUPS, prepare
from rec_release_preflight import snapshot_b2
from rec_rollback_rehearsal import rehearse


class RehearsalTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.out = self.root / "out"
        self.out.mkdir(mode=0o700)
        self.git("init")
        for name in GROUPS["b2"]:
            path = self.repo / name
            path.parent.mkdir(exist_ok=True)
            path.write_text("old " + name)
            path.chmod(0o700)
        self.snapshot = snapshot_b2(self.repo, self.out)
        for name in GROUPS["b2"]:
            path = self.repo / name
            path.write_text("new " + name)
            path.chmod(0o644)
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "fixture")
        self.commit = self.git("rev-parse", "HEAD").strip()
        self.bundle = self.out / prepare(self.repo, self.commit, self.out, ["b2"])["bundle"]

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                              capture_output=True, text=True).stdout

    def run_rehearsal(self, **kwargs):
        return rehearse(self.bundle, self.snapshot, self.repo, self.commit, self.out, **kwargs)

    def test_nominal(self):
        report = self.run_rehearsal()
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["rollback_bytes_and_modes_verified"])
        self.assertFalse(report["live_deployment_performed"])
        self.assertFalse(report["systemd_tested"])
        for name in GROUPS["b2"]:
            restored = self.out / report["directory"] / "sandbox" / name
            self.assertEqual(restored.read_text(), "old " + name)
            self.assertEqual(restored.stat().st_mode & 0o777, 0o700)
            self.assertEqual((self.repo / name).read_text(), "new " + name)

    def test_fault_after_each_replacement(self):
        for i in (1, 2, 3):
            with self.subTest(index=i):
                report = self.run_rehearsal(fault_after=i)
                self.assertEqual(report["status"], "INSTALL_FAILED_ROLLBACK_PASS")
                self.assertTrue(report["rollback_bytes_and_modes_verified"])
                self.assertFalse(report["candidate_verified_in_sandbox"])

    def test_corrupt_snapshot(self):
        (self.snapshot / "payload" / GROUPS["b2"][0]).write_text("tamper")
        before = set(self.out.iterdir())
        with self.assertRaises(ValueError):
            self.run_rehearsal()
        self.assertEqual(set(self.out.iterdir()), before)

    def test_corrupt_bundle(self):
        (self.bundle / "payload" / GROUPS["b2"][0]).write_text("tamper")
        with self.assertRaises(ValueError):
            self.run_rehearsal()

    def test_refuse_snapshot_symlink(self):
        path = self.snapshot / "payload" / GROUPS["b2"][0]
        path.unlink()
        path.symlink_to(self.repo / GROUPS["b2"][0])
        with self.assertRaises(OSError):
            self.run_rehearsal()

    def test_refuse_unsafe_mode(self):
        manifest = self.snapshot / "manifest.json"
        doc = json.loads(manifest.read_text())
        doc["files"][GROUPS["b2"][0]]["original_mode"] = 0o777
        manifest.write_text(json.dumps(doc))
        with self.assertRaises(ValueError):
            self.run_rehearsal()
