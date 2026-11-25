#!/usr/bin/env bash
set -euo pipefail
umask 077
BUCKET=dsig-backup
SOURCE="$HOME/dsig-backups"
STATE="$HOME/dsig-b2-automation"
B2="$HOME/.local/bin/b2"
fail() { echo "FAIL : $*" >&2; exit 1; }
for dir in "$SOURCE" "$STATE"; do
  [[ -d "$dir" && ! -L "$dir" && -O "$dir" && "$(stat -c %a "$dir")" == 700 ]] || fail "répertoire non sécurisé"
done
[[ ! -L "$STATE/.export.lock" ]] || fail "verrou symbolique"
exec 9>"$STATE/.export.lock"
flock -n 9 || fail "export concurrent"
DAY=$(date -u +%Y%m%d)
MODE=daily
NAME=""
case $# in
  0) ;;
  1) [[ "$1" == --manual ]] || fail "argument invalide"; MODE=manual ;;
  3) [[ "$1" == --manual && "$2" == --archive ]] || fail "argument invalide"; MODE=manual; NAME="$3" ;;
  *) fail "argument invalide" ;;
esac
if [[ "$MODE" == daily ]]; then
  HOUR=$(date -u +%H)
  [[ "$HOUR" == 03 ]] || fail "export quotidien hors fenêtre 03:00-04:00 UTC"
  mapfile -t NAMES < <(find "$SOURCE" -maxdepth 1 -type f -name "dsig-rec-${DAY}T02????Z.dsigbak" -printf '%f\n' | sort)
  [[ ${#NAMES[@]} == 1 ]] || fail "archive quotidienne unique attendue"
  NAME="${NAMES[0]}"
elif [[ -z "$NAME" ]]; then
  mapfile -t NAMES < <(find "$SOURCE" -maxdepth 1 -type f -name 'dsig-rec-*.dsigbak' -printf '%f\n' | sort -r)
  [[ ${#NAMES[@]} -gt 0 ]] || fail "aucune archive"
  NAME="${NAMES[0]}"
fi
[[ "$NAME" =~ ^dsig-rec-([0-9]{8})T([0-9]{6})Z\.dsigbak$ ]] || fail "nom archive invalide"
FILE="$SOURCE/$NAME"
[[ -f "$FILE" && ! -L "$FILE" && -s "$FILE" && -O "$FILE" && "$(stat -c %a "$FILE")" == 600 ]] || fail "archive non sécurisée"
NOW=$(date -u +%s)
MODIFIED=$(stat -c %Y "$FILE")
AGE=$((NOW - MODIFIED))
(( AGE >= 0 && AGE <= 10800 )) || fail "sauvegarde trop ancienne ou horloge incohérente"
OBJECT="rec/${NAME:9:4}/${NAME:13:2}/$NAME"
SHA=$(sha256sum "$FILE" | cut -d' ' -f1)
MARKER="$STATE/$NAME.sha256"
TMP=$(mktemp -d "$STATE/check.XXXXXXXX")
trap 'rm -rf -- "$TMP"' EXIT
"$B2" bucket get "$BUCKET" > "$TMP/bucket.json"
python3 - "$TMP/bucket.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    b = json.load(f)
if b.get("bucketName") != "dsig-backup" or b.get("bucketType") != "allPrivate":
    raise SystemExit("FAIL : bucket non privé")
PY
if [[ -e "$MARKER" || -L "$MARKER" ]]; then
  [[ -f "$MARKER" && ! -L "$MARKER" && "$(stat -c %a "$MARKER")" == 600 && "$(cat "$MARKER")" == "$SHA" ]] || fail "marqueur incohérent"
fi
# List first: absence is distinct from network/authorization failure.
"$B2" ls --recursive --json "b2://$BUCKET/rec/${NAME:9:4}/${NAME:13:2}/" > "$TMP/list.json"
PRESENT=$(python3 - "$TMP/list.json" "$OBJECT" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    rows = json.load(f)
if not isinstance(rows, list):
    raise SystemExit("FAIL : inventaire B2 invalide")
print("yes" if any(r.get("fileName") == sys.argv[2] and r.get("action") == "upload" for r in rows) else "no")
PY
)
if [[ "$PRESENT" == no ]]; then
  [[ ! -e "$MARKER" ]] || fail "objet distant absent malgré preuve"
  "$B2" file upload --no-progress "$BUCKET" "$FILE" "$OBJECT" > "$TMP/upload.json"
fi
"$B2" file download --no-progress "b2://$BUCKET/$OBJECT" "$TMP/downloaded.dsigbak" > "$TMP/download.json"
[[ "$(sha256sum "$TMP/downloaded.dsigbak" | cut -d' ' -f1)" == "$SHA" ]] || fail "SHA256 distant incorrect"
[[ "$(sha256sum "$FILE" | cut -d' ' -f1)" == "$SHA" ]] || fail "archive locale modifiée"
if [[ ! -e "$MARKER" ]]; then
  printf '%s\n' "$SHA" > "$TMP/marker"
  chmod 600 "$TMP/marker"
  ln -T -- "$TMP/marker" "$MARKER"
fi
echo "PASS : sauvegarde B2 vérifiée ($MODE)"
echo "Objet : $OBJECT"
echo "SHA256 : $SHA"
