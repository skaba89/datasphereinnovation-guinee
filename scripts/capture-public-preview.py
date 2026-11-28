"""Capture real public export screenshots; never contact REC or production."""
import argparse
import functools
import hashlib
import http.server
import json
import pathlib
import re
import subprocess
import tempfile
import threading
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=pathlib.Path)
    args = parser.parse_args()
    root = pathlib.Path(__file__).resolve().parents[1]
    args.output.mkdir(parents=True, exist_ok=False)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    report = {"sha": sha, "publication_authorized": False, "human_review": "PENDING", "checks": []}
    with tempfile.TemporaryDirectory(prefix="dsig-public-preview-") as tmp:
        export = pathlib.Path(tmp) / "public"
        subprocess.run(["node", "scripts/build-public-site.mjs", str(export), "contact@dsig-consulting.com"], cwd=root, check=True)
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(export))
        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            pages = ["/", "/en.html", "/secteurs.html", "/sectors.html", "/offres-saas.html", "/offers-saas.html", "/secteurs-transport.html", "/sectors-transport.html"]
            for pattern in ("expertise-*.html", "expertise-en-*.html"):
                candidates = sorted(p for p in export.glob(pattern) if pattern != "expertise-*.html" or not p.name.startswith("expertise-en-"))
                if not candidates:
                    raise RuntimeError("Missing expertise pages")
                pages.append("/" + candidates[0].name)
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    for width in (390, 768, 1366, 1920):
                        context = browser.new_context(viewport={"width": width, "height": 900}, reduced_motion="reduce")
                        context.route("**/*", lambda route: route.continue_() if route.request.url.startswith(base + "/") else route.abort())
                        page = context.new_page()
                        for route in pages:
                            errors = []
                            listener = lambda error: errors.append(str(error))
                            page.on("pageerror", listener)
                            response = page.goto(base + route, wait_until="networkidle", timeout=30000)
                            page.evaluate("document.fonts.ready")
                            dimensions = page.evaluate("({width:document.documentElement.clientWidth, scroll:document.documentElement.scrollWidth})")
                            title_count = page.locator("h1").count()
                            file = f"{width}-{route.strip('/').replace('.html','') or 'home-fr'}.png"
                            page.screenshot(path=str(args.output / file), full_page=True, animations="disabled", timeout=30000)
                            page.remove_listener("pageerror", listener)
                            report["checks"].append({"route": route, "width": width, "http": response.status if response else None, "h1": title_count, "horizontal_overflow": dimensions["scroll"] > dimensions["width"] + 1, "page_errors": errors, "screenshot": file, "sha256": hashlib.sha256((args.output / file).read_bytes()).hexdigest()})
                        context.close()
                    browser.close()
            finally:
                server.shutdown()
                thread.join(timeout=5)
    report["status"] = "PASS" if all(x["http"] == 200 and x["h1"] == 1 and not x["horizontal_overflow"] and not x["page_errors"] for x in report["checks"]) else "FAIL"
    (args.output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Public preview: {report['status']} ({len(report['checks'])} captures); human review pending")
    return 0 if report["status"] == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
