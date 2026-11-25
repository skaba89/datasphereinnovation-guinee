import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
from rec_unit_snapshot import REQUIRED, capture


class UnitSnapshotTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.source, self.out = root / "units", root / "out"
        self.source.mkdir(mode=0o700)
        self.out.mkdir(mode=0o700)
        for name in REQUIRED:
            (self.source / name).write_text("[Unit]\nDescription=REC fixture\n")
            (self.source / name).chmod(0o644)

    def snapshot(self):
        result = capture(self.source, self.out, os.getuid())
        path = self.out / result["snapshot"]
        return path, json.loads((path / "manifest.json").read_text())

    def test_units_and_dropins(self):
        directory = self.source / "dsig-rec-b2.service.d"
        directory.mkdir(mode=0o755)
        (directory / "alert.conf").write_text("[Unit]\nOnFailure=example.service\n")
        (directory / "alert.conf").chmod(0o644)
        path, manifest = self.snapshot()
        self.assertEqual(len(manifest["files"]), len(REQUIRED)+1)
        self.assertIn("dsig-rec-outbox-observe.service", manifest["absent"])
        self.assertEqual((path / "payload" / directory.name / "alert.conf").stat().st_mode & 0o777, 0o600)
        self.assertFalse(manifest["effective_config_verified"])

    def test_empty_directory(self):
        name = "dsig-rec-b2.service.d"
        (self.source / name).mkdir()
        _, manifest = self.snapshot()
        self.assertIn(name, manifest["empty_dropin_dirs"])

    def test_missing_required(self):
        (self.source / "dsig-rec-b2.service").unlink()
        with self.assertRaises(ValueError):
            self.snapshot()
        self.assertFalse(list(self.out.iterdir()))

    def test_symlink_refused(self):
        path = self.source / "dsig-rec-b2.service"
        path.unlink()
        path.symlink_to("dsig-rec-backup.service")
        with self.assertRaises(OSError):
            self.snapshot()

    def test_dropin_symlink_refused(self):
        (self.source / "dsig-rec-b2.service.d").symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.snapshot()

    def test_unrelated_files_excluded(self):
        (self.source / "other.service").write_text("other")
        (self.source / "dsig-rec-alert.env").write_text("synthetic secret")
        _, manifest = self.snapshot()
        self.assertEqual(set(manifest["files"]), REQUIRED)

    def test_unsafe_permissions_refused(self):
        (self.source / "dsig-rec-b2.service").chmod(0o666)
        with self.assertRaises(ValueError):
            self.snapshot()
