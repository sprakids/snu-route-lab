"""Check source bytes, PDF structure, links and the separation of acquisition states."""
from pathlib import Path
from pypdf import PdfReader
from datetime import datetime, timezone, timedelta
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parent
manifest = json.loads((ROOT / 'official_capture_manifest.json').read_text(encoding='utf-8'))
register = json.loads((ROOT / 'source_register.json').read_text(encoding='utf-8'))
audited = []
for row in manifest:
    for item in row['files'] + row.get('downloads', []):
        if 'file' in item:
            path = ROOT / item['file']
            assert hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256'], str(path)
            audited.append(item['file'])
night = ROOT / 'sources/O03_시험기간_야간심야_운행계획.pdf'
assert hashlib.sha256(night.read_bytes()).hexdigest() == 'f54555ec4d14c58c69dce97bc8ad4ff0bbd08315418cc153d389e6a1131f27e0'
audited.append(str(night.relative_to(ROOT)))
pdfs = sorted((ROOT / 'sources').glob('*.pdf'))
assert len(pdfs) == 9, [path.name for path in pdfs]
pdf_audit = []
for path in pdfs:
    assert path.read_bytes().startswith(b'%PDF')
    reader = PdfReader(path)
    pdf_audit.append({'file': str(path.relative_to(ROOT)), 'pages': len(reader.pages), 'bytes': path.stat().st_size,
                      'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
markdown = (ROOT / '세부배치시간_조사결과.md').read_text(encoding='utf-8')
for link in re.findall(r'\]\(([^)]+)\)', markdown):
    if not link.startswith(('http:', 'https:')):
        assert (ROOT / link).is_file(), link
bands = [line for line in markdown.splitlines() if re.match(r'^\| (통학|교내|야간도서관|심야) \|', line)]
assert len(bands) == 18, len(bands)
assert (ROOT / 'sources/O11_2.pdf').read_bytes() == (ROOT.parent / 'research/sources/S01_2026_2_shuttle_timetable.pdf').read_bytes()
termination = (ROOT / 'evidence/O13_1.txt').read_text(encoding='utf-8')
assert '2026.7.10.' in termination and '28428' in termination
verification = {
    'verified_at': datetime.now(timezone(timedelta(hours=9))).isoformat(),
    'official_document_groups': len(register), 'pdf_count': len(pdfs),
    'total_pdf_pages': sum(row['pages'] for row in pdf_audit),
    'regular_timetable_bands': len(bands), 'regular_timetable_matches_earlier_saved_bytes': True,
    'hash_audit_count': len(audited), 'hash_mismatches': 0, 'local_report_links_valid': True,
    'upper_homeward_termination_notice_acquired': True,
    'individual_vehicle_driver_duty_schedule_acquired': False,
    'current_signed_contract_business_schedule_acquired': False,
    'external_request_submitted': False, 'pdfs': pdf_audit,
}
assert verification['total_pdf_pages'] == 14
(ROOT / 'verification.json').write_text(json.dumps(verification, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({key: verification[key] for key in ['official_document_groups', 'pdf_count', 'total_pdf_pages', 'regular_timetable_bands', 'hash_mismatches']}, ensure_ascii=False))
