import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import prod_private_authority as authority


class AuthorityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        # Exercise filesystem operations with the test user's ownership.
        # Root-only ancestor validation is tested independently.
        self.real_directory = authority._directory
        self.open_dir = patch.object(authority, '_directory',
            side_effect=lambda path: os.open(path, os.O_RDONLY | os.O_DIRECTORY))
        self.open_dir.start()
        self.addCleanup(self.open_dir.stop)
        original_read = authority._read
        def read(fd, name, length):
            # Use actual mode/link/size checks while adapting owner on non-root CI.
            with patch.object(authority.os, 'fstat', side_effect=lambda n:
                    type('Info', (), dict(st_mode=real_fstat(n).st_mode,
                    st_uid=0, st_nlink=real_fstat(n).st_nlink))()):
                return original_read(fd, name, length)
        real_fstat = os.fstat
        self.read = patch.object(authority, '_read', side_effect=read)
        self.read.start()
        self.addCleanup(self.read.stop)

    def test_provision_and_no_overwrite(self):
        report = authority.provision(self.path)
        public = (self.path / 'authority.pub').read_bytes()
        self.assertEqual(report['authority_pin'], hashlib.sha256(public).hexdigest())
        self.assertFalse(report['production_authorized'])
        for p in self.path.iterdir():
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
        before = (self.path / 'authority.key').read_bytes()
        with self.assertRaises(FileExistsError):
            authority.provision(self.path)
        self.assertEqual((self.path / 'authority.key').read_bytes(), before)

    def test_wrong_pin(self):
        authority.provision(self.path)
        with self.assertRaises(ValueError):
            authority.load(self.path, approved_pin='0'*64)

    def test_symlink_key(self):
        report = authority.provision(self.path)
        (self.path / 'authority.key').unlink()
        (self.path / 'authority.key').symlink_to('authority.pub')
        with self.assertRaises(OSError):
            authority.load(self.path, approved_pin=report['authority_pin'])

    def test_nonroot_refused(self):
        with patch.object(authority.os, 'geteuid', return_value=10001):
            with self.assertRaises(PermissionError):
                self.real_directory(self.path)
