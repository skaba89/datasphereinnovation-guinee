"""Commercial proposal as a downloadable PDF (stdlib only, no external dependency).

Client-facing content only: never the daily cost, expenses or margin. The issuer's legal
identifiers are not validated yet (see LEGAL_COMPLIANCE_V161.md), so none is printed and the
document is marked as a non-contractual REC document.
"""
import re
import sqlite3
import zlib
from datetime import date
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

import accounts
import quotes

PAGE_W, PAGE_H, MARGIN = 595.28, 841.89, 50
PURPLE, INK, MUTED, LIGHT = (0.208, 0.063, 0.306), (0.13, 0.11, 0.21), (0.36, 0.35, 0.42), (0.94, 0.92, 0.98)

# Helvetica advance widths (1/1000 em) for ASCII 32..126; other characters use their base letter or 556.
_W = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278] + [556] * 10 + \
     [278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
      667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556,
      278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334,
      260, 334, 584]

TEXT = {
    'fr': {'title': 'Proposition commerciale', 'ref': 'Référence', 'date': 'Date', 'validity': 'Validité', 'client': 'Client',
           'contact': 'Contact', 'subject': 'Objet', 'scope': 'Périmètre de l’intervention', 'pricing': 'Conditions financières',
           'mode': {'REGIE': 'Régie (temps passé)', 'FORFAIT': 'Forfait'}, 'designation': 'Désignation', 'qty': 'Quantité',
           'unit': 'Prix unitaire HT', 'amount': 'Montant HT', 'days': 'jours', 'flat': 'Prestation au forfait', 'total': 'Total HT',
           'terms': 'Conditions commerciales', 'to_confirm': 'À confirmer', 'page': 'Page',
           'stamp': 'RECETTE — DOCUMENT NON CONTRACTUEL',
           'footer': 'Montants hors taxes. Document de recette non contractuel : mentions légales de l’émetteur en cours de validation.'},
    'en': {'title': 'Commercial proposal', 'ref': 'Reference', 'date': 'Date', 'validity': 'Valid until', 'client': 'Client',
           'contact': 'Contact', 'subject': 'Subject', 'scope': 'Scope of work', 'pricing': 'Pricing',
           'mode': {'REGIE': 'Time and materials', 'FORFAIT': 'Fixed price'}, 'designation': 'Description', 'qty': 'Quantity',
           'unit': 'Unit price (excl. tax)', 'amount': 'Amount (excl. tax)', 'days': 'days', 'flat': 'Fixed-price engagement',
           'total': 'Total (excl. tax)', 'terms': 'Commercial terms', 'to_confirm': 'To be confirmed', 'page': 'Page',
           'stamp': 'TEST — NON-CONTRACTUAL DOCUMENT',
           'footer': 'Amounts exclude taxes. Non-contractual test document: issuer legal details pending validation.'},
}


def width(text, size, bold=False):
    import unicodedata
    total = 0
    for ch in text:
        base = unicodedata.normalize('NFKD', ch)[:1] or ch
        total += _W[ord(base) - 32] if 32 <= ord(base) <= 126 else 556
    return total * size / 1000 * (1.04 if bold else 1)


def wrap(text, size, max_width, bold=False):
    lines = []
    for paragraph in str(text).replace('\r\n', '\n').split('\n'):
        line = ''
        for word in paragraph.split(' '):
            candidate = (line + ' ' + word) if line else word
            if width(candidate, size, bold) <= max_width:
                line = candidate
                continue
            if line:
                lines.append(line)
            while width(word, size, bold) > max_width:  # very long token: hard split
                cut = max(1, int(len(word) * max_width / width(word, size, bold)))
                lines.append(word[:cut])
                word = word[cut:]
            line = word
        lines.append(line)
    return lines


def money(value, currency, language):
    amount = Decimal(value)
    digits = 0 if currency in ('GNF', 'XOF') else 2
    text = f'{amount:,.{digits}f}'
    if language == 'fr':
        text = text.replace(',', ' ').replace('.', ',').replace(' ', ' ')
    return f'{text} {currency}'


def _escape(text):
    raw = str(text).encode('cp1252', 'replace')
    return raw.replace(b'\\', b'\\\\').replace(b'(', b'\\(').replace(b')', b'\\)')


class Canvas:
    def __init__(self):
        self.pages = []
        self.ops = None

    def page(self):
        self.ops = []
        self.pages.append(self.ops)

    def color(self, rgb, stroke=False):
        self.ops.append(b'%.3f %.3f %.3f %s' % (*rgb, b'RG' if stroke else b'rg'))

    def rect(self, x, y, w, h, rgb):
        self.color(rgb)
        self.ops.append(b'%.2f %.2f %.2f %.2f re f' % (x, y, w, h))

    def line(self, x1, y1, x2, y2, rgb=MUTED, w=0.5):
        self.color(rgb, stroke=True)
        self.ops.append(b'%.2f w %.2f %.2f m %.2f %.2f l S' % (w, x1, y1, x2, y2))

    def text(self, x, y, text, size=10, bold=False, rgb=INK, align='left', angle=None):
        if align == 'right':
            x -= width(text, size, bold)
        self.color(rgb)
        font = b'/F2' if bold else b'/F1'
        if angle:
            c, s = angle
            self.ops.append(b'BT %s %.1f Tf %.4f %.4f %.4f %.4f %.2f %.2f Tm (%s) Tj ET' % (font, size, c, s, -s, c, x, y, _escape(text)))
        else:
            self.ops.append(b'BT %s %.1f Tf %.2f %.2f Td (%s) Tj ET' % (font, size, x, y, _escape(text)))

    def build(self, title):
        objects = [b'<< /Type /Catalog /Pages 2 0 R >>', None,
                   b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>',
                   b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>',
                   b'<< /Title (' + _escape(title) + b') /Producer (DSIG REC) >>']
        kids = []
        for ops in self.pages:
            stream = zlib.compress(b'\n'.join(ops))
            objects.append(b'<< /Length %d /Filter /FlateDecode >>\nstream\n' % len(stream) + stream + b'\nendstream')
            content = len(objects)
            objects.append(b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2f %.2f] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents %d 0 R >>'
                           % (PAGE_W, PAGE_H, content))
            kids.append(len(objects))
        objects[1] = b'<< /Type /Pages /Kids [%s] /Count %d >>' % (b' '.join(b'%d 0 R' % k for k in kids), len(kids))
        out, offsets = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n'), []
        for number, body in enumerate(objects, 1):
            offsets.append(len(out))
            out += b'%d 0 obj\n' % number + body + b'\nendobj\n'
        xref = len(out)
        out += b'xref\n0 %d\n0000000000 65535 f \n' % (len(objects) + 1)
        out += b''.join(b'%010d 00000 n \n' % o for o in offsets)
        out += b'trailer\n<< /Size %d /Root 1 0 R /Info 5 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(objects) + 1, xref)
        return bytes(out)


def reference(q):
    return f"DSIG-{q['created_at'][:4]}-{q['id'][:8].upper()}-v{q['version']}"


def render(q, language='fr', today=None):
    t = TEXT[language]
    today = today or date.today()
    c = Canvas()
    inner = PAGE_W - 2 * MARGIN
    state = {'y': 0}

    def new_page():
        c.page()
        c.rect(0, PAGE_H - 70, PAGE_W, 70, PURPLE)
        c.text(MARGIN, PAGE_H - 43, 'DSIG | Consulting', 20, True, (1, 1, 1))
        c.text(PAGE_W - MARGIN, PAGE_H - 43, 'DataSphere Innovation Guinée', 10, False, (1, 1, 1), 'right')
        size, (cos, sin) = 22, (0.8192, 0.5736)
        half = width(t['stamp'], size, True) / 2
        c.text(PAGE_W / 2 - half * cos, PAGE_H / 2 - 40 - half * sin, t['stamp'], size, True, (0.9, 0.88, 0.94), angle=(cos, sin))
        state['y'] = PAGE_H - 105

    def ensure(space):
        if state['y'] - space < 80:
            new_page()

    def heading(text):
        ensure(40)
        state['y'] -= 8
        c.text(MARGIN, state['y'], text, 12, True, PURPLE)
        c.line(MARGIN, state['y'] - 5, PAGE_W - MARGIN, state['y'] - 5, PURPLE, 0.8)
        state['y'] -= 22

    def paragraph(text, size=10):
        for line in wrap(text, size, inner):
            ensure(16)
            c.text(MARGIN, state['y'], line, size)
            state['y'] -= size + 4.5

    new_page()
    c.text(MARGIN, state['y'], t['title'], 22, True, PURPLE)
    state['y'] -= 30
    facts = [(t['ref'], reference(q)), (t['date'], today.isoformat()),
             (t['validity'], q.get('valid_until') or t['to_confirm']), (t['client'], q['company'])]
    if q.get('contact'):
        facts.append((t['contact'], q['contact']))
    box = 16 * len(facts) + 14
    c.rect(MARGIN, state['y'] - box + 12, inner, box, LIGHT)
    for label, value in facts:
        c.text(MARGIN + 12, state['y'], label, 10, True, MUTED)
        c.text(MARGIN + 130, state['y'], value, 10)
        state['y'] -= 16
    state['y'] -= 14

    heading(t['subject'])
    paragraph(q['title'], 11)
    heading(t['scope'])
    paragraph(q['scope'])

    heading(t['pricing'] + ' — ' + t['mode'][q['mode']])
    # Designation (left), quantity (left), unit price and amount (right-aligned, room for GNF amounts).
    cols = (MARGIN + 8, MARGIN + 205, MARGIN + 375, PAGE_W - MARGIN - 8)
    aligns = ('left', 'left', 'right', 'right')
    ensure(80)
    c.rect(MARGIN, state['y'] - 6, inner, 20, PURPLE)
    for x, label, align in zip(cols, (t['designation'], t['qty'], t['unit'], t['amount']), aligns):
        c.text(x, state['y'], label, 9, True, (1, 1, 1), align)
    state['y'] -= 24
    total = quotes.calculate(q)['revenue']
    if q['mode'] == 'REGIE':
        row = (q['title'], f"{Decimal(q['days']).normalize():f} {t['days']}", money(q['rate'], q['currency'], language))
    else:
        row = (t['flat'], '1', money(q['fixed_price'], q['currency'], language))
    designation = wrap(row[0], 10, 185)
    for i, line in enumerate(designation):
        c.text(cols[0], state['y'] - i * 14, line, 10)
    c.text(cols[1], state['y'], row[1], 10)
    c.text(cols[2], state['y'], row[2], 10, align='right')
    c.text(cols[3], state['y'], money(total, q['currency'], language), 10, align='right')
    state['y'] -= 14 * len(designation) + 4
    c.line(MARGIN, state['y'] + 6, PAGE_W - MARGIN, state['y'] + 6)
    state['y'] -= 12
    c.text(cols[1], state['y'], t['total'], 11, True, PURPLE)
    c.text(cols[3], state['y'], money(total, q['currency'], language), 11, True, PURPLE, 'right')
    state['y'] -= 26

    heading(t['terms'])
    paragraph(q.get('terms') or t['to_confirm'])

    count = len(c.pages)
    for number, ops in enumerate(c.pages, 1):
        c.ops = ops
        c.line(MARGIN, 58, PAGE_W - MARGIN, 58)
        for i, line in enumerate(wrap(t['footer'], 8, inner - 60)):
            c.text(MARGIN, 44 - i * 10, line, 8, rgb=MUTED)
        c.text(PAGE_W - MARGIN, 44, f"{t['page']} {number}/{count}", 8, rgb=MUTED, align='right')
    return c.build(f"{t['title']} {reference(q)}")


def handle(h, connect, oid):
    """GET /api/admin/quotes/<id>/pdf[?lang=fr|en] — quotes read permission."""
    if not h.admin_authorized():
        return
    query = parse_qs(urlsplit(h.path).query)
    language = query.get('lang', ['fr'])[0]
    if set(query) - {'lang'} or language not in TEXT or not re.fullmatch(r'[0-9a-f-]{36}', oid):
        return h.json_response(400, {'error': 'Paramètres invalides.'})
    with connect() as db:
        db.row_factory = sqlite3.Row
        row = db.execute('''SELECT q.*,o.company,o.contact,COALESCE(p.valid_until,'') AS valid_until,COALESCE(p.terms,'') AS terms
            FROM quotes q JOIN opportunities o ON o.id=q.opportunity_id LEFT JOIN quote_proposal_terms p ON p.quote_id=q.id
            WHERE q.id=?''', (oid,)).fetchone()
        if not row:
            return h.json_response(404, {'error': 'Devis introuvable.'})
        accounts.event(db, h.actor, 'DEVIS_PDF', oid)
    q = dict(row)
    body = render(q, language)
    h.send_response(200)
    h.send_header('Content-Type', 'application/pdf')
    h.send_header('Content-Disposition', f'attachment; filename="{reference(q)}.pdf"')
    h.send_header('Cache-Control', 'no-store')
    h.send_header('Content-Length', str(len(body)))
    h.end_headers()
    h.wfile.write(body)
