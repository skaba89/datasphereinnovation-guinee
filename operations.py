"""Local operational controls: encrypted SQLite snapshots and isolated restores."""
import os
import sqlite3
import tempfile
from pathlib import Path
from contextlib import closing
from cryptography.fernet import Fernet, InvalidToken

MAX_DB_BYTES = 64 * 1024 * 1024
MAX_ENCRYPTED_BYTES = 2 * MAX_DB_BYTES
REQUIRED_TABLES = {'requests', 'request_events', 'accounts', 'credentials', 'sessions', 'mfa', 'recovery_codes', 'access_events', 'opportunities', 'opportunity_events', 'consultants', 'consultant_events', 'quotes', 'quote_events', 'missions', 'activity', 'mission_events', 'tenders', 'tender_events', 'milestones', 'invoices', 'payments', 'billing_events', 'organizations', 'organization_links', 'mission_members', 'contract_renewals', 'expenses', 'documents'}


def readonly(path):
    return sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True, timeout=3)


def ready(path):
    try:
        with closing(readonly(path)) as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            return REQUIRED_TABLES <= tables and db.execute('SELECT 1').fetchone() == (1,)
    except (sqlite3.Error, OSError, ValueError):
        return False


def verify(path):
    if not ready(path):
        raise ValueError('Schéma de sauvegarde invalide.')
    with closing(readonly(path)) as db:
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('Intégrité de la sauvegarde invalide.')


def cipher():
    try:
        return Fernet(os.environ.get('DSIG_BACKUP_KEY', '').encode())
    except (ValueError, TypeError) as exc:
        raise ValueError('DSIG_BACKUP_KEY absente ou invalide.') from exc


def safe_target(destination, active, served):
    path = Path(destination).resolve()
    if path == Path(active).resolve() or path.is_relative_to(Path(served).resolve()):
        raise ValueError('Destination interdite : base active ou répertoire public.')
    return path


def write_new(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data); handle.flush(); os.fsync(handle.fileno())
    except Exception:
        path.unlink()
        raise


def encrypted_backup(active, destination, served):
    path = safe_target(destination, active, served)
    key = cipher()
    if path.exists(): raise FileExistsError(path)
    with tempfile.TemporaryDirectory(prefix='dsig-backup-') as temp:
        snapshot = Path(temp) / 'snapshot.sqlite3'
        with closing(readonly(active)) as source, closing(sqlite3.connect(snapshot)) as target:
            if source.execute('PRAGMA page_count').fetchone()[0] * source.execute('PRAGMA page_size').fetchone()[0] > MAX_DB_BYTES:
                raise ValueError('Base trop volumineuse pour ce mode de sauvegarde.')
            source.backup(target)
        verify(snapshot)
        if snapshot.stat().st_size > MAX_DB_BYTES: raise ValueError('Sauvegarde trop volumineuse.')
        write_new(path, key.encrypt(snapshot.read_bytes()))


def restore_isolated(source, destination, active, served):
    path = safe_target(destination, active, served)
    if path.exists(): raise FileExistsError(path)
    key = cipher()
    with Path(source).open('rb') as handle:
        encrypted = handle.read(MAX_ENCRYPTED_BYTES+1)
    if len(encrypted)>MAX_ENCRYPTED_BYTES: raise ValueError('Sauvegarde trop volumineuse.')
    try: data = key.decrypt(encrypted)
    except InvalidToken as exc: raise ValueError('Sauvegarde altérée ou clé incorrecte.') from exc
    if len(data)>MAX_DB_BYTES: raise ValueError('Base trop volumineuse.')
    with tempfile.TemporaryDirectory(prefix='dsig-restore-') as temp:
        candidate = Path(temp) / 'restore.sqlite3'
        write_new(candidate, data)
        verify(candidate)
        with closing(sqlite3.connect(candidate)) as db:
            # Sessions exported in the backup must not become valid again.
            db.execute('DELETE FROM sessions'); db.commit()
        verify(candidate)
        write_new(path, candidate.read_bytes())
