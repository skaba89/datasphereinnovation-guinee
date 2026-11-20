#!/usr/bin/env bash
# Isolated candidate suite: no production containers, no real database, no published ports.
set -euo pipefail
umask 077
cd "$(git rev-parse --show-toplevel)"
commit=$(git rev-parse HEAD)
[[ "$commit" =~ ^[0-9a-f]{40}$ ]]
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo 'Tracked worktree changes: abort' >&2
  exit 1
fi
stage=$(mktemp -d /tmp/dsig-rec-suite.XXXXXXXX)
cleanup() {
  if [[ "$stage" =~ ^/tmp/dsig-rec-suite\.[a-zA-Z0-9]+$ ]]; then
    rm -rf -- "$stage"
  fi
}
trap cleanup EXIT
git archive "$commit" | tar -xf - -C "$stage"
# Git-tracked source only. No .env or active database.
test ! -e "$stage/.env"
test ! -e "$stage/data"
# Archive is tracked source only; allow the unprivileged container to read it.
chmod -R a+rX "$stage"
image="dsig-rec-suite:$commit"
docker build -t "$image" "$stage"
echo "Candidate commit: $commit"
docker run --rm --network none --read-only --tmpfs /tmp:rw,nosuid,nodev,size=512m \
  --cap-drop ALL --security-opt no-new-privileges \
  --mount "type=bind,src=$stage,dst=/suite,readonly" \
  -e DSIG_ENV=REC -e PYTHONDONTWRITEBYTECODE=1 \
  -w /suite "$image" python -m unittest -v
echo 'PASS: isolated Python regression suite. Manual REC acceptance still required.'
