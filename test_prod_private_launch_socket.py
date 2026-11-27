import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import prod_private_launch_socket as launch


class LaunchSocketTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        for p in (
            patch.object(launch.topology, 'HOST_CHANNEL', str(self.path)),
            patch.object(launch.topology, 'CHANNEL', str(self.path)),
            patch.object(launch, '_directory', return_value=self.path),
            patch.object(launch.os, 'chown'),
        ):
            p.start()
            self.addCleanup(p.stop)

    def test_real_socket_and_cleanup(self):
        path = self.path / launch.NAME
        with launch.host_listener() as listener:
            self.assertTrue(path.is_socket())
            self.assertEqual(path.stat().st_mode & 0o777, 0o660)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(2)
                client.connect(str(path))
                conn, _ = listener.accept()
                with conn:
                    client.sendall(b'hello')
                    self.assertEqual(conn.recv(5), b'hello')
        self.assertFalse(path.exists())

    def test_existing_file_never_removed(self):
        path = self.path / launch.NAME
        path.write_text('preserve')
        with self.assertRaises(FileExistsError):
            with launch.host_listener():
                self.fail('unexpected listener')
        self.assertEqual(path.read_text(), 'preserve')

    def test_runtime_rejects_regular_file(self):
        (self.path / launch.NAME).write_text('not a socket')
        with self.assertRaises(ValueError):
            with launch.runtime_connection():
                self.fail('unexpected connection')

    def test_cleanup_on_exception(self):
        with self.assertRaises(RuntimeError):
            with launch.host_listener():
                raise RuntimeError('test')
        self.assertFalse((self.path / launch.NAME).exists())


if __name__ == '__main__':
    unittest.main()
