"""Longer transport deadline only. Frozen fitting/evaluation rules stay unchanged."""
from datetime import datetime
import importlib.util
import subprocess
import time
from extract_observations import ROOT, KST, write_json, digest
from heldout_protocol import DAY, verify_freeze

verify_freeze()
dest = ROOT/'private'/f'{DAY}.jsons.gz'
partial = ROOT/'private'/f'{DAY}.jsons.gz.part'
if dest.exists() or partial.exists():
    raise RuntimeError('Preserve existing archive/partial file; do not duplicate a download')
write_json(ROOT/'artifacts/fetch_failure_001.json', {
    'attempt': 1, 'curl_exit': 28, 'deadline_seconds': 55,
    'labels_parsed_or_evaluated': False, 'new_provider_polls': 0,
    'frozen_protocol_unchanged': True})
helper = ROOT.parent/'weekly_empirical_readiness_20261116/check_recording_inventory.py'
spec = importlib.util.spec_from_file_location('readonly_private_collector', helper)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
c = module.credentials()
config = ('url="'+c['url'].rstrip('/')+'/export?day='+DAY+'"\n'
          'header="Authorization: Bearer '+c['token']+'"\n')
start = time.monotonic()
r = subprocess.run(['curl.exe', '--config', '-', '--silent', '--show-error', '--fail',
                    '--max-time', '180', '--connect-timeout', '10', '--output', str(partial)],
                   input=config.encode(), capture_output=True, timeout=185)
receipt = {'day': DAY, 'attempt': 2, 'curl_exit': r.returncode,
           'elapsed_seconds': time.monotonic()-start, 'finished_at': datetime.now(KST).isoformat(),
           'partial_bytes': partial.stat().st_size if partial.exists() else 0,
           'new_provider_polls': 0, 'total_saved_export_attempts': 2,
           'transport_deadline_only_changed': True, 'script_sha256': digest(__file__)}
write_json(ROOT/'artifacts/transport_retry_receipt.json', receipt)
if r.returncode:
    raise RuntimeError('Saved export retry failed; partial bytes and receipt preserved; curl exit '+str(r.returncode))
with partial.open('rb') as stream:
    if stream.read(2) != b'\x1f\x8b':
        raise RuntimeError('Unexpected saved response; preserve without parsing labels')
assert partial.resolve().is_relative_to(ROOT.resolve()) and dest.resolve().is_relative_to(ROOT.resolve())
partial.rename(dest)
write_json(ROOT/'artifacts/holdout_opening.json', {
    'opened_at': datetime.now(KST).isoformat(), 'day': DAY, 'bytes': dest.stat().st_size,
    'sha256': digest(dest), 'total_saved_export_attempts': 2, 'new_provider_polls': 0,
    'frozen_protocol_sha256': digest(ROOT/'artifacts/frozen_protocol.json'), 'other_new_days_opened': []})
print({'saved_day': DAY, 'bytes': dest.stat().st_size, 'new_provider_polls': 0})
