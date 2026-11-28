"""Pure REC promotion planning. No Docker, filesystem writes or activation."""
import copy
import hashlib
import json
import re

from verify_rec_config import validate

SHA = r'[0-9a-f]{40}'
IMAGE = r'sha256:[0-9a-f]{64}'
HASH = r'[0-9a-f]{64}'
REQUIRED = (
    'local_regression_verified', 'image_content_verified',
    'exact_commit_ci_verified', 'forward_restore_verified',
    'backward_restore_verified', 'application_startup_verified',
    'business_api_write_verified', 'business_rollback_verified',
    'revision_label_verified',
)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def manifest_config(manifest, raw):
    fields = {'schema_version', 'release_id', 'release_name', 'environment',
              'git_commit', 'image_id', 'image_reference', 'configuration_file',
              'configuration_sha256', 'qualification', 'production_authorized',
              'startup_authorized'}
    if set(manifest) != fields or type(manifest['schema_version']) is not int or manifest['schema_version'] != 1:
        raise ValueError('manifest schema')
    commit = manifest['git_commit']
    if not re.fullmatch(SHA, commit) or manifest['release_id'] != commit:
        raise ValueError('commit')
    if not re.fullmatch(IMAGE, manifest['image_id']):
        raise ValueError('image')
    if (manifest['environment'] != 'REC' or manifest['production_authorized'] is not False
            or manifest['startup_authorized'] is not False
            or manifest['configuration_file'] != 'compose.approved.json'
            or manifest['configuration_sha256'] != digest(raw)):
        raise ValueError('manifest binding')
    if not isinstance(manifest['qualification'], dict):
        raise ValueError('qualification')
    config = json.loads(raw)
    if validate(config, 'rec', 'dsig-rec_dsig-data')['status'] != 'PASS':
        raise ValueError('topology')
    service = config['services']['dsig']
    if (service['image'] != manifest['image_reference']
            or str(service['ports'][0]['published']) != '8300'
            or service['environment']['DSIG_HTTPS_ORIGIN'] != 'https://rec.dsig-consulting.com'
            or set(service['networks']) != {'default', 'edge'}
            or 'dsig-rec' not in service['networks']['edge']['aliases']
            or config['networks']['default']['name'] != 'dsig-rec_default'
            or config['networks']['edge']['name'] != 'edge'
            or config['networks']['edge']['external'] is not True):
        raise ValueError('REC binding')
    return config


def plan(active, active_raw, candidate, candidate_raw, qualification_raw, ci_raw, image_report):
    """Evaluate supplied evidence only. PASS is not authorization or live verification."""
    checks = dict.fromkeys(('active_manifest', 'candidate_manifest', 'distinct_release',
                            'only_image_changed', 'qualification', 'evidence_binding',
                            'ci_exact', 'oci_image'), False)
    try:
        before = manifest_config(active, active_raw)
        checks['active_manifest'] = True
        after = manifest_config(candidate, candidate_raw)
        checks['candidate_manifest'] = True
        checks['distinct_release'] = (active['release_id'] != candidate['release_id']
                                      and active['image_id'] != candidate['image_id'])
        a, b = copy.deepcopy(before), copy.deepcopy(after)
        for config in (a, b):
            config['services']['dsig'].pop('image')
        checks['only_image_changed'] = a == b
        q = candidate['qualification']
        checks['qualification'] = (q.get('type') == 'isolated_candidate'
            and q.get('status') == 'QUALIFIED_INACTIVE'
            and q.get('new_release_activation_authorized') is False
            and all(q.get(key) is True for key in REQUIRED))
        local, ci = json.loads(qualification_raw), json.loads(ci_raw)
        evidence = q['evidence']
        checks['evidence_binding'] = (
            evidence['qualification_sha256'] == digest(qualification_raw)
            and evidence['ci_proof_sha256'] == digest(ci_raw)
            and local['git_commit'] == candidate['git_commit']
            and local['image_id'] == candidate['image_id']
            and local['baseline_image_id'] == active['image_id']
            and local['qualification_status'] == 'LOCAL_PASS'
            and set(local['checks']) == {'local_regression', 'image_integrity', 'forward_restore',
                'backward_restore', 'sqlite_compatibility', 'application_startup',
                'business_api_write', 'business_rollback'}
            and all(value is True for value in local['checks'].values())
            and all(report.get(flag) is False for report in (local, ci)
                    for flag in ('activation_authorized', 'production_authorized', 'startup_authorized')))
        jobs = ci['jobs']
        checks['ci_exact'] = (ci['git_commit'] == candidate['git_commit']
            and ci['exact_commit_ci_verified'] is True
            and ci['run_id'] == q['ci_run_id']
            and ci['branch'] == 'main' and ci['event'] == 'push' and ci['workflow'] == 'ci.yml'
            and ci['jobs_verified'] == len(jobs) == 5
            and len({job['id'] for job in jobs}) == 5
            and all(job['conclusion'] == 'success' for job in jobs))
        checks['oci_image'] = (image_report['status'] == 'PASS'
            and image_report['git_commit'] == candidate['git_commit']
            and image_report['image_id'] == candidate['image_id']
            and image_report['qualification_local'] is True
            and image_report['ci_local'] is False
            and image_report['revision_required'] is True
            and image_report['production_authorized'] is False
            and image_report['checks'] == dict.fromkeys(
                ('source_manifest', 'immutable_reference', 'image_identity', 'content_matches', 'revision'), 'PASS'))
    except (KeyError, TypeError, ValueError, AttributeError, IndexError):
        pass
    return {'status': 'PASS' if all(checks.values()) else 'FAIL',
            'checks': checks, 'mode': 'simulation', 'live_state_verified': False,
            'activation_authorized': False, 'activation_executed': False,
            'startup_authorized': False, 'production_authorized': False}
