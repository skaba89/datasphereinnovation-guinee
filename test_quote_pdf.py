"""Quote PDF: valid structure, client-facing content only, languages, pagination and permissions."""
import json
import os
import re
import tempfile
import threading
import unittest
import zlib
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

import quote_pdf
import server


def pdf_text(pdf):
    """Decompressed content streams (text drawing operators), decoded as cp1252."""
    streams = re.findall(rb'stream\n(.*?)\nendstream', pdf, re.S)
    return b'\n'.join(zlib.decompress(s) for s in streams).decode('cp1252')


def check_structure(test, pdf):
    test.assertTrue(pdf.startswith(b'%PDF-1.4\n'))
    test.assertTrue(pdf.endswith(b'%%EOF\n'))
    start = int(re.search(rb'startxref\n(\d+)\n', pdf).group(1))
    test.assertTrue(pdf[start:].startswith(b'xref\n'))
    entries = re.findall(rb'(\d{10}) 00000 n ', pdf[start:])
    for number, offset in enumerate(entries, 1):
        test.assertTrue(pdf[int(offset):].startswith(b'%d 0 obj' % number), number)


class QuotePdfTests(unittest.TestCase):
    QUOTE = {'id': '12345678-aaaa-bbbb-cccc-1234567890ab', 'version': 3, 'created_at': '2026-11-20 10:00:00', 'company': 'Société (fictive)',
             'contact': 'Awa Fictive', 'title': 'Audit data', 'scope': 'Diagnostic, ateliers et feuille de route.', 'mode': 'REGIE',
             'currency': 'GNF', 'days': '12', 'rate': '4500000', 'daily_cost': '3123457', 'expenses': '777777', 'fixed_price': '0',
             'valid_until': '2099-01-01', 'terms': 'Paiement à 30 jours.'}

    def test_structure_content_and_no_internal_costs(self):
        pdf = quote_pdf.render(self.QUOTE)
        check_structure(self, pdf)
        text = pdf_text(pdf)
        for expected in ('Proposition commerciale', 'DSIG-2026-12345678-v3', 'Soci\xe9t\xe9 \\(fictive\\)', '54 000 000 GNF',
                         '4 500 000 GNF', '12 jours', 'Paiement \xe0 30 jours.', 'RECETTE \u2014 DOCUMENT NON CONTRACTUEL', 'Page 1/1'):
            self.assertIn(expected, text)
        for internal in ('3123457', '3 123 457', '777777', '777 777', 'marge', 'Marge', 'co\xfbt'):
            self.assertNotIn(internal, text)

    def test_english_fixed_price_and_pagination(self):
        pdf = quote_pdf.render(self.QUOTE | {'mode': 'FORFAIT', 'currency': 'EUR', 'fixed_price': '18500.5', 'scope': 'Long scope. ' * 900}, 'en')
        check_structure(self, pdf)
        text = pdf_text(pdf)
        self.assertIn('Commercial proposal', text)
        self.assertIn('18,500.50 EUR', text)
        self.assertIn('Fixed-price engagement', text)
        pages = int(re.search(rb'/Count (\d+)', pdf).group(1))
        self.assertGreater(pages, 2)
        self.assertIn(f'Page {pages}/{pages}', text)

    def test_wrap_and_money(self):
        lines = quote_pdf.wrap('mot ' * 200 + 'x' * 300, 10, 200)
        self.assertTrue(all(quote_pdf.width(line, 10) <= 200 for line in lines))
        self.assertEqual(quote_pdf.money('1234567.5', 'EUR', 'fr'), '1 234 567,50 EUR')
        self.assertEqual(quote_pdf.money('1234567', 'XOF', 'en'), '1,234,567 XOF')


class QuotePdfApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        mfa = patch.dict(os.environ, {'DSIG_MFA_REQUIRED_ROLES': ''})
        mfa.start()
        self.addCleanup(mfa.stop)
        self.original, self.original_token = server.DB, server.ADMIN_TOKEN
        server.DB = Path(self.tmp.name) / 'pdf.sqlite3'
        server.ADMIN_TOKEN = 'test-token-only-' + 'x' * 32
        server.RATE.clear()
        self.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.admin = {'Authorization': 'Bearer ' + server.ADMIN_TOKEN, 'Content-Type': 'application/json'}
        opp = {'company': 'Client PDF fictif', 'contact': 'Contact PDF', 'email': '', 'title': 'Projet PDF', 'mode': 'REGIE', 'skills': '',
               'consultant_id': '', 'next_action': '', 'followup': '', 'notes': '', 'status': 'PROPOSITION'}
        oid = self.call('POST', '/api/admin/crm', opp, self.admin)[1]['id']
        quote = {'opportunity_id': oid, 'title': 'Devis PDF', 'scope': 'Fictif', 'mode': 'REGIE', 'currency': 'EUR', 'days': '5', 'rate': '600',
                 'daily_cost': '432.17', 'expenses': '0', 'fixed_price': '0', 'status': 'BROUILLON'}
        self.qid = self.call('POST', '/api/admin/quotes', quote, self.admin)[1]['id']

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        server.DB, server.ADMIN_TOKEN = self.original, self.original_token
        self.tmp.cleanup()

    def call(self, method, path, payload=None, headers=None):
        conn = HTTPConnection('127.0.0.1', self.http.server_address[1], timeout=5)
        conn.request(method, path, None if payload is None else json.dumps(payload), headers or {})
        res = conn.getresponse()
        body, hdrs = res.read(), dict(res.getheaders())
        conn.close()
        return res.status, (json.loads(body) if body and hdrs.get('Content-Type', '').startswith('application/json') else body), hdrs

    def account(self, role):
        key = self.call('POST', '/api/admin/accounts', {'username': role.lower() + '.pdf', 'role': role, 'consultant_id': ''}, self.admin)[1]['key']
        return {'Authorization': 'Bearer ' + key}

    def test_download_and_permissions(self):
        status, pdf, headers = self.call('GET', f'/api/admin/quotes/{self.qid}/pdf', headers=self.admin)
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'application/pdf')
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertRegex(headers['Content-Disposition'], r'^attachment; filename="DSIG-\d{4}-[0-9A-F]{8}-v1\.pdf"$')
        check_structure(self, pdf)
        text = pdf_text(pdf)
        self.assertIn('3 000,00 EUR', text)
        self.assertIn('Contact PDF', text)
        self.assertNotIn('432', text)
        self.assertEqual(self.call('GET', f'/api/admin/quotes/{self.qid}/pdf?lang=en', headers=self.admin)[0], 200)
        self.assertEqual(self.call('GET', f'/api/admin/quotes/{self.qid}/pdf?lang=de', headers=self.admin)[0], 400)
        self.assertEqual(self.call('GET', '/api/admin/quotes/00000000-0000-0000-0000-000000000000/pdf', headers=self.admin)[0], 404)
        self.assertEqual(self.call('GET', f'/api/admin/quotes/{self.qid}/pdf')[0], 401)
        self.assertEqual(self.call('GET', f'/api/admin/quotes/{self.qid}/pdf', headers=self.account('PROJET'))[0], 200)  # quotes read
        self.assertEqual(self.call('GET', f'/api/admin/quotes/{self.qid}/pdf', headers=self.account('RH'))[0], 403)
        with server.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM access_events WHERE action='DEVIS_PDF'").fetchone()[0], 3)


if __name__ == '__main__':
    unittest.main()
