#!/usr/bin/env bash
set -euo pipefail
umask 077
container=dsig-rec-dsig-1
directory="${DSIG_BACKUP_DIR:-$HOME/dsig-backups}"
mkdir -p -m 700 -- "$directory"
[[ -d "$directory" && ! -L "$directory" && -O "$directory" ]]
[[ "$(stat -c %a "$directory")" == 700 ]]
exec 9>"$directory/.backup.lock"
flock -n 9 || { echo 'Backup already running' >&2; exit 1; }
stamp=$(date -u +%Y%m%dT%H%M%SZ)
destination="$directory/dsig-rec-$stamp.dsigbak"
stage=''
remote=''
cleanup() {
  if [[ "$remote" =~ ^/tmp/dsig-backup\.[a-zA-Z0-9]+$ ]]; then
    docker exec "$container" rm -f -- "$remote/archive.dsigbak" "$remote/restored.sqlite3" || true
    docker exec "$container" rmdir -- "$remote" || true
  fi
  if [[ -n "$stage" ]]; then rm -f -- "$stage"; fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
[[ ! -e "$destination" && ! -L "$destination" ]]
docker exec "$container" python preflight.py
remote=$(docker exec "$container" mktemp -d /tmp/dsig-backup.XXXXXXXX)
[[ "$remote" =~ ^/tmp/dsig-backup\.[a-zA-Z0-9]+$ ]]
stage=$(mktemp "$directory/.partial.XXXXXXXX")
docker exec "$container" python server.py --backup-encrypted "$remote/archive.dsigbak"
docker exec "$container" python server.py --restore-isolated "$remote/archive.dsigbak" "$remote/restored.sqlite3"
docker exec "$container" cat "$remote/archive.dsigbak" > "$stage"
[[ -s "$stage" ]]
expected=$(docker exec "$container" sha256sum "$remote/archive.dsigbak")
actual=$(sha256sum "$stage")
[[ "${expected%% *}" =~ ^[0-9a-f]{64}$ && "${expected%% *}" == "${actual%% *}" ]]
ln -T -- "$stage" "$destination"
echo "Verified backup: $destination"
sha256sum "$destination"
