import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
from scripts.pra_restore import isolation_args, private_input, require_empty_host


class PraRestoreTests(unittest.TestCase):
    def test_isolation(self):
        args = isolation_args("dsig-pra-" + "a"*32, "sha256:"+"b"*64)
        for flag in ("--read-only", "--rm", "--cap-drop", "--security-opt"):
            self.assertIn(flag, args)
        self.assertEqual(args[args.index("--network")+1], "none")
        self.assertEqual(args[args.index("--pull")+1], "never")
        for flag in ("-p", "--publish", "-v", "--volume", "--mount", "--privileged"):
            self.assertNotIn(flag, args)

    def test_reject_active_name(self):
        with self.assertRaises(ValueError):
            isolation_args("dsig-rec-dsig-1", "sha256:"+"b"*64)

    def test_reject_mutable_tag(self):
        with self.assertRaises(ValueError):
            isolation_args("dsig-pra-"+"a"*32, "dsig:latest")

    def test_private_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"backup"
            path.write_bytes(b"test")
            path.chmod(0o600)
            digest = hashlib.sha256(b"test").hexdigest()
            private_input(path, digest)
            with self.assertRaises(ValueError):
                private_input(path, "0"*64)
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                private_input(path, digest)
            link = Path(tmp)/"link"
            link.symlink_to(path)
            with self.assertRaises(OSError):
                private_input(link, digest)

    @patch("scripts.pra_restore.docker")
    def test_refuse_containers(self, docker):
        docker.return_value = Mock(stdout=b"existing\n")
        with self.assertRaises(ValueError):
            require_empty_host()

    @patch("scripts.pra_restore.docker")
    def test_refuse_volumes(self, docker):
        docker.side_effect = [Mock(stdout=b""), Mock(stdout=b"existing\n")]
        with self.assertRaises(ValueError):
            require_empty_host()

    @patch("scripts.pra_restore.docker")
    def test_refuse_custom_network(self, docker):
        docker.side_effect = [Mock(stdout=b""), Mock(stdout=b""), Mock(stdout=b"bridge\nedge\n")]
        with self.assertRaises(ValueError):
            require_empty_host()
