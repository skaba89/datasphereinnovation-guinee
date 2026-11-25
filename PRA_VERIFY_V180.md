# PRA REC — V180

Read-only verification phase. No production authorization, no installation, no Docker or systemd changes.

On a trusted Linux recovery host with Python 3.10+ and GPG, download each encrypted kit and obtain its SHA256 from an independently retained trusted record. Set the archive mode to 0600 and run:

    export GPG_TTY=$(tty)
    python3 scripts/pra_verify.py /private/kit.tar.gz.gpg --sha256 <trusted-lowercase-sha256>

Enter the GPG passphrase interactively. Never put it in shell arguments, logs or Git. The verifier streams the archive without extracting it, rejects unsafe paths, links, duplicate entries, missing checksums and unchecked files, and requires GPG success. Limits: 2 GiB of member payloads, 4096 entries, 1 MiB checksum manifest. Review the limits before larger kits are issued.

Run synthetic tests: python3 -m unittest -v test_pra_verify. The existing CI unittest discovery runs them. Real encrypted kit validation is still required; these tests do not establish GPG integration, semantic manifest validity, secret absence, image identity, SQLite restore, Object Lock or RPO/RTO. A checksum from the same compromised source is not independent evidence. Retain trusted hashes and GPG keys separately. Do not use this command to authorize production.

Next phase: isolated restoration on a dedicated recovery host, using the exact image and data archive, no published ports or external notifications. Do not change the current daily B2 schedule.
