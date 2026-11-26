"""Dedicated B2 CLI adapter for isolated review, not a production scheduler."""
import json
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path
from prod_b2_export import BUCKET, NAME
QUALIFICATION_NAME=re.compile(r'prod/qualification/v232/[0-9a-f]{32}/dsig-prod-[0-9]{8}T[0-9]{6}Z\.dsigbak')

CAPABILITIES={'listBuckets','listFiles','readFiles','writeFiles',
              'readBucketEncryption','readBucketRetentions','readFileRetentions'}
MAX_BYTES=128*1024*1024


class B2ReadTimeout(ValueError):
    """Timeout of a read-only CLI command; no command output exposed."""


class B2ReviewAdapter:
    def __init__(self, expected_bucket_id, *, run=None):
        if not re.fullmatch(r'[A-Za-z0-9_-]{8,128}',expected_bucket_id):
            raise ValueError('invalid bucket identity')
        self.expected=expected_bucket_id
        self.home=Path.home()
        self.account=self.home/'.config/dsig-prod-b2/account.sqlite'
        self.binary=self.home/'.local/bin/b2'
        self.run=run or self._command

    def _command(self,args):
        for path,mode in ((self.account.parent,0o700),(self.account,0o600)):
            info=path.lstat()
            kind=stat.S_ISDIR if path==self.account.parent else stat.S_ISREG
            if not kind(info.st_mode) or stat.S_IMODE(info.st_mode)!=mode or info.st_uid!=os.getuid():
                raise ValueError('unsafe dedicated B2 session')
        env={'HOME':str(self.home),'PATH':'/usr/bin:/bin','B2_ACCOUNT_INFO':str(self.account)}
        try:
            result=subprocess.run([str(self.binary),*args],env=env,stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL,timeout=600,check=True)
            return result.stdout
        except subprocess.TimeoutExpired:
            if tuple(args[:2]) in {('account','get'),('bucket','get'),('file','download')} or args[:1]==['ls']:
                raise B2ReadTimeout('B2 read timed out') from None
            raise ValueError('B2 write outcome uncertain') from None
        except (OSError,subprocess.SubprocessError):
            raise ValueError('B2 command failed') from None

    def _json(self,args):
        try:
            return json.loads(self.run(args))
        except B2ReadTimeout:
            raise
        except (ValueError,TypeError):
            raise ValueError('invalid B2 response') from None

    def bucket_info(self,bucket):
        if bucket!=BUCKET:
            raise ValueError('invalid bucket')
        a=self._json(['account','get'])
        allowed=a['allowed']
        if (a.get('isMasterKey') is not False or set(allowed['capabilities'])!=CAPABILITIES
                or allowed['namePrefix']!='prod/'
                or allowed['buckets']!=[{'id':self.expected,'name':BUCKET}]):
            raise ValueError('unsafe B2 credentials')
        b=self._json(['bucket','get',BUCKET])
        retention=b['defaultRetention']
        period=retention['period']
        encryption=b['defaultServerSideEncryption']
        if (b['bucketId']!=self.expected or b['bucketName']!=BUCKET or b['bucketType']!='allPrivate'
                or b['isFileLockEnabled'] is not True or period['unit']!='days'
                or retention['mode']!='compliance' or type(period['duration']) is not int or period['duration']<30
                or encryption['mode']!='SSE-B2' or encryption['algorithm']!='AES256'):
            raise ValueError('unsafe B2 bucket')
        return dict(bucketName=BUCKET,bucketId=self.expected,bucketType='allPrivate',
                    encryption='SSE-B2',lock_mode='compliance',lock_days=period['duration'])

    def _allowed_object(self,obj):
        parts=obj.split('/')
        match=NAME.fullmatch(parts[-1])
        return bool(len(parts)==4 and parts[0]=='prod' and match
                    and parts[1]==match.group(1)[:4] and parts[2]==match.group(1)[4:6])

    def _versions(self,bucket,obj):
        if bucket!=BUCKET or not self._allowed_object(obj):
            raise ValueError('invalid PROD object')
        self.bucket_info(bucket)
        rows=self._json(['ls','--recursive','--versions','--json',f'b2://{BUCKET}/{obj}'])
        if not isinstance(rows,list) or any(not isinstance(x,dict) or not isinstance(x.get('fileName'),str) for x in rows):
            raise ValueError('invalid versions')
        matches=[x for x in rows if x['fileName']==obj]
        if len(matches)>1 or any(x.get('action')!='upload' for x in matches):
            raise ValueError('ambiguous remote versions')
        return matches

    def read(self,bucket,obj):
        rows=self._versions(bucket,obj)
        if not rows:
            return None
        with tempfile.TemporaryDirectory(prefix='dsig-prod-b2-read-') as tmp:
            dest=Path(tmp)/'archive'
            self.run(['file','download','--no-progress',f'b2://{BUCKET}/{obj}',str(dest)])
            with dest.open('rb') as handle:
                data=handle.read(MAX_BYTES+1)
            if not 0<len(data)<=MAX_BYTES or self._versions(bucket,obj)!=rows:
                raise ValueError('remote version changed')
            return data

    def create_only(self,bucket,obj,data):
        # B2 upload is versioned, not an atomic create-if-absent. Single writer required.
        if self._versions(bucket,obj):
            raise ValueError('remote object already exists')
        if not isinstance(data,bytes) or not 0<len(data)<=MAX_BYTES:
            raise ValueError('invalid archive size')
        with tempfile.TemporaryDirectory(prefix='dsig-prod-b2-write-') as tmp:
            path=Path(tmp)/'archive'
            path.write_bytes(data)
            path.chmod(0o600)
            self.run(['file','upload','--no-progress',BUCKET,str(path),obj])
        if len(self._versions(bucket,obj))!=1:
            raise ValueError('upload not uniquely verified')


class B2QualificationAdapter(B2ReviewAdapter):
    """Restricted to unique V232 qualification namespaces, never business paths."""
    def _allowed_object(self,obj):
        return isinstance(obj,str) and (QUALIFICATION_NAME.fullmatch(obj) is not None or re.fullmatch(r'prod/qualification/v232/[0-9a-f]{32}/journal-anchor\.json',obj) is not None or re.fullmatch(r'prod/qualification/v232/[0-9a-f]{32}/retry/[0-9]{4}-[0-9]{2}-[0-9]{2}/audit/[1-5]\.(start|end)\.json',obj) is not None)


    def read_retry_records(self,bucket,run_id,day):
        """Fresh bounded version inventory, download present records, re-list.
        
        Never caches bytes across calls. Unknown objects and duplicate/hide
        versions within the exact audit prefix fail closed.
        """
        from datetime import date
        if bucket!=BUCKET or not isinstance(run_id,str) or not re.fullmatch(r'[0-9a-f]{32}',run_id):
            raise ValueError('invalid retry namespace')
        if not isinstance(day,str) or date.fromisoformat(day).isoformat()!=day:
            raise ValueError('invalid retry date')
        prefix=f'prod/qualification/v232/{run_id}/retry/{day}/audit/'
        allowed={prefix+f'{i}.{event}.json' for i in range(1,6) for event in ('start','end')}

        def inventory():
            self.bucket_info(bucket)
            rows=self._json(['ls','--recursive','--versions','--json',f'b2://{BUCKET}/{prefix}'])
            if not isinstance(rows,list) or len(rows)>10:
                raise ValueError('invalid retry inventory')
            out={}
            for row in rows:
                if not isinstance(row,dict):
                    raise ValueError('invalid retry version')
                name=row.get('fileName')
                if not isinstance(name,str) or name not in allowed or name in out or row.get('action')!='upload':
                    raise ValueError('ambiguous retry versions')
                if not isinstance(row.get('fileId'),str) or not row['fileId']:
                    raise ValueError('missing retry version identity')
                out[name]=row
            return out

        before=inventory()
        records={}
        with tempfile.TemporaryDirectory(prefix='dsig-retry-batch-') as tmp:
            for i,name in enumerate(sorted(before)):
                dest=Path(tmp)/str(i)
                self.run(['file','download','--no-progress',f'b2://{BUCKET}/{name}',str(dest)])
                with dest.open('rb') as handle:
                    data=handle.read(8193)
                if not 0<len(data)<=8192:
                    raise ValueError('invalid retry record size')
                records[name]=data
        if inventory()!=before:
            raise ValueError('retry inventory changed')
        return records


class B2SlotQualificationAdapter(B2QualificationAdapter):
    """Only the distinct V232 slot namespace; never legacy or business objects."""
    def _allowed_object(self,obj):
        if not isinstance(obj,str):
            return False
        m=re.fullmatch(r'prod/qualification/v232-slots/[0-9a-f]{32}/([0-9]{4}-[0-9]{2}-[0-9]{2})-(01|13)/(.+)',obj)
        if not m:
            return False
        from datetime import date
        day,hour,tail=m.groups()
        try:
            if date.fromisoformat(day).isoformat()!=day:return False
        except ValueError:return False
        return (tail=='journal-anchor.json'
                or tail==f"dsig-prod-{day.replace('-','')}T{hour}1500Z.dsigbak"
                or re.fullmatch(r'retry/audit/[1-5]\.(start|end)\.json',tail) is not None)

    def read_retry_records(self,*args,**kwargs):
        raise ValueError('legacy retry namespace refused')

    def read_slot_retry_records(self,bucket,run_id,day):
        prefix=f'prod/qualification/v232-slots/{run_id}/{day}/retry/audit/'
        if bucket!=BUCKET or not self._allowed_object(prefix+'1.start.json'):
            raise ValueError('invalid slot inventory')
        allowed={prefix+f'{i}.{event}.json' for i in range(1,6) for event in ('start','end')}
        def inventory():
            self.bucket_info(bucket)
            rows=self._json(['ls','--recursive','--versions','--json',f'b2://{BUCKET}/{prefix}'])
            if not isinstance(rows,list) or len(rows)>10:raise ValueError('invalid slot inventory')
            out={}
            for row in rows:
                if not isinstance(row,dict):raise ValueError('invalid slot version')
                name=row.get('fileName')
                if not isinstance(name,str) or name not in allowed or name in out or row.get('action')!='upload' or not isinstance(row.get('fileId'),str) or not row['fileId']:
                    raise ValueError('ambiguous slot versions')
                out[name]=row
            return out
        before=inventory()
        records={}
        with tempfile.TemporaryDirectory(prefix='dsig-slot-batch-') as tmp:
            for i,name in enumerate(sorted(before)):
                dest=Path(tmp)/str(i)
                self.run(['file','download','--no-progress',f'b2://{BUCKET}/{name}',str(dest)])
                with dest.open('rb') as handle:data=handle.read(8193)
                if not 0<len(data)<=8192:raise ValueError('invalid slot record size')
                records[name]=data
        if inventory()!=before:raise ValueError('slot inventory changed')
        return records
