import signal
import threading
import unittest
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler
import prod_private_http_lifecycle as lifecycle


class LifecycleTests(unittest.TestCase):
    def test_drains_active_request_before_context_exit(self):
        entered, release, closed, stop = (threading.Event() for _ in range(4))
        ready = threading.Event()
        addresses, errors, responses = [], [], []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                entered.set()
                if not release.wait(5):
                    return
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'ok')
        def serve():
            try:
                with lifecycle.listener(('127.0.0.1', 0), handler=Handler) as http:
                    addresses.append(http.server_port)
                    ready.set()
                    lifecycle.serve_until_stopped(http, stop)
            except Exception as exc:
                errors.append(exc)
            finally:
                closed.set()
        def request():
            try:
                conn = HTTPConnection('127.0.0.1', addresses[0], timeout=5)
                try:
                    conn.request('GET', '/')
                    response = conn.getresponse()
                    responses.append((response.status, response.read()))
                finally:
                    conn.close()
            except Exception as exc:
                errors.append(exc)
        worker = threading.Thread(target=serve)
        worker.start()
        client = None
        try:
            self.assertTrue(ready.wait(3))
            client = threading.Thread(target=request)
            client.start()
            self.assertTrue(entered.wait(3))
            stop.set()
            self.assertFalse(closed.wait(0.5))
        finally:
            stop.set()
            release.set()
            if client is not None:
                client.join(6)
            worker.join(6)
        self.assertTrue(closed.is_set())
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(responses, [(200, b'ok')])

    def test_signals_restored(self):
        previous = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
        with lifecycle.termination_event() as stop:
            self.assertFalse(stop.is_set())
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
            self.assertTrue(stop.is_set())
        for sig, handler in previous.items():
            self.assertEqual(signal.getsignal(sig), handler)

    def test_preexisting_stop(self):
        stop = threading.Event()
        stop.set()
        with lifecycle.listener(('127.0.0.1', 0)) as http:
            lifecycle.serve_until_stopped(http, stop)


if __name__ == '__main__':
    unittest.main()
