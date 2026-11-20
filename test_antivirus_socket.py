"""REC tests of the INSTREAM wire protocol, without a production scanner.

The local peer emulates clamd responses; it does not detect malware.
An optional real-daemon smoke test requires DSIG_TEST_CLAMD_SOCKET.
"""
import os
import socket
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch

import antivirus


@unittest.skipUnless(hasattr(socket, 'AF_UNIX'), 'Unix sockets required')
class AntivirusSocketTests(unittest.TestCase):
    def exchange(self, response, expected=None, payload=b'fictional document'):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'scan.sock')
            received, errors = [], []
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
                listener.bind(path)
                listener.listen(1)
                listener.settimeout(3)

                def read_exact(conn, size):
                    data = bytearray()
                    while len(data) < size:
                        part = conn.recv(size - len(data))
                        if not part:
                            raise EOFError('unexpected EOF')
                        data.extend(part)
                    return bytes(data)

                def peer():
                    try:
                        with listener.accept()[0] as conn:
                            conn.settimeout(3)
                            self.assertEqual(read_exact(conn, 10), b'zINSTREAM\0')
                            while True:
                                size = struct.unpack('!I', read_exact(conn, 4))[0]
                                if not size:
                                    break
                                self.assertLessEqual(size, 65536)
                                received.append(read_exact(conn, size))
                            for part in response:
                                conn.sendall(part)
                    except Exception as exc:
                        errors.append(exc)

                worker = threading.Thread(target=peer, daemon=True)
                worker.start()
                try:
                    with patch.dict(os.environ, {'DSIG_CLAMD_SOCKET': path}):
                        if expected is None:
                            antivirus.scan(payload)
                        else:
                            with self.assertRaises(expected):
                                antivirus.scan(payload)
                finally:
                    worker.join(4)
                self.assertFalse(worker.is_alive())
                self.assertFalse(errors, errors)
                self.assertEqual(b''.join(received), payload)

    def test_multichunk_clean_document(self):
        self.exchange([b'stream: ', b'OK\0'], payload=b'A' * 150000)

    def test_infected_document(self):
        self.exchange([b'stream: Fictional.Test FOUND\0'], antivirus.Infected)

    def test_fail_closed_on_error_or_truncated_response(self):
        for response in ([b'stream: ERROR\0'], [b'stream: OK'], [], [b'unknown\0']):
            with self.subTest(response=response):
                self.exchange(response, antivirus.Unavailable)

    def test_missing_socket_and_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {'DSIG_CLAMD_SOCKET': os.path.join(directory, 'absent.sock')}):
                with self.assertRaises(antivirus.Unavailable):
                    antivirus.scan(b'fictional document')
        self.exchange([b'stream: OK\0'])

    def test_saturation_releases_slots(self):
        acquired = 0
        try:
            for _ in range(4):
                self.assertTrue(antivirus.SLOTS.acquire(blocking=False))
                acquired += 1
            with patch.dict(os.environ, {'DSIG_CLAMD_SOCKET': '/unused/clamd.sock'}):
                with self.assertRaises(antivirus.Unavailable):
                    antivirus.scan(b'fictional document')
        finally:
            for _ in range(acquired):
                antivirus.SLOTS.release()
        self.exchange([b'stream: OK\0'])

    @unittest.skipUnless(os.environ.get('DSIG_TEST_CLAMD_SOCKET'), 'real REC clamd not configured')
    def test_real_clamd_clean_document(self):
        with patch.dict(os.environ, {'DSIG_CLAMD_SOCKET': os.environ['DSIG_TEST_CLAMD_SOCKET']}):
            antivirus.scan(b'DSIG REC synthetic clean document')
