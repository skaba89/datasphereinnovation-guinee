#!/usr/bin/env python3
"""Export an encrypted REC archive to Backblaze B2 and publish its SHA256 proof (V179).

  export-rec-b2.py --scheduled              daily cycle (dsig-rec-b2.timer, 03:05 UTC): exactly the
                                            archive the daily audit expects (02:00-03:00 UTC)
  export-rec-b2.py --manual [--archive N]   most recent archive (or N), at most 24 h old; never
                                            refreshes an existing proof, never counts as a daily cycle

Order: lock -> select -> local checks -> remote state -> upload only if absent -> re-download and hash
-> proof published atomically ONLY after that remote verification. Idempotent: after an interruption
between upload and proof, the next run finds the identical remote object, skips the upload and writes
the proof. A remote object with a different SHA256 is never overwritten (FAIL, human investigation).
The b2 CLI uses its own authorised account; no secret is read, printed or passed on the command line.
"""
import argparse
import errno
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rec_b2  # noqa: E402
from rec_b2 import Failure  # noqa: E402

HOME = Path('/home/ubuntu')
BACKUPS = HOME / 'dsig-backups'
STATE = HOME / 'dsig-b2-automation'
B2 = HOME / '.local/bin/b2'
BUCKET = 'dsig-backup'
UPLOAD_TIMEOUT = 1800


def run_b2(args, timeout=600):
    """Run the b2 CLI; its output is captured but never logged (it may echo account details)."""
    try:
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise Failure('B2 injoignable ou délai dépassé')
    if result.returncode != 0:
        raise Failure(f'commande B2 en échec (code {result.returncode})')
    return result.stdout.decode('utf-8', errors='strict')


class Lock:
    """Non-blocking exclusive lock: a second export fails at once instead of waiting."""

    def __init__(self, path, busy):
        self.path, self.busy, self.fd = path, busy, None

    def __enter__(self):
        import fcntl
        flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0)
        try:
            self.fd = os.open(self.path, flags, 0o600)
        except OSError as error:
            raise Failure('verrou inutilisable' if error.errno != errno.ELOOP else 'verrou : lien symbolique interdit')
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(self.fd)
            raise Failure(self.busy)
        return self

    def __exit__(self, *exc):
        os.close(self.fd)


def backup_idle(backups):
    """Refuse to start while backup-rec.sh holds its lock; released at once (never delays a backup)."""
    lock = Path(backups) / '.backup.lock'
    if lock.is_symlink():
        raise Failure('verrou de sauvegarde : lien symbolique interdit')
    if lock.exists():
        with Lock(lock, 'sauvegarde locale en cours'):
            pass


def json_response(run, args):
    try:
        return json.loads(run(args))
    except (ValueError, TypeError):
        raise Failure('réponse B2 invalide')


def remote_present(run, b2, obj):
    prefix = obj.rsplit('/', 1)[0] + '/'
    rows = json_response(run, [str(b2), 'ls', '--recursive', '--json',
                               f'b2://{BUCKET}/{prefix}'])
    if not isinstance(rows, list) or any(
        not isinstance(row, dict) or not isinstance(row.get('fileName'), str)
        or row.get('action') not in ('upload', 'hide', 'folder') for row in rows
    ):
        raise Failure('inventaire B2 invalide')
    return any(row['fileName'] == obj and row['action'] == 'upload' for row in rows)


def remote_digest(run, b2, obj, directory, label):
    dest = Path(directory) / label
    run([str(b2), 'file', 'download', '--no-progress', f'b2://{BUCKET}/{obj}', str(dest)])
    if not dest.is_file():
        raise Failure('téléchargement B2 incomplet')
    return rec_b2.sha256(dest)


def export(mode, now, name=None, backups=None, state=None, b2=None, run=run_b2):
    if mode not in ('scheduled', 'manual'):
        raise Failure('mode export invalide')
    backups, state, b2 = Path(backups or BACKUPS), Path(state or STATE), Path(b2 or B2)
    rec_b2.private_dir(backups, 'répertoire de sauvegarde')
    rec_b2.private_dir(state, 'répertoire des preuves')
    if not b2.is_file():
        raise Failure('exécutable Backblaze absent')
    if mode == 'scheduled' and now.hour < rec_b2.PROOF_HOURS[0]:
        raise Failure('export planifié avant 03:00 UTC : la fenêtre des archives quotidiennes n\'est pas close')
    with Lock(state / '.export.lock', 'export B2 déjà en cours'):
        backup_idle(backups)
        if mode == 'scheduled':
            archive = rec_b2.select_daily(backups, now.strftime('%Y%m%d'))
        else:
            archive = rec_b2.select_manual(backups, now, name)
        rec_b2.check_archive(archive)
        digest = rec_b2.sha256(archive)
        marker = rec_b2.proof_path(state, archive.name, mode)
        recorded = rec_b2.read_proof(marker, archive.name)
        known = [rec_b2.read_proof(rec_b2.proof_path(state, archive.name, kind), archive.name)
                 for kind in ('scheduled', 'manual', 'legacy')]
        if any(value is not None and value != digest for value in known):
            raise Failure('preuve existante incohérente avec l\'archive : rien n\'est écrasé')
        obj = rec_b2.object_name(archive.name)
        bucket = json_response(run, [str(b2), 'bucket', 'get', BUCKET])
        if not isinstance(bucket, dict) or bucket.get('bucketName') != BUCKET or bucket.get('bucketType') != 'allPrivate':
            raise Failure('bucket non privé ou invalide')
        with tempfile.TemporaryDirectory(prefix='dsig-b2-export-') as tmp:
            present = remote_present(run, b2, obj)
            if not present and any(value is not None for value in known):
                raise Failure('objet distant absent malgré preuve existante')
            remote = remote_digest(run, b2, obj, tmp, 'before.dsigbak') if present else None
            if remote is not None and remote != digest:
                raise Failure('objet distant différent de l\'archive locale : rien n\'est écrasé')
            uploaded = remote is None
            if uploaded:
                run([str(b2), 'file', 'upload', '--no-progress', BUCKET, str(archive), obj], timeout=UPLOAD_TIMEOUT)
                if remote_digest(run, b2, obj, tmp, 'after.dsigbak') != digest:
                    raise Failure('vérification distante en échec après envoi : aucune preuve écrite')
        if rec_b2.sha256(archive) != digest:
            raise Failure('archive locale modifiée pendant export')
        # Proof only after effective remote verification, in the mode-specific namespace.
        # Manual exports cannot create or refresh a scheduled proof.
        proof = 'inchangée'
        if mode == 'scheduled' or recorded is None:
            rec_b2.write_proof(state, archive.name, digest, mode)
            proof = 'publiée'
    return {'archive': archive.name, 'object': obj, 'sha256': digest, 'uploaded': uploaded, 'proof': proof,
            'in_daily_window': mode == 'scheduled' and now.hour < rec_b2.PROOF_HOURS[1]}


def main(argv=None):
    parser = argparse.ArgumentParser(description='DSIG REC -> Backblaze B2 export')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--scheduled', action='store_true', help='daily cycle (timer only)')
    group.add_argument('--manual', action='store_true', help='recent archive outside the daily window')
    parser.add_argument('--archive', help='archive file name (with --manual only)')
    args = parser.parse_args(argv)
    if args.archive and not args.manual:
        parser.error('--archive requires --manual')
    mode = 'scheduled' if args.scheduled else 'manual'
    try:
        result = export(mode, datetime.now(timezone.utc), args.archive)
    except (Failure, OSError) as error:
        print('FAIL:', error if isinstance(error, Failure) else 'erreur système', flush=True)
        return 1
    print('Mode :', 'cycle quotidien' if mode == 'scheduled' else 'MANUEL (ne valide pas le cycle quotidien)')
    print('Archive :', result['archive'])
    print('Objet B2 :', result['object'], '(envoyé)' if result['uploaded'] else '(déjà présent, identique)')
    print('SHA256 :', result['sha256'])
    print('Preuve :', result['proof'])
    if mode == 'scheduled' and not result['in_daily_window']:
        print('ATTENTION : preuve créée après 04:00 UTC, l\'audit quotidien signalera ce cycle')
    print('PASS : archive externalisée et vérifiée sur B2')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
