"""Send a minimal public-site incident email with dedicated SMTP settings."""
import os
import re
import smtplib
import ssl
from email.message import EmailMessage


def notify(env, smtp_factory=smtplib.SMTP_SSL):
    host, sender, recipient, user, password = (env['DSIG_PUBLIC_ALERT_'+key] for key in ('SMTP_HOST','FROM','TO','SMTP_USER','SMTP_PASSWORD'))
    address = r'[A-Za-z0-9._+%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
    if not re.fullmatch(r'[A-Za-z0-9.-]+',host) or not all(re.fullmatch(address,x) for x in (sender,recipient)) or not user or not password:
        raise ValueError('Invalid alert settings')
    message = EmailMessage()
    message['From'], message['To'] = sender, recipient
    message['Subject'] = 'DSIG public: monitoring failure'
    message.set_content('Check dsig-public-monitor.service in the VPS journal. No automatic restart or deployment was performed.\n')
    with smtp_factory(host,465,timeout=15,context=ssl.create_default_context()) as smtp:
        smtp.login(user,password)
        if smtp.send_message(message): raise ValueError('Recipient rejected')


if __name__ == '__main__':
    try:
        notify(os.environ)
    except (OSError, ValueError, KeyError, smtplib.SMTPException):
        print('FAIL: public alert delivery unsuccessful')
        raise SystemExit(1)
    print('PASS: SMTP accepted public alert')
