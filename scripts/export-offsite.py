"""Export encrypted REC archives to an explicitly mounted private destination."""
import hashlib
import os
import re
import shutil
import stat
import sys
import tempfile
from pathlib import Path

NAME = re.compile(r'dsig-rec-\d{8}T\d{6}Z\.dsigbak')


def digest(path):
    with path.open('rb') as stream:
        sha = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(chunk)
        return sha.hexdigest()


def private_dir(path):
    return not path.is_symlink() and path.is_dir() and stat.S_IMODE(path.stat().st_mode) == 0o700


def export(source, mount, target):
    if not private_dir(source) or not os.path.ismount(mount) or mount.is_symlink():
        raise ValueError('Source private and mounted destination required')
    if not private_dir(target) or target.resolve().parent != mount.resolve():
        raise ValueError('Destination must be a private direct child of mount')
    if source.stat().st_dev == target.stat().st_dev:
        raise ValueError('Destination must be on another filesystem')
    archives = []
    for path in source.iterdir():
        if NAME.fullmatch(path.name):
            info = path.lstat()
            if stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600 and info.st_size:
                archives.append(path)
    if not archives:
        raise ValueError('No private archives found')
    for archive in sorted(archives):
        expected = digest(archive)
        final = target / archive.name
        if final.exists() or final.is_symlink():
            if final.is_symlink() or not final.is_file() or stat.S_IMODE(final.stat().st_mode) != 0o600 or digest(final) != expected:
                raise ValueError('Existing destination differs')
            continue
        fd, name = tempfile.mkstemp(prefix='.partial-', dir=target)
        stage = Path(name)
        try:
            with os.fdopen(fd, 'wb') as out, archive.open('rb') as inp:
                shutil.copyfileobj(inp, out)
                out.flush()
                os.fsync(out.fileno())
            if digest(stage) != expected:
                raise ValueError('Checksum mismatch')
            os.link(stage, final)
        finally:
            stage.unlink(missing_ok=True)
    return len(archives)


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            raise ValueError('Provide mountpoint')
        mount = Path(sys.argv[1])
        if not mount.is_absolute():
            raise ValueError('Absolute mountpoint required')
        source = Path(os.environ.get('DSIG_BACKUP_DIR', str(Path.home() / 'dsig-backups')))
        count = export(source, mount, mount / 'dsig-rec')
        print(f'PASS: {count} encrypted archive(s) verified')
    except (OSError, ValueError):
        print('FAIL: offsite export not completed', file=sys.stderr)
        raise SystemExit(1)
