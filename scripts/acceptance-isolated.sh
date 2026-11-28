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
if docker image inspect "$image" >/dev/null 2>&1; then
  echo 'Existing suite image: use a fresh commit or review the existing qualification' >&2
  exit 1
fi
docker build --label "org.opencontainers.image.revision=$commit" -t "$image" "$stage"
image_id=$(docker image inspect --format '{{.Id}}' "$image")
[[ "$image_id" =~ ^sha256:[0-9a-f]{64}$ ]]
python3 scripts/verify-prod-image.py "$commit" "$image_id" --qualification-local --require-revision
# Test-only derivative: host-side release tooling needs Git in the isolated suite.
# Keep the deployable application image unchanged; install dependencies at build time only.
test_image="dsig-rec-suite-git:$commit"
docker build --build-arg BASE_IMAGE="$image_id" --label "com.dsig.image.role=test-only" -t "$test_image" -f - "$stage" <<'DOCKERFILE'
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
USER root
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
USER 10001:10001
DOCKERFILE
echo "Candidate commit: $commit"
docker run --rm --network none --read-only --tmpfs /tmp:rw,nosuid,nodev,size=512m \
  --cap-drop ALL --security-opt no-new-privileges \
  --mount "type=bind,src=$stage,dst=/suite,readonly" \
  -e DSIG_ENV=REC -e PYTHONDONTWRITEBYTECODE=1 \
  -w /tmp "$test_image" sh -ec 'cp -R /suite /tmp/suite; cd /tmp/suite; python -m unittest -v'
[[ "$(docker image inspect --format '{{.Id}}' "$image")" == "$image_id" ]]
echo "Qualified application image: $image_id"
echo 'PASS: isolated Python regression suite. Manual REC acceptance still required.'
