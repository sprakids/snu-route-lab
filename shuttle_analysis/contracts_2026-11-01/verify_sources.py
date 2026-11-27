"""Audit saved source bytes and document-acquisition status; no network access."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib
import json

ROOT = Path(__file__).resolve().parent
registry = json.loads((ROOT / 'source_register.json').read_text(encoding='utf-8-sig'))
initial = json.loads((ROOT / 'capture_manifest.json').read_text(encoding='utf-8-sig'))
followup = json.loads((ROOT / 'original_search/extraction_manifest.json').read_text(encoding='utf-8-sig'))
notice = json.loads((ROOT / 'original_search/notice_checks.json').read_text(encoding='utf-8-sig'))
assert len({row['id'] for row in registry}) == len(registry)
audited = []
for row in initial:
    if row['saved_file']:
        path = ROOT / row['saved_file']
        audited.append({'file': row['saved_file'], 'matches': hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256']})
for row in followup['files']:
    path = ROOT / 'original_search' / row['file']
    audited.append({'file': 'original_search/' + row['file'], 'matches': hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256']})
assert all(row['matches'] for row in audited)
assert notice['budget_reconciles'] and notice['source_strings_present']
assert notice['all_vehicle_sum'] == 38 and notice['route_count'] == 8
output = {
    'verified_at': datetime.now(timezone(timedelta(hours=9))).isoformat(),
    'source_register_count': len(registry),
    'initial_capture_manifest_scope': 'P01-P08, B01-B02; 10 initial sources only',
    'initial_capture_count': len(initial),
    'initial_html_saved_count': sum(bool(row['saved_file']) for row in initial),
    'initial_html_failed_ids': [row['id'] for row in initial if not row['saved_file']],
    'followup_preserved_html_count': len(followup['files']),
    'followup_metadata_web_read_only_ids': ['I03'],
    'saved_html_hash_audit': audited,
    'hash_mismatch_count': sum(not row['matches'] for row in audited),
    'excerpt_image_sha256': hashlib.sha256((ROOT / 'sources/B01_보도게재_과업지시서_제5조_발췌.jpg').read_bytes()).hexdigest(),
    'excerpt_image_visually_reviewed': True,
    'public_preserved_tender_notice_body_acquired': True,
    'notice_number': '20231243066-01',
    'official_hwp_original_acquired': False,
    'signed_contract_acquired': False,
    'current_2026_third_year_contract_acquired': False,
    'full_task_specification_acquired': False,
    'full_business_schedule_acquired': False,
    'external_request_submitted': False,
    'semantic_reconciliation_file': 'original_search/notice_checks.json',
}
(ROOT / 'verification.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({key: output[key] for key in ['source_register_count', 'initial_html_saved_count', 'followup_preserved_html_count', 'hash_mismatch_count', 'signed_contract_acquired']}, ensure_ascii=False))
