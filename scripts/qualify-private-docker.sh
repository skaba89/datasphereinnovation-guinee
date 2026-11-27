#!/usr/bin/env bash
set -euo pipefail
# CI-only qualification: no published ports, host mounts or persistent volumes.
image="${1:-dsig-ci}"
[[ "$image" == dsig-ci ]] || { echo "Expected local CI image" >&2; exit 1; }
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true --user 10001:10001 \
  --memory 512m --cpus 2 --pids-limit 128 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777 \
  --tmpfs /app/data:rw,noexec,nosuid,nodev,size=64m,uid=10001,gid=10001,mode=0700 \
  --no-healthcheck -e DSIG_ENV=DEV "$image" \
  python -m unittest -v test_prod_private_qualification_entrypoint
