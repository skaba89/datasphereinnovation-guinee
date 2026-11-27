"""Fail-closed scanner qualification; never grants startup authorization."""
import os
import stat
from pathlib import Path
import antivirus
from check_antivirus import EICAR

SOCKET='/run/dsig-clamav/clamd.ctl'

def inspect():
    checks=dict.fromkeys(('configuration','socket','clean','eicar_rejected','stable_socket'),'NOT_RUN')
    result=dict(status='FAIL',checks=checks,production_authorized=False,startup_authorized=False)
    try:
        checks['configuration']='FAIL'
        if os.environ.get('DSIG_ENV')!='PROD' or os.environ.get('DSIG_CLAMD_SOCKET')!=SOCKET:
            return result
        checks['configuration']='PASS'
        checks['socket']='FAIL'
        path=Path(SOCKET)
        before=path.lstat()
        if not stat.S_ISSOCK(before.st_mode):
            return result
        checks['socket']='PASS'
        checks['clean']='FAIL'
        antivirus.scan(b'DSIG private production scanner qualification')
        checks['clean']='PASS'
        checks['eicar_rejected']='FAIL'
        try:
            antivirus.scan(EICAR)
        except antivirus.Infected:
            checks['eicar_rejected']='PASS'
        if checks['eicar_rejected']!='PASS':
            return result
        checks['stable_socket']='FAIL'
        after=path.lstat()
        if (before.st_dev,before.st_ino,before.st_uid,before.st_gid,before.st_mode)!=(
                after.st_dev,after.st_ino,after.st_uid,after.st_gid,after.st_mode):
            return result
        checks['stable_socket']='PASS'
        result['status']='PASS'
    except (OSError,ValueError,antivirus.Unavailable,antivirus.Infected):
        pass
    return result
