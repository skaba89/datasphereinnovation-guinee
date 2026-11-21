#!/usr/bin/env bash
# Prepare an upgrade only. Never recreate, stop or replace the active container.
set -euo pipefail
umask 077
cd "$(git rev-parse --show-toplevel)"
commit="${1:-}"
[[ $# == 1 && "$commit" =~ ^[0-9a-f]{40}$ ]] || { echo 'Exact approved Git SHA required' >&2; exit 1; }
[[ "$(git rev-parse HEAD)" == "$commit" && -z "$(git status --porcelain --untracked-files=no)" ]] || { echo 'Clean checkout of approved SHA required' >&2; exit 1; }
container=dsig-rec-dsig-1
[[ "$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' "$container")" == dsig-rec ]]
[[ "$(docker inspect --format '{{index .Config.Labels "com.docker.compose.service"}}' "$container")" == dsig ]]
docker exec "$container" python -c 'import os; assert os.environ.get("DSIG_ENV") == "REC"'
[[ "$(docker inspect --format '{{.State.Health.Status}}' "$container")" == healthy ]]
old_id=$(docker inspect --format '{{.Image}}' "$container")
[[ "$old_id" =~ ^sha256:[0-9a-f]{64}$ ]]
stamp=$(date -u +%Y%m%dT%H%M%SZ)
candidate="dsig-rec-candidate:$commit"
rollback="dsig-rec-rollback:$stamp"
if docker image inspect "$candidate" >/dev/null 2>&1 || docker image inspect "$rollback" >/dev/null 2>&1; then
  echo 'Image tag already exists; review existing preparation first' >&2
  exit 1
fi
# The existing isolated suite builds only tracked files and runs tests without networking.
bash scripts/acceptance-isolated.sh
suite="dsig-rec-suite:$commit"
candidate_id=$(docker image inspect --format '{{.Id}}' "$suite")
[[ "$candidate_id" =~ ^sha256:[0-9a-f]{64}$ ]]
docker tag "$candidate_id" "$candidate"
docker tag "$old_id" "$rollback"
# Verify backup and restore without replacing the active database.
[[ "$(docker inspect --format '{{.Image}}' "$container")" == "$old_id" ]]
bash scripts/backup-rec.sh
[[ "$(docker inspect --format '{{.Image}}' "$container")" == "$old_id" ]]
printf 'PREPARED ONLY\nCommit: %s\nCandidate: %s (%s)\nRollback: %s (%s)\n' "$commit" "$candidate" "$candidate_id" "$rollback" "$old_id"
echo 'Manual REC activation and post-deployment checks required. No production authorization.'
