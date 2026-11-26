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
        except (OSError,subprocess.SubprocessError):
            raise ValueError('B2 command failed') from None

    def _json(self,args):
        try:
            return json.loads(self.run(args))
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
        return isinstance(obj,str) and QUALIFICATION_NAME.fullmatch(obj) is not None
