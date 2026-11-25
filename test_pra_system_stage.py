import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
from pra_system_stage import SELECTED, stage


class PraSystemStageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.source = root / "source"
        self.out = root / "out"
        self.source.mkdir(mode=0o700)
        self.out.mkdir(mode=0o700)
        self.marker = self.source / "SHA256SUMS"
        self.lines = []
        for name in sorted(SELECTED):
            p = self.source / name
            p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            p.write_bytes(b"test\n")
            p.chmod(0o600)
            self.lines.append(hashlib.sha256(b"test\n").hexdigest() + "  ./" + name)
        self.write_marker()

    def write_marker(self):
        self.marker.write_text("\n".join(self.lines) + "\n")
        self.marker.chmod(0o600)

    def test_valid(self):
        report = stage(self.source, self.out)
        self.assertEqual((report["units"], report["dropins"], report["clamav_configs"]), (13, 4, 2))
        self.assertFalse(report["installed"])
        self.assertFalse(report["activated"])
        self.assertFalse(report["production_authorized"])
        self.assertEqual((self.out / report["stage"] / "report.json").stat().st_mode & 0o777, 0o600)

    def test_missing(self):
        self.lines.pop()
        self.write_marker()
        with self.assertRaises(ValueError):
            stage(self.source, self.out)
        self.assertFalse(list(self.out.iterdir()))

    def test_tamper(self):
        (self.source / "clamav/clamd.conf").write_text("changed")
        with self.assertRaises(ValueError):
            stage(self.source, self.out)
        self.assertFalse(list(self.out.iterdir()))

    def test_link(self):
        p = self.source / "clamav/clamd.conf"
        p.unlink()
        p.symlink_to("/etc/passwd")
        with self.assertRaises(OSError):
            stage(self.source, self.out)

    def test_extra_unit(self):
        self.lines.append("0"*64 + "  systemd/extra.service")
        self.write_marker()
        with self.assertRaises(ValueError):
            stage(self.source, self.out)

    def test_duplicate(self):
        self.lines.append(self.lines[0])
        self.write_marker()
        with self.assertRaises(ValueError):
            stage(self.source, self.out)

    def test_public_directory(self):
        self.out.chmod(0o755)
        with self.assertRaises(ValueError):
            stage(self.source, self.out)
