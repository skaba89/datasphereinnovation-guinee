"""REC delivery reconciliation from operator-verified Resend dashboard evidence."""
import argparse
import json
import os
import re
import time

EVENTS = ('sent','delivered','delivery_delayed','bounced','complained','failed','suppressed')


def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS contact_delivery_events (
        provider_id TEXT NOT NULL, event TEXT NOT NULL, verified_at INTEGER NOT NULL,
        PRIMARY KEY(provider_id,event))''')


def record(db, provider_id, event):
    if not re.fullmatch(r'[A-Za-z0-9-]{1,100}',provider_id) or event not in EVENTS:
        raise ValueError('Invalid delivery evidence')
    schema(db)
    if not db.execute("SELECT 1 FROM contact_mail WHERE provider_id=? AND state='ACCEPTED'",(provider_id,)).fetchone():
        raise ValueError('Unknown accepted notification')
    result=db.execute('INSERT OR IGNORE INTO contact_delivery_events VALUES (?,?,?)',(provider_id,event,int(time.time())))
    return result.rowcount == 1


def status(db, request_ids=None):
    schema(db)
    if request_ids is not None and not request_ids:
        return []
    where = '' if request_ids is None else ' WHERE m.request_id IN (' + ','.join('?' for _ in request_ids) + ')'
    rows=db.execute('''SELECT m.request_id,m.kind,m.language,m.state,m.provider_id,
        (SELECT group_concat(event) FROM contact_delivery_events e WHERE e.provider_id=m.provider_id)
        FROM contact_mail m''' + where + ' ORDER BY m.created DESC,m.kind', tuple(request_ids or ())).fetchall()
    result=[]
    for rid,kind,language,state,pid,events in rows:
        observed=set((events or '').split(','))
        # Negative terminal evidence wins; a delayed event cannot undo delivery.
        delivery=next((e for e in ('complained','bounced','suppressed','failed','delivered','delivery_delayed','sent') if e in observed),None)
        result.append(dict(request_id=rid,kind=kind,language=language,queue_state=state,provider_id=pid,delivery=delivery or 'unverified'))
    return result


def for_requests(db, request_ids):
    """Redacted communication history, restricted to the current request page."""
    grouped = {rid: [] for rid in request_ids}
    for row in status(db, request_ids):
        grouped[row['request_id']].append({
            'kind': row['kind'], 'language': row['language'],
            'queue_state': row['queue_state'], 'delivery': row['delivery'],
        })
    return grouped


def main():
    if os.environ.get('DSIG_ENV')!='REC':raise SystemExit('REC uniquement.')
    import server
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='action',required=True)
    sub.add_parser('status')
    r=sub.add_parser('record');r.add_argument('provider_id');r.add_argument('event',choices=EVENTS)
    args=p.parse_args()
    with server.connect() as db:
        if args.action=='status':print(json.dumps(status(db),ensure_ascii=False))
        else:
            try:print(json.dumps({'recorded':record(db,args.provider_id,args.event)}))
            except ValueError as exc:raise SystemExit(str(exc))


if __name__=='__main__':main()
