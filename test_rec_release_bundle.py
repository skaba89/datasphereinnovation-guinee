import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from scripts.rec_release_bundle import GROUPS, selected, prepare


class ReleaseBundleTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.repo = root / "repo"
        self.repo.mkdir()
        self.out = root / "out"
        self.out.mkdir(mode=0o700)
        self.git("init")
        for path in selected(list(GROUPS)):
            target = self.repo / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.encode())
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "commit", "-m", "fixture")
        self.commit = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args],
                              check=True, capture_output=True, text=True).stdout

    def test_selective_b2(self):
        report = prepare(self.repo, self.commit, self.out, ["b2"])
        self.assertEqual(set(report["files"]), set(GROUPS["b2"]))
        self.assertFalse(report["installed"])
        self.assertFalse(report["production_authorized"])
        folder = self.out / report["bundle"]
        for path, info in report["files"].items():
            file = folder / "payload" / path
            self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(), info["sha256"])
            self.assertEqual(file.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads((folder / "manifest.json").read_text())["status"], "STAGED_ONLY")

    def test_all_nested_directories_private_with_permissive_umask(self):
        previous = os.umask(0o022)
        try:
            report = prepare(self.repo, self.commit, self.out, list(GROUPS))
        finally:
            os.umask(previous)
        folder = self.out / report["bundle"]
        for directory in [folder] + [p for p in folder.rglob("*") if p.is_dir()]:
            self.assertEqual(directory.stat().st_mode & 0o777, 0o700, str(directory))

    def test_dependencies(self):
        with self.assertRaises(ValueError):
            selected(["health"])

    def test_refuse_unknown_component(self):
        with self.assertRaises(ValueError):
            selected(["prod"])

    def test_refuse_mutable_ref(self):
        with self.assertRaises(ValueError):
            prepare(self.repo, "HEAD", self.out, ["b2"])

    def test_worktree_changes_not_packaged(self):
        path = GROUPS["b2"][0]
        (self.repo / path).write_text("local changes")
        (self.repo / ".env").write_text("secret")
        report = prepare(self.repo, self.commit, self.out, ["b2"])
        folder = self.out / report["bundle"] / "payload"
        self.assertEqual((folder / path).read_bytes(), path.encode())
        self.assertFalse((folder / ".env").exists())

    def test_private_output_required(self):
        self.out.chmod(0o755)
        with self.assertRaises(ValueError):
            prepare(self.repo, self.commit, self.out, ["b2"])

    def test_refuse_symlink_in_commit(self):
        path = self.repo / GROUPS["b2"][0]
        path.unlink()
        path.symlink_to("/etc/passwd")
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "commit", "-m", "symlink")
        commit = self.git("rev-parse", "HEAD").strip()
        with self.assertRaises(ValueError):
            prepare(self.repo, commit, self.out, ["b2"])
        self.assertFalse(list(self.out.iterdir()))
