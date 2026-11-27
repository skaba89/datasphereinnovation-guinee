"""HTTP lifecycle primitive; caller owns admission and the volume lock.
Not a production entrypoint. No authorization is granted here.
"""
import signal
import threading
from contextlib import contextmanager
import server


class DrainingServer(server.BoundedHTTPServer):
    daemon_threads = False
    block_on_close = True

    def get_request(self):
        conn, address = super().get_request()
        conn.settimeout(10)
        return conn, address


@contextmanager
def listener(address, *, handler=server.Handler):
    """Close listening socket and join all handlers before returning."""
    with DrainingServer(address, handler) as http:
        http.timeout = 0.25
        yield http


def serve_until_stopped(http, stop):
    """Called on the serving thread; no shutdown() self-deadlock."""
    while not stop.is_set():
        http.handle_request()


@contextmanager
def termination_event():
    """Install and restore process signal handlers on the main thread."""
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError('main thread required')
    stop = threading.Event()
    previous = {}
    def request_stop(signum, frame):
        stop.set()
    try:
        for sig in (signal.SIGTERM, signal.SIGINT):
            previous[sig] = signal.signal(sig, request_stop)
        yield stop
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
