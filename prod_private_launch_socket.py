"""One-shot host launch socket. No Docker mutation or startup authorization."""
import os
import socket
import stat
from contextlib import contextmanager
from pathlib import Path
import prod_private_launch_topology as topology
import prod_private_handoff_transport as transport

NAME = 'launch.sock'


def _directory(path, *, host):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError('unsafe channel directory')
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0
            or info.st_gid != 10001 or stat.S_IMODE(info.st_mode) != 0o750):
        raise ValueError('unsafe channel permissions')
    if host and os.geteuid() != 0:
        raise PermissionError('root required')
    return path


@contextmanager
def host_listener():
    path = _directory(topology.HOST_CHANNEL, host=True) / NAME
    if os.path.lexists(path):
        raise FileExistsError('launch socket already exists')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(path))
        identity = path.lstat()
        try:
            os.chown(path, 0, 10001)
            os.chmod(path, 0o660)
            listener.listen(1)
            listener.settimeout(30)
            yield listener
        finally:
            try:
                current = path.lstat()
                if (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino):
                    path.unlink()
            except FileNotFoundError:
                pass


@contextmanager
def runtime_connection():
    path = _directory(topology.CHANNEL, host=False) / NAME
    info = path.lstat()
    if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != 0
            or info.st_gid != 10001 or stat.S_IMODE(info.st_mode) != 0o660):
        raise ValueError('unsafe launch socket')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(transport.TIMEOUT)
        conn.connect(str(path))
        transport.peer(conn, 0)
        current = path.lstat()
        if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
            raise ValueError('launch socket changed')
        yield conn
