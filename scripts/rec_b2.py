"""Shared rules of the REC -> Backblaze B2 chain (V179): archive selection, local checks, SHA256 proofs.

Single source of truth for the export (export-rec-b2.py) and the audit (audit-rec-b2.py), so both
always designate the same archive:
  * daily cycle: the unique archive of the day created between 02:00 and 03:00 UTC (backup timer
    02:15), exported and proven between 03:00 and 04:00 UTC;
  * manual qualification: the most recent archive (or one named explicitly), at most 24 h old, at any
    time. It never counts as a daily cycle.
V185 separates manual and scheduled proofs. Legacy unqualified markers are read only as
integrity safeguards, never as evidence of a scheduled cycle. Never handles B2 secrets.
"""
import hashlib
import os
import re
import stat
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ARCHIVE = re.compile(r'dsig-rec-(\d{8})T(\d{6})Z\.dsigbak')
DAILY_WINDOW = ('020000', '030000')  # archive creation, UTC, [start, end)
PROOF_HOURS = (3, 4)                 # daily proof creation, UTC, [start, end)
MANUAL_MAX_AGE = timedelta(hours=24)
FUTURE_TOLERANCE = timedelta(minutes=5)
HEX64 = re.compile(r'[0-9a-f]{64}')


class Failure(Exception):
    """A check failed; the message is safe to print (no secret, no personal data)."""


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def archive_time(name):
    match = ARCHIVE.fullmatch(name)
    if not match:
        raise Failure('nom d\'archive invalide')
    try:
        return datetime.strptime(match.group(1) + match.group(2), '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
    except ValueError:
        raise Failure('date archive invalide') from None


def object_name(name):
    """B2 object of an archive, dated by the archive itself (rec/YYYY/MM/<name>)."""
    day = ARCHIVE.fullmatch(name).group(1)
    return f'rec/{day[:4]}/{day[4:6]}/{name}'


def private_dir(path, label):
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise Failure(label + ' absent ou lien symbolique')
    if path.stat().st_mode & 0o077:
        raise Failure('permissions ' + label + ' trop ouvertes')


def _regular_archives(backups):
    for path in Path(backups).iterdir():
        if ARCHIVE.fullmatch(path.name) and stat.S_ISREG(path.lstat().st_mode):
            yield path


def select_daily(backups, day):
    """The unique archive of `day` (YYYYMMDD) created in the daily window, else Failure."""
    start, end = DAILY_WINDOW
    found = [p for p in _regular_archives(backups)
             if ARCHIVE.fullmatch(p.name).group(1) == day and start <= ARCHIVE.fullmatch(p.name).group(2) < end]
    if len(found) != 1:
        raise Failure('une archive unique attendue entre 02:00 et 03:00 UTC')
    archive_time(found[0].name)
    return found[0]


def select_manual(backups, now, name=None):
    """The named archive, or the most recent one; refused if older than 24 h or in the future."""
    if name is not None:
        if not ARCHIVE.fullmatch(name):
            raise Failure('nom d\'archive invalide (nom seul, sans chemin)')
        path = Path(backups) / name
        if path.is_symlink():
            raise Failure('lien symbolique interdit')
        if not path.is_file():
            raise Failure('archive demandée absente')
    else:
        found = sorted(_regular_archives(backups), key=lambda p: p.name)
        if not found:
            raise Failure('aucune archive locale')
        path = found[-1]
    created = archive_time(path.name)
    if created > now + FUTURE_TOLERANCE:
        raise Failure('archive datée dans le futur')
    if now - created > MANUAL_MAX_AGE:
        raise Failure('archive trop ancienne (plus de 24 h)')
    return path


def check_archive(path):
    info = Path(path).lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise Failure('lien symbolique interdit')
    if info.st_size == 0:
        raise Failure('archive vide')
    if info.st_mode & 0o077:
        raise Failure('permissions archive trop ouvertes')


def proof_path(state, name, mode='scheduled'):
    if mode not in ('scheduled', 'manual', 'legacy'):
        raise Failure('mode de preuve invalide')
    suffix = '.sha256' if mode == 'legacy' else '.' + mode + '.sha256'
    return Path(state) / (name + suffix)


def read_proof(marker, name):
    """The digest recorded in a proof; None if there is no proof; Failure if it is unusable."""
    marker = Path(marker)
    if not marker.is_symlink() and not marker.exists():
        return None
    info = marker.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise Failure('preuve B2 : lien symbolique interdit')
    if info.st_mode & 0o077:
        raise Failure('permissions preuve trop ouvertes')
    fields = marker.read_text(encoding='ascii', errors='replace').split()
    if len(fields) == 2 and fields[1].lstrip('*') == name:
        fields = fields[:1]  # sha256sum format of the same archive
    if len(fields) != 1 or not HEX64.fullmatch(fields[0]):
        raise Failure('preuve B2 illisible')
    return fields[0]


def write_proof(state, name, digest, mode='scheduled'):
    """Atomically publish <state>/<name>.sha256 (0600). Call only after remote verification."""
    if mode not in ('scheduled', 'manual'):
        raise Failure('écriture de preuve historique interdite')
    if not HEX64.fullmatch(digest):
        raise Failure('empreinte invalide')
    fd, tmp = tempfile.mkstemp(prefix='.proof-', dir=state)
    try:
        with os.fdopen(fd, 'w', encoding='ascii') as out:
            out.write(digest + '\n')
            out.flush()
            os.fsync(out.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, proof_path(state, name, mode))
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    if hasattr(os, 'O_DIRECTORY'):
        dfd = os.open(state, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)


def proof_time(marker):
    return datetime.fromtimestamp(Path(marker).stat().st_mtime, timezone.utc)
