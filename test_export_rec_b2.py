"""V179: versioned REC -> B2 export, consistent with the daily audit, plus manual qualification.

B2 is simulated in memory (no network, no secret). Clocks are injected; the only os.utime calls set
the proof date a real export would have produced at the simulated time (test clock, never in scripts).
"""
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


exporter = load('dsig_b2_export', 'export-rec-b2.py')
auditor = load('dsig_b2_audit_v179', 'audit-rec-b2.py')
rec_b2 = sys.modules['rec_b2']


def at(day, hour, minute=0):
    return datetime(2026, 11, day, hour, minute, tzinfo=timezone.utc)


class FakeB2:
    def __init__(self):
        self.objects, self.uploads = {}, 0
        self.network_down = self.crash_after_upload = False
        self.bucket = {'bucketName': 'dsig-backup', 'bucketType': 'allPrivate'}

    def __call__(self, args, timeout=600, capture=False):
        if self.network_down:
            raise rec_b2.Failure('B2 injoignable ou délai dépassé')
        if args[1:] == ['bucket', 'get', 'dsig-backup']:
            assert capture
            return json.dumps(self.bucket)
        if args[1:3] == ['file', 'download']:
            obj = args[-2].removeprefix('b2://dsig-backup/')
            if obj not in self.objects:
                raise rec_b2.Failure('commande B2 en échec (code 1)')
            Path(args[-1]).write_bytes(self.objects[obj])
        elif args[1:3] == ['file', 'upload']:
            self.assertion_upload(args)
            self.objects[args[-1]] = Path(args[-2]).read_bytes()
            self.uploads += 1
            if self.crash_after_upload:
                raise KeyboardInterrupt  # process killed between upload and proof
        else:
            raise AssertionError(args)

    @staticmethod
    def assertion_upload(args):
        assert args[3:5] == ['--no-progress', 'dsig-backup'] and args[-1].startswith('rec/'), args


@unittest.skipIf(os.name == 'nt', 'POSIX permissions and flock (CI runs on Linux)')
class ExportTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='dsig-b2-v179-')
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.backups, self.state = root / 'backups', root / 'state'
        self.backups.mkdir(mode=0o700)
        self.state.mkdir(mode=0o700)
        self.backups.chmod(0o700)
        self.state.chmod(0o700)
        self.b2bin = root / 'b2'
        self.b2bin.touch()
        self.b2 = FakeB2()

    def archive(self, stamp, content=b'ENCRYPTED-TEST-ARCHIVE', mode=0o600):
        path = self.backups / f'dsig-rec-{stamp}Z.dsigbak'
        path.write_bytes(content)
        path.chmod(mode)
        return path

    def export(self, mode, now, name=None):
        return exporter.export(mode, now, name, self.backups, self.state, self.b2bin, self.b2)

    def proof(self, path):
        return rec_b2.proof_path(self.state, path.name)

    def set_proof_time(self, path, when):
        os.utime(self.proof(path), (when.timestamp(), when.timestamp()))

    def run_audit(self, now, argv=()):
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return now
        output = io.StringIO()
        with contextlib.ExitStack() as stack:
            for name, value in (('BACKUPS', self.backups), ('STATE', self.state), ('B2', self.b2bin), ('datetime', Clock),
                                ('timer_active', lambda unit: True), ('command', self.b2)):
                stack.enter_context(patch.object(auditor, name, value))
            stack.enter_context(contextlib.redirect_stdout(output))
            try:
                auditor.main(list(argv))
                return True, output.getvalue()
            except (SystemExit, rec_b2.Failure):
                return False, output.getvalue()

    # --- daily cycle -------------------------------------------------------------------------------

    def test_nominal_daily_cycle_export_then_audit(self):
        daily = self.archive('20261126T021500')
        result = self.export('scheduled', at(26, 3, 5))
        self.assertEqual((result['archive'], result['uploaded'], result['proof']), (daily.name, True, 'publiée'))
        self.assertEqual(result['object'], 'rec/2026/11/' + daily.name)
        self.assertEqual(self.proof(daily).read_text(), rec_b2.sha256(daily) + '\n')
        self.assertEqual(self.proof(daily).stat().st_mode & 0o777, 0o600)
        self.set_proof_time(daily, at(26, 3, 6))
        ok, out = self.run_audit(at(26, 4, 5))
        self.assertTrue(ok, out)
        self.assertIn('cycle quotidien REC vers B2 vérifié', out)

    def test_daily_archive_missing(self):
        self.archive('20261126T120000')
        with self.assertRaisesRegex(rec_b2.Failure, 'archive unique'):
            self.export('scheduled', at(26, 3, 5))
        self.assertEqual(self.b2.uploads, 0)

    def test_several_archives_in_daily_window(self):
        self.archive('20261126T021500')
        self.archive('20261126T024000')
        with self.assertRaisesRegex(rec_b2.Failure, 'archive unique'):
            self.export('scheduled', at(26, 3, 5))
        self.assertFalse(self.run_audit(at(26, 4, 5))[0])

    def test_manual_archive_newer_than_daily_is_not_picked_by_the_cycle(self):
        daily = self.archive('20261126T021500', b'DAILY')
        manual = self.archive('20261126T031000', b'MANUAL')
        self.assertEqual(self.export('manual', at(26, 3, 12))['archive'], manual.name)
        self.assertEqual(self.export('scheduled', at(26, 3, 15))['archive'], daily.name)
        self.set_proof_time(daily, at(26, 3, 15))
        ok, out = self.run_audit(at(26, 4, 5))
        self.assertTrue(ok, out)
        self.assertIn(daily.name, out)

    def test_scheduled_before_window_closes_is_refused(self):
        self.archive('20261126T021500')
        with self.assertRaisesRegex(rec_b2.Failure, 'avant 03:00'):
            self.export('scheduled', at(26, 2, 40))

    def test_late_catch_up_exports_but_audit_still_flags_the_day(self):
        daily = self.archive('20261126T021500')
        result = self.export('scheduled', at(26, 9, 0))  # Persistent timer after a reboot
        self.assertFalse(result['in_daily_window'])
        self.set_proof_time(daily, at(26, 9, 1))
        ok, out = self.run_audit(at(26, 9, 30))
        self.assertFalse(ok)
        self.assertIn('fenêtre prévue', out)

    # --- manual qualification ----------------------------------------------------------------------

    def test_manual_qualification_outside_window(self):
        archive = self.archive('20261126T095000')
        self.assertEqual(self.export('manual', at(26, 10, 0))['archive'], archive.name)
        self.set_proof_time(archive, at(26, 10, 1))
        ok, out = self.run_audit(at(26, 10, 5), ['--manual'])
        self.assertTrue(ok, out)
        self.assertIn('cycle quotidien NON validé', out)
        ok, out = self.run_audit(at(26, 10, 5))  # the daily audit is not satisfied by it
        self.assertFalse(ok)
        self.assertIn('archive unique', out)

    def test_manual_explicit_archive(self):
        older = self.archive('20261126T021500', b'A')
        self.archive('20261126T095000', b'B')
        self.assertEqual(self.export('manual', at(26, 10, 0), older.name)['archive'], older.name)
        for bad in ('../etc/passwd', 'dsig-rec-20261126T021500Z.dsigbak.bak'):
            with self.assertRaisesRegex(rec_b2.Failure, 'nom d'):
                self.export('manual', at(26, 10, 0), bad)

    def test_manual_never_moves_an_existing_daily_proof(self):
        daily = self.archive('20261126T021500')
        self.export('scheduled', at(26, 3, 5))
        self.set_proof_time(daily, at(26, 3, 6))
        result = self.export('manual', at(26, 11, 0), daily.name)
        self.assertEqual((result['uploaded'], result['proof']), (False, 'inchangée'))
        self.assertEqual(rec_b2.proof_time(self.proof(daily)), at(26, 3, 6))
        self.assertTrue(self.run_audit(at(26, 11, 5))[0])

    def test_archive_too_old_or_in_future(self):
        self.archive('20261125T090000')
        with self.assertRaisesRegex(rec_b2.Failure, 'trop ancienne'):
            self.export('manual', at(26, 10, 0))
        self.assertFalse(self.run_audit(at(26, 10, 0), ['--manual'])[0])
        self.archive('20261126T230000')
        with self.assertRaisesRegex(rec_b2.Failure, 'futur'):
            self.export('manual', at(26, 10, 0))

    # --- proofs ------------------------------------------------------------------------------------

    def test_proof_absent_incoherent_or_stale(self):
        archive = self.archive('20261126T021500')
        self.b2.objects[rec_b2.object_name(archive.name)] = archive.read_bytes()
        ok, out = self.run_audit(at(26, 4, 5))
        self.assertFalse(ok)
        self.assertIn('preuve B2 absente', out)
        self.proof(archive).write_text('0' * 64 + '\n')
        self.proof(archive).chmod(0o600)
        with self.assertRaisesRegex(rec_b2.Failure, 'incohérente'):
            self.export('scheduled', at(26, 3, 5))
        self.assertEqual(self.proof(archive).read_text(), '0' * 64 + '\n')  # never overwritten
        self.proof(archive).write_text(rec_b2.sha256(archive) + '\n')
        self.set_proof_time(archive, at(25, 3, 10))  # yesterday's proof
        ok, out = self.run_audit(at(26, 4, 5))
        self.assertFalse(ok)
        self.assertIn('fenêtre prévue', out)

    def test_manual_proof_older_than_archive_is_incoherent(self):
        archive = self.archive('20261126T095000')
        self.export('manual', at(26, 10, 0))
        self.set_proof_time(archive, at(26, 9, 0))
        ok, out = self.run_audit(at(26, 10, 5), ['--manual'])
        self.assertFalse(ok)
        self.assertIn('incohérente', out)

    def test_existing_sha256sum_format_proof_is_accepted(self):
        archive = self.archive('20261126T021500')
        self.b2.objects[rec_b2.object_name(archive.name)] = archive.read_bytes()
        self.proof(archive).write_text(f'{rec_b2.sha256(archive)}  {archive.name}\n')
        self.proof(archive).chmod(0o600)
        self.set_proof_time(archive, at(26, 3, 10))
        self.assertTrue(self.run_audit(at(26, 4, 5))[0])

    # --- remote ------------------------------------------------------------------------------------

    def test_remote_sha256_differs_is_never_overwritten(self):
        archive = self.archive('20261126T021500')
        obj = rec_b2.object_name(archive.name)
        self.b2.objects[obj] = b'OTHER-CONTENT'
        with self.assertRaisesRegex(rec_b2.Failure, 'distant différent'):
            self.export('scheduled', at(26, 3, 5))
        self.assertEqual((self.b2.objects[obj], self.b2.uploads), (b'OTHER-CONTENT', 0))
        self.assertFalse(self.proof(archive).exists())

    def test_remote_object_missing_is_uploaded_then_verified(self):
        archive = self.archive('20261126T021500')
        self.assertTrue(self.export('scheduled', at(26, 3, 5))['uploaded'])
        self.assertEqual(self.b2.objects[rec_b2.object_name(archive.name)], archive.read_bytes())
        self.b2.objects.clear()  # deleted remotely afterwards: the audit detects it
        self.set_proof_time(archive, at(26, 3, 6))
        ok, out = self.run_audit(at(26, 4, 5))
        self.assertFalse(ok)

    def test_public_or_unknown_bucket_blocks_upload(self):
        archive = self.archive('20261126T021500')
        for bucket in ({'bucketName': 'dsig-backup', 'bucketType': 'allPublic'}, {'bucketName': 'other', 'bucketType': 'allPrivate'}, None):
            self.b2.bucket = bucket
            with self.assertRaisesRegex(rec_b2.Failure, 'non privé'):
                self.export('scheduled', at(26, 3, 5))
        self.assertEqual((self.b2.uploads, self.proof(archive).exists()), (0, False))

    def test_network_error_writes_no_proof(self):
        archive = self.archive('20261126T021500')
        self.b2.network_down = True
        with self.assertRaisesRegex(rec_b2.Failure, 'injoignable'):
            self.export('scheduled', at(26, 3, 5))
        self.assertFalse(self.proof(archive).exists())
        self.assertEqual(list(self.state.glob('.proof-*')), [])
        self.b2.network_down = False  # the next run recovers on its own
        self.assertEqual(self.export('scheduled', at(26, 3, 30))['proof'], 'publiée')

    def test_resume_after_interrupted_upload(self):
        archive = self.archive('20261126T021500')
        self.b2.crash_after_upload = True
        with self.assertRaises(KeyboardInterrupt):
            self.export('scheduled', at(26, 3, 5))
        self.assertFalse(self.proof(archive).exists())  # uploaded but unproven
        self.b2.crash_after_upload = False
        result = self.export('scheduled', at(26, 3, 20))
        self.assertEqual((result['uploaded'], result['proof'], self.b2.uploads), (False, 'publiée', 1))

    # --- local safety ------------------------------------------------------------------------------

    def test_empty_archive(self):
        self.archive('20261126T021500', b'')
        with self.assertRaisesRegex(rec_b2.Failure, 'vide'):
            self.export('scheduled', at(26, 3, 5))

    def test_wrong_permissions(self):
        self.archive('20261126T021500', mode=0o644)
        with self.assertRaisesRegex(rec_b2.Failure, 'permissions archive'):
            self.export('scheduled', at(26, 3, 5))
        self.backups.joinpath('dsig-rec-20261126T021500Z.dsigbak').chmod(0o600)
        self.state.chmod(0o755)
        with self.assertRaisesRegex(rec_b2.Failure, 'permissions'):
            self.export('scheduled', at(26, 3, 5))
        self.assertFalse(self.run_audit(at(26, 4, 5))[0])

    def test_symlinks_refused(self):
        real = self.archive('20261126T095000')
        link = self.backups / 'dsig-rec-20261126T100000Z.dsigbak'
        link.symlink_to(real)
        with self.assertRaisesRegex(rec_b2.Failure, 'lien symbolique'):
            self.export('manual', at(26, 10, 5), link.name)
        self.assertEqual(self.export('manual', at(26, 10, 5))['archive'], real.name)  # link ignored
        target = self.state / 'elsewhere'
        target.write_text(rec_b2.sha256(real) + '\n')
        target.chmod(0o600)
        self.proof(real).unlink()
        self.proof(real).symlink_to(target)
        self.assertFalse(self.run_audit(at(26, 10, 10), ['--manual'])[0])
        with self.assertRaisesRegex(rec_b2.Failure, 'lien symbolique'):
            self.export('manual', at(26, 10, 10))

    def test_concurrent_export_refused(self):
        self.archive('20261126T021500')
        with exporter.Lock(self.state / '.export.lock', 'busy'):
            with self.assertRaisesRegex(rec_b2.Failure, 'déjà en cours'):
                self.export('scheduled', at(26, 3, 5))
        self.assertEqual(self.b2.uploads, 0)

    def test_running_backup_blocks_export_without_holding_its_lock(self):
        self.archive('20261126T021500')
        lock = self.backups / '.backup.lock'
        with exporter.Lock(lock, 'busy'):
            with self.assertRaisesRegex(rec_b2.Failure, 'sauvegarde locale en cours'):
                self.export('scheduled', at(26, 3, 5))
        self.export('scheduled', at(26, 3, 6))
        with exporter.Lock(lock, 'busy'):  # released after the export: a backup can start
            pass

    def test_cli_requires_an_explicit_mode(self):
        with contextlib.redirect_stderr(io.StringIO()):
            for argv in ([], ['--archive', 'x'], ['--scheduled', '--archive', 'x'], ['--scheduled', '--manual']):
                with self.assertRaises(SystemExit) as raised:
                    exporter.main(argv)
                self.assertEqual(raised.exception.code, 2)


class SystemdTests(unittest.TestCase):
    def unit(self, name):
        return (ROOT / 'deploy' / 'systemd' / name).read_text(encoding='utf-8')

    def test_export_and_audit_sequencing(self):
        export, audit = self.unit('dsig-rec-b2.service'), self.unit('dsig-rec-backup-audit.service')
        self.assertIn('export-rec-b2.py --scheduled', export)
        self.assertIn('OnFailure=dsig-rec-alert@%n.service', export)
        self.assertIn('OnFailure=dsig-rec-alert@%n.service', audit)
        self.assertIn('OnCalendar=*-*-* 02:15:00 UTC', self.unit('dsig-rec-backup.timer'))
        self.assertIn('OnCalendar=*-*-* 03:05:00 UTC', self.unit('dsig-rec-b2.timer'))
        self.assertIn('OnCalendar=*-*-* 04:05:00 UTC', self.unit('dsig-rec-backup-audit.timer'))
        self.assertIn('TimeoutStartSec=2700', export)  # 03:05 + 45 min < 04:00: proof stays in its window
        for text in (export, audit):
            self.assertNotRegex(text, r'(?i)application_key|B2_APPLICATION|keyID')
        notify = (ROOT / 'scripts' / 'notify-rec.py').read_text(encoding='utf-8')
        self.assertIn("'dsig-rec-b2.service'", notify)
        self.assertIn("'dsig-rec-backup-audit.service'", notify)


if __name__ == '__main__':
    unittest.main()
