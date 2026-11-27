"""Explicit host actions for one approved private production container.

Never create, remove, restart, or operate on a Compose project. The caller
must complete independent approval and the orchestrator's preparation first.
"""
import os
import re
import prod_backup_acquisition as acquisition
import prod_private_executable_binding as binding
import prod_private_runtime_continuity as continuity
import prod_review


def actions(*, container_id, image_id, approved_digest):
    if os.geteuid() != 0:
        raise PermissionError('root required')
    if (not re.fullmatch('[0-9a-f]{64}', container_id)
            or not re.fullmatch('sha256:[0-9a-f]{64}', image_id)
            or not re.fullmatch('[0-9a-f]{64}', approved_digest)):
        raise ValueError('invalid pinned identity')

    def observation(cid):
        if os.geteuid() != 0 or cid != container_id:
            raise ValueError('unexpected target')
        value = prod_review.decode(acquisition.command(
            ['container','inspect','--format',binding.FORMAT,cid]).encode('utf-8'))
        labels = value['Config']['Labels']
        if (value['Id'] != cid or value['Image'] != image_id
                or labels.get('com.docker.compose.project') != 'dsig-prod'
                or labels.get('com.docker.compose.service') != 'app'):
            raise ValueError('unexpected container identity')
        return value

    def start(cid):
        value = observation(cid)
        if value['State'] != 'created' or continuity.digest(value) != approved_digest:
            raise ValueError('approved container changed')
        acquisition.command(['container','start',cid])

    def stop(cid):
        value = observation(cid)
        if value['State'] in ('created','exited','dead'):
            return
        if value['State'] != 'running':
            raise ValueError('unexpected container state; manual recovery required')
        acquisition.command(['container','stop','--time','15',cid])
        if observation(cid)['State'] != 'exited':
            raise ValueError('container stop not confirmed')

    return start, stop
