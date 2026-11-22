"""Read-only probes for the public DSIG site; no credentials or redirects."""
import http.client
import json
import ssl
import time
from datetime import datetime, timezone

HOST = 'dsig-consulting.com'


def probe(path):
    connection = http.client.HTTPSConnection(HOST, timeout=8, context=ssl.create_default_context())
    start = time.monotonic()
    try:
        connection.connect()
        expires = ssl.cert_time_to_seconds(connection.sock.getpeercert()['notAfter'])
        connection.request('GET', path)
        response = connection.getresponse()
        return response.status, response.read(256 * 1024).decode('utf-8', errors='replace'), expires, round((time.monotonic()-start)*1000), response.getheader('X-Robots-Tag', '')
    finally:
        connection.close()


def monitor(check=probe, now=None):
    now = time.time() if now is None else now
    checks = {}
    for path, marker in [('/healthz', 'ok'), ('/', 'rel="canonical" href="https://dsig-consulting.com/"'), ('/robots.txt', 'Sitemap: https://dsig-consulting.com/sitemap.xml'), ('/sitemap.xml', 'https://dsig-consulting.com/en.html')]:
        try:
            status, body, expires, elapsed, robots = check(path)
            days = round((expires-now)/86400, 2)
            valid = status == 200 and marker in body and days >= 21 and elapsed <= 5000
            if path == '/':
                valid = valid and 'noindex' not in robots.lower() and 'content="index,follow,max-image-preview:large"' in body
            checks[path] = {'status':'PASS' if valid else 'FAIL', 'http':status, 'ms':elapsed, 'tls_days':days}
        except (OSError, ValueError, KeyError, http.client.HTTPException):
            checks[path] = {'status':'FAIL', 'reason':'connection_or_response_error'}
    return {'timestamp_utc':datetime.fromtimestamp(now, timezone.utc).isoformat(), 'status':'PASS' if all(c['status']=='PASS' for c in checks.values()) else 'FAIL', 'checks':checks}


if __name__ == '__main__':
    result = monitor()
    print(json.dumps(result))
    raise SystemExit(0 if result['status']=='PASS' else 1)
