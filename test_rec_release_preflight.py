import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
from rec_release_bundle import GROUPS, prepare
from rec_release_preflight import verify_bundle, snapshot_b2


class PreflightTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name) / "repo"
        self.repo.mkdir()
        self.out = Path(tmp.name) / "out"
        self.out.mkdir(mode=0o700)
        self.git("init")
        for name in GROUPS["b2"]:
            path = self.repo / name
            path.parent.mkdir(exist_ok=True)
            path.write_text(name)
            path.chmod(0o700)
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "fixture")
        self.commit = self.git("rev-parse", "HEAD").strip()
        self.bundle = self.out / prepare(self.repo, self.commit, self.out, ["b2"])["bundle"]

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                              capture_output=True, text=True).stdout

    def test_valid(self):
        self.assertEqual(set(verify_bundle(self.bundle, self.repo, self.commit)), set(GROUPS["b2"]))

    def test_forged_manifest_and_payload(self):
        import hashlib
        path = GROUPS["b2"][0]
        data = b"tampered"
        (self.bundle / "payload" / path).write_bytes(data)
        manifest = self.bundle / "manifest.json"
        doc = json.loads(manifest.read_text())
        doc["files"][path].update(sha256=hashlib.sha256(data).hexdigest(), size=len(data))
        manifest.write_text(json.dumps(doc))
        with self.assertRaises(ValueError):
            verify_bundle(self.bundle, self.repo, self.commit)

    def test_extra_file(self):
        (self.bundle / "payload" / ".env").write_text("synthetic")
        with self.assertRaises(ValueError):
            verify_bundle(self.bundle, self.repo, self.commit)

    def test_wrong_commit(self):
        with self.assertRaises(ValueError):
            verify_bundle(self.bundle, self.repo, "a"*40)

    def test_symlink(self):
        path = self.bundle / "payload" / GROUPS["b2"][0]
        path.unlink()
        path.symlink_to(self.repo / GROUPS["b2"][0])
        with self.assertRaises(OSError):
            verify_bundle(self.bundle, self.repo, self.commit)

    def test_snapshot(self):
        snapshot = snapshot_b2(self.repo, self.out)
        manifest = json.loads((snapshot / "manifest.json").read_text())
        self.assertEqual(set(manifest["files"]), set(GROUPS["b2"]))
        self.assertFalse(manifest["units_backed_up"])
        for name in GROUPS["b2"]:
            self.assertEqual((snapshot / "payload" / name).read_text(), name)
            self.assertEqual(manifest["files"][name]["original_mode"], 0o700)

    def test_missing_source_refused(self):
        (self.repo / GROUPS["b2"][0]).unlink()
        before = list(self.out.iterdir())
        with self.assertRaises(OSError):
            snapshot_b2(self.repo, self.out)
        self.assertEqual(list(self.out.iterdir()), before)
