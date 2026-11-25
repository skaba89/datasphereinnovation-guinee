# PRA V181 — isolated Docker and SQLite rehearsal

Only run on a disposable dedicated Linux recovery host with a local Docker daemon, no existing containers, volumes or custom networks, and sufficient memory and disk. Do not run on the shared OVH VPS. An operator must verify the host is dedicated; the automated empty-host checks are not a proof of exclusivity.

First qualify the encrypted V1 kit using V180 with the independently retained SHA256. Extract the trusted image archive on that host in a private directory, identify the exact saved image tar (gzip supported by docker load), and obtain its internal SHA256 from the verified kit. Obtain the encrypted SQLite backup and its trusted SHA256 separately. Do not use untrusted Docker save archives. Keep input files private (0600), with exclusive access to the directory during the exercise.

    python3 scripts/pra_restore.py --dedicated-recovery-host --image-tar /private/image.tar.gz --image-sha256 <trusted-hash> --image-id sha256:<trusted-image-id> --backup /private/backup.dsigbak --backup-sha256 <trusted-hash>

The backup key is prompted interactively, not supplied in arguments. The restored database exists only in container tmpfs. No host mounts, published ports, external network or mail jobs. The exact image ID is checked after load. The worker uses the existing restore logic, verifies foreign keys and invalidated sessions, and probes health and readiness on loopback. The report is JSON; elapsed time is not full RTO. The loaded image remains on the recovery host; destroy the disposable host according to the approved retention policy. Do not prune shared resources.

Synthetic tests: python3 -m unittest -v test_pra_restore. Existing CI discovery runs them. These tests do not execute Docker restore end-to-end. Real exercise is required. No document/MFA key recovery, Caddy, ClamAV, systemd, public HTTPS or business acceptance in this phase. No PROD authorization. The daily B2 schedule is untouched.
