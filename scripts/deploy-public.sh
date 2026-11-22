#!/usr/bin/env bash
# Explicit activation only; never edits edge proxy or REC.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
[[ $# == 2 && "$1" =~ ^[a-f0-9]{40}$ && "$2" == --activate-public ]] || { echo 'Usage: deploy-public.sh SHA --activate-public' >&2; exit 1; }
sha=$1
export DSIG_PUBLIC_IMAGE="dsig-public:$sha"
docker image inspect "$DSIG_PUBLIC_IMAGE" >/dev/null
docker network inspect edge >/dev/null
[[ "$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$DSIG_PUBLIC_IMAGE")" == "$sha" ]] || { echo 'Image revision mismatch' >&2; exit 1; }
dc() { docker compose -p dsig-public -f compose.public.yaml "$@"; }
dc config --quiet
previous=$(dc ps -q vitrine)
if [[ -n "$previous" ]]; then
  previous=$(docker inspect --format '{{.Image}}' "$previous")
  [[ "$previous" =~ ^sha256:[a-f0-9]{64}$ ]]
  echo "Previous image ID: $previous"
fi
if ! dc up -d --no-deps --no-build --pull never --wait vitrine; then
  echo 'Activation failed; attempting previous image rollback' >&2
  if [[ -n "$previous" ]]; then
    rollback="dsig-public:rollback-${previous#sha256:}"
    docker image tag "$previous" "$rollback"
    export DSIG_PUBLIC_IMAGE="$rollback"
    dc up -d --no-deps --no-build --pull never --wait vitrine
  else
    dc stop vitrine
  fi
  exit 1
fi
echo 'PASS: public container healthy; edge proxy unchanged'
