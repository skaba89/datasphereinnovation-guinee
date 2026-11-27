"""Host-side peer identity check; never authorizes startup."""
import os
import re
import socket
import struct
import select
from pathlib import Path
import prod_backup_acquisition as acquisition
import prod_review

FORMAT='{"Id":{{json .Id}},"Image":{{json .Image}},"Running":{{json .State.Running}},"Pid":{{json .State.Pid}},"StartedAt":{{json .State.StartedAt}}}'

def inspect(sock,*,container_id,image_id,expected_uid=10001):
    result=dict(status='FAIL',startup_authorized=False,production_authorized=False)
    fd=None
    try:
        if sock.family!=socket.AF_UNIX or not re.fullmatch('[0-9a-f]{64}',container_id) or not re.fullmatch('sha256:[0-9a-f]{64}',image_id):
            return result
        pid,uid,gid=struct.unpack('3i',sock.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,struct.calcsize('3i')))
        if pid<=1 or uid!=expected_uid:
            return result
        fd=os.pidfd_open(pid)
        poll=select.poll()
        poll.register(fd,select.POLLIN)
        def snapshot():
            c=prod_review.decode(acquisition.command(['container','inspect','--format',FORMAT,container_id]).encode())
            if (c['Id']!=container_id or c['Image']!=image_id or c['Running'] is not True
                    or type(c['Pid']) is not int or c['Pid']!=pid or not c['StartedAt']):
                raise ValueError('peer not container init')
            # Read process generation from proc stat, after the final closing parenthesis.
            fields=Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()
            return c,fields[19]
        first=snapshot()
        if snapshot()!=first or poll.poll(0):
            return result
        result['status']='PASS'
    except (OSError,ValueError,TypeError,KeyError,AttributeError,IndexError,struct.error):
        pass
    finally:
        if fd is not None:
            os.close(fd)
    return result
