"""Tests isolés de l'audit quotidien DSIG REC vers Backblaze B2."""

import contextlib
import hashlib
import importlib.util
import io
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parent / "scripts/audit-rec-b2.py"

spec = importlib.util.spec_from_file_location("dsig_b2_audit", SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

DAY = "20261126"
NAME = f"dsig-rec-{DAY}T021500Z.dsigbak"
CONTENT = b"DSIG-ISOLATED-TEST-DATA"
DIGEST = hashlib.sha256(CONTENT).hexdigest()


class FixedClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(
            2026, 11, 26, 3, 35,
            tzinfo=timezone.utc,
        )


class TestDailyB2Audit(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(
            prefix="dsig-audit-unittest-"
        )
        self.addCleanup(self.tmp.cleanup)

        root = Path(self.tmp.name)

        self.backups = root / "backups"
        self.state = root / "state"

        self.backups.mkdir(mode=0o700)
        self.state.mkdir(mode=0o700)

        self.archive = self.backups / NAME
        self.archive.write_bytes(CONTENT)
        self.archive.chmod(0o600)

        self.marker = self.state / (NAME + ".sha256")
        self.marker.write_text(DIGEST + "\n")
        self.marker.chmod(0o600)

        timestamp = datetime(
            2026, 11, 26, 3, 10,
            tzinfo=timezone.utc,
        ).timestamp()

        os.utime(self.marker, (timestamp, timestamp))

        self.remote = root / "remote.dsigbak"
        self.remote.write_bytes(CONTENT)

        self.b2 = root / "b2"
        self.b2.touch()

        self.timer_enabled = True

    def fake_timer(self, name):
        return self.timer_enabled

    def fake_command(self, args, timeout=60):
        if "file" in args and "download" in args:
            if not self.remote.is_file():
                audit.fail("objet B2 inaccessible")

            shutil.copyfile(self.remote, args[-1])
            return ""

        raise AssertionError("Commande inattendue")

    def execute(self, should_succeed, **kwargs):
        output = io.StringIO()

        with contextlib.ExitStack() as stack:
            stack.enter_context(
                patch.object(audit, "BACKUPS", self.backups)
            )
            stack.enter_context(
                patch.object(audit, "STATE", self.state)
            )
            stack.enter_context(
                patch.object(audit, "B2", self.b2)
            )
            stack.enter_context(
                patch.object(audit, "datetime", FixedClock)
            )
            stack.enter_context(
                patch.object(audit, "timer_active", self.fake_timer)
            )
            stack.enter_context(
                patch.object(audit, "command", self.fake_command)
            )
            stack.enter_context(
                contextlib.redirect_stdout(output)
            )

            if should_succeed:
                audit.audit(**kwargs)
            else:
                with self.assertRaises(SystemExit) as raised:
                    audit.audit(**kwargs)

                self.assertEqual(raised.exception.code, 1)
                self.assertIn("FAIL:", output.getvalue())

    def test_01_valid_cycle(self):
        self.execute(True)

    def test_02_missing_archive(self):
        self.archive.unlink()
        self.execute(False)

    def test_03_empty_archive(self):
        self.archive.write_bytes(b"")
        self.execute(False)

    def test_04_wrong_sha256(self):
        self.marker.write_text("0" * 64 + "\n")
        self.execute(False)

    def test_05_stale_marker(self):
        timestamp = datetime(
            2026, 11, 25, 3, 10,
            tzinfo=timezone.utc,
        ).timestamp()

        os.utime(self.marker, (timestamp, timestamp))
        self.execute(False)

    def test_06_inactive_timer(self):
        self.timer_enabled = False
        self.execute(False)

    def test_07_missing_remote_object(self):
        self.remote.unlink()
        self.execute(False)

    def test_08_corrupted_remote_object(self):
        self.remote.write_bytes(b"CORRUPTED")
        self.execute(False)

    def test_09_multiple_archives(self):
        other = self.backups / (
            f"dsig-rec-{DAY}T022000Z.dsigbak"
        )
        other.write_bytes(CONTENT)
        other.chmod(0o600)
        self.execute(False)


    def test_manual_explicit(self):
        stamp = datetime(2026, 11, 26, 2, 15, tzinfo=timezone.utc).timestamp()
        os.utime(self.archive, (stamp, stamp))
        self.execute(True, manual=True, archive_name=NAME)

    def test_manual_traversal(self):
        self.execute(False, manual=True, archive_name="../" + NAME)

    def test_daily_ignores_manual_archive(self):
        other = self.backups / f"dsig-rec-{DAY}T031000Z.dsigbak"
        other.write_bytes(CONTENT)
        other.chmod(0o600)
        self.execute(True)

    def test_missing_marker(self):
        self.marker.unlink()
        self.execute(False)

    def test_open_permissions(self):
        self.archive.chmod(0o644)
        self.execute(False)

    def test_symlink_marker(self):
        self.marker.unlink()
        self.marker.symlink_to(self.remote)
        self.execute(False)


if __name__ == "__main__":
    unittest.main()
