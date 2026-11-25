"""Send minimal REC incident notifications over authenticated SMTP/TLS."""
import os
import re
import smtplib
import ssl
import sys
from email.message import EmailMessage

UNITS = {
    'dsig-rec-b2.service',
    'dsig-rec-backup.service',
    'dsig-rec-monitor.service',
    'test',
}
ADDRESS = re.compile(r'[A-Za-z0-9.!#$%&\'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')


def notify(unit, env):
    if unit not in UNITS:
        raise ValueError('Unknown unit')
    host = env['DSIG_ALERT_SMTP_HOST']
    sender = env['DSIG_ALERT_FROM']
    recipient = env['DSIG_ALERT_TO']
    user = env['DSIG_ALERT_SMTP_USER']
    password = env['DSIG_ALERT_SMTP_PASSWORD']
    if not re.fullmatch(r'[A-Za-z0-9.-]+', host) or not all(ADDRESS.fullmatch(x) for x in (sender, recipient)) or not user or not password:
        raise ValueError('Invalid alert configuration')
    message = EmailMessage()
    message['From'] = sender
    message['To'] = recipient
    message['Subject'] = f'DSIG REC: {"test notification" if unit == "test" else "service failure"}'
    message.set_content(f'Environment: REC\nService: {unit}\nCheck the DSIG systemd journal on the VPS.\n')
    with smtplib.SMTP_SSL(host, 465, timeout=15, context=ssl.create_default_context()) as smtp:
        smtp.login(user, password)
        if smtp.send_message(message):
            raise ValueError('Recipient rejected')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            raise ValueError('Missing unit')
        notify(sys.argv[1], os.environ)
    except (OSError, ValueError, KeyError, smtplib.SMTPException):
        print('FAIL: alert delivery unsuccessful', file=sys.stderr)
        raise SystemExit(1)
    print('PASS: SMTP accepted notification')
