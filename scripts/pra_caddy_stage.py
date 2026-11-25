"""Stage the authenticated REC Caddy fragment; adapt offline, never start Caddy."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile

from pra_system_stage import private_dir, read_private
from pra_verify import safe_name


def verified_fragment(source):
    private_dir(source)
    expected = {}
    for line in read_private(source, "SHA256SUMS").decode("ascii").splitlines():
        match = re.fullmatch(r"([a-f0-9]{64}) [ *](.+)", line)
        if not match:
            raise ValueError("invalid checksum")
        name = safe_name(match[2])
        if name in expected:
            raise ValueError("duplicate checksum")
        expected[name] = match[1]
    if set(expected) != {"MANIFEST.txt", "dsig-rec.caddy"}:
        raise ValueError("unexpected V3 contents")
    for name, checksum in expected.items():
        data = read_private(source, name)
        if hashlib.sha256(data).hexdigest() != checksum:
            raise ValueError("checksum mismatch")
        if name == "dsig-rec.caddy":
            fragment = data
    return fragment


def check_fragment(fragment, hostname):
    # Deliberately restricted subset. Reject unknown or ambiguous constructs;
    # this is a staging gate, not a general-purpose Caddyfile parser.
    if not re.fullmatch(r"rec-[a-z0-9-]+(?:\.[a-z0-9-]+)+", hostname):
        raise ValueError("explicit REC hostname required")
    text = fragment.decode("utf-8")
    if any(c in text for c in ("\x00", "\r", "\x60")):
        raise ValueError("unsupported characters")
    if re.search(r"\{\$|\{env\.|(?m:^\s*import\b)", text):
        raise ValueError("external dependency or substitution")
    # No snippet declarations, global options or second site at top level.
    # Count braces outside quoted strings and inline placeholders; multiline
    # quoted values and heredocs are not supported by this gate.
    depth = 0
    sites = 0
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if depth == 0:
            if line != hostname + " {":
                raise ValueError("unexpected site or global configuration")
            sites += 1
        if re.search(r"(?i)(?:^|\s)(?:tls|import|basic_auth|basicauth|forward_auth|file_server|root|php_fastcgi|log|acme_server|storage|on_demand_tls|templates|exec)\b", line):
            raise ValueError("directive requires separate review")
        if "<<" in line or "\\" in line:
            raise ValueError("unsupported syntax")
        clean = re.sub(r'"[^"]*"', "", line)
        clean = re.sub(r"\{[a-zA-Z0-9_.-]+\}", "", clean)
        depth += clean.count("{") - clean.count("}")
        if depth < 0:
            raise ValueError("unbalanced configuration")
    if depth != 0 or sites != 1:
        raise ValueError("expected one complete REC site")


def adapt(fragment, caddy_image):
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", caddy_image):
        raise ValueError("locally trusted immutable Caddy image required")
    # Only adaptation, not validate/provision/run; no host mounts or network.
    result = subprocess.run(
        ["docker", "--host", "unix:///var/run/docker.sock", "run", "--rm", "-i",
         "--pull", "never", "--network", "none", "--read-only", "--cap-drop", "ALL",
         "--security-opt", "no-new-privileges", "--user", "10001:10001",
         "--memory", "128m", "--pids-limit", "64", "--log-driver", "none",
         "--entrypoint", "caddy", caddy_image, "adapt", "--adapter", "caddyfile",
         "--config", "/dev/stdin"],
        input=fragment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=60, check=True,
    )
    return json.loads(result.stdout)


def check_adapted(config, hostname):
    # Refuse unexpected handlers and upstreams in the adapted structure.
    # Inspect all nested dictionaries, including subroutes.
    hosts = set()
    proxies = []
    allowed = {"subroute", "headers", "encode", "reverse_proxy", "static_response",
               "vars", "rewrite"}
    def walk(node):
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            if "host" in node:
                values = node["host"]
                if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
                    raise ValueError("unexpected host matcher")
                hosts.update(values)
            if "handler" in node:
                if node["handler"] not in allowed:
                    raise ValueError("unexpected handler")
                if node["handler"] == "reverse_proxy":
                    upstreams = node.get("upstreams", [])
                    if not upstreams or node.get("dynamic_upstreams") or node.get("transport"):
                        raise ValueError("unexpected proxy dependency")
                    for upstream in upstreams:
                        proxies.append(upstream.get("dial"))
            for value in node.values():
                walk(value)
    if set(config) - {"apps"} or set(config.get("apps", {})) != {"http"}:
        raise ValueError("unexpected Caddy application")
    walk(config)
    if hosts != {hostname} or not proxies or set(proxies) != {"dsig-rec-dsig-1:8080"}:
        raise ValueError("unexpected REC host or upstream")


def stage(source, parent, hostname, caddy_image):
    private_dir(parent)
    fragment = verified_fragment(source)
    check_fragment(fragment, hostname)
    config = adapt(fragment, caddy_image)
    check_adapted(config, hostname)
    destination = Path(tempfile.mkdtemp(prefix="dsig-pra-caddy-", dir=parent))
    report = {"hostname": hostname, "sha256": hashlib.sha256(fragment).hexdigest(),
              "caddy_image": caddy_image, "adaptation": "PASS",
              "installed": False, "activated": False, "tls_issued": False,
              "runtime_validated": False, "production_authorized": False,
              "requires_manual_review": True}
    for name, data in (("dsig-rec.caddy", fragment),
                       ("report.json", json.dumps(report, indent=2).encode())):
        with os.fdopen(os.open(destination / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as out:
            out.write(data)
    return dict(report, stage=destination.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--private-stage-parent", required=True, type=Path)
    parser.add_argument("--hostname", required=True)
    parser.add_argument("--caddy-image", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        print(json.dumps(stage(args.source, args.private_stage_parent, args.hostname, args.caddy_image)))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print("FAIL: Caddy staging (" + type(exc).__name__ + ")")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
