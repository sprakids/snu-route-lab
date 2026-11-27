"""Read-only, independently reconstructed audit of the user-supplied July snapshot.

Run from any directory. Requires xlrd==2.0.2 (installed into ../.deps here).
Writes audit evidence under research/evidence; never modifies the handoff.
"""
from pathlib import Path
import sys, csv, json, re, hashlib
from collections import Counter

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / '.deps'))
import xlrd

INPUT = ROOT.parent / 'input_handoff'
OUT = ROOT / 'evidence'
OUT.mkdir(exist_ok=True)
source = INPUT / 'raw/2026_2_courses_published_2026_07_03_revised.xls'
book = xlrd.open_workbook(source)
sheet = book.sheet_by_index(0)
headers = sheet.row_values(2)
provided = list(csv.DictReader((INPUT / 'sections_raw.csv').open(encoding='utf-8-sig')))
provided_slots = list(csv.DictReader((INPUT / 'meeting_slots_raw.csv').open(encoding='utf-8-sig')))
sections = [{h: str(sheet.cell_value(i, j)) for j, h in enumerate(headers)} |
            {'source_excel_row': str(i+1)} for i in range(3, sheet.nrows)]
cell_mismatches = []
assert len(provided) == len(sections), 'Section row count mismatch'
for actual, reference in zip(provided, sections):
    for field in headers + ['source_excel_row']:
        if actual[field] != reference[field]:
            cell_mismatches.append({'row':reference['source_excel_row'], 'field':field})

slot_reference, unparsed, alignment_errors = [], [], []
for row in sections:
    times = row['수업교시'].split('/') if row['수업교시'] else []
    rooms = row['강의실(동-호)(#연건, *평창)'].split('/')
    types = row['수업형태'].split('/')
    if times and not len(times) == len(rooms) == len(types):
        alignment_errors.append(row['source_excel_row'])
        continue
    for i, time in enumerate(times):
        match = re.fullmatch(r'([월화수목금토일])\((\d\d:\d\d)~(\d\d:\d\d)\)', time.strip())
        if not match:
            unparsed.append({'row':row['source_excel_row'], 'time':time})
            continue
        day, start, end = match.groups()
        room, typ = rooms[i], types[i]
        assert start < end, (row['source_excel_row'], time)
        slot_reference.append({
            'section_id':row['교과목번호']+'-'+row['강좌번호'],
            'source_excel_row':row['source_excel_row'], 'meeting_index':str(i+1),
            'weekday':day, 'start':start, 'end':end,
            'meeting_room_raw':room, 'meeting_type_raw':typ,
            'campus_source_marker':'연건: source # marker' if '#' in room else
                                   '평창: source * marker' if '*' in room else '미확정',
            'capacity_raw':row['정원'], 'offering_college':row['개설대학'],
            'offering_department':row['개설학과'], 'course_category':row['교과구분'],
            'degree_level':row['이수과정'], 'course_title':row['교과목명'],
            'notes_raw':row['비고'], 'has_circled_c_marker':str('ⓒ' in row['비고']),
            'possible_lab_subgroup':str(bool(re.search(r'실습반\d', typ))),
        })
assert len(provided_slots) == len(slot_reference), 'Meeting row count mismatch'
slot_mismatches = []
for actual, reference in zip(provided_slots, slot_reference):
    for field in reference:
        if actual[field] != reference[field]:
            slot_mismatches.append({'row':reference['source_excel_row'],
                                    'meeting_index':reference['meeting_index'], 'field':field})
capacity_pairs = [re.fullmatch(r'(\d+)\s*\((\d+)\)', r['정원']) for r in sections]
keys = [(r['교과목번호'],r['강좌번호']) for r in sections]
meta = json.loads((INPUT / 'provenance_and_coverage.json').read_text(encoding='utf-8'))
audit = {
    'dataset_label':'7월 공개 수강편람 기반 예비 분석',
    'snapshot_basis_kst':'2026-07-03T10:00:00+09:00',
    'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
    'sha256_matches_handoff_metadata':hashlib.sha256(source.read_bytes()).hexdigest()==meta['source_sha256'],
    'section_rows':len(sections), 'original_columns':len(headers),
    'original_cells_compared':len(sections)*len(headers),
    'source_row_mapping_comparisons':len(sections),
    'cell_mismatches':cell_mismatches,
    'unique_section_keys':len(set(keys)), 'duplicate_section_keys':len(keys)-len(set(keys)),
    'sections_with_time':sum(bool(r['수업교시']) for r in sections),
    'sections_without_time':sum(not r['수업교시'] for r in sections),
    'meeting_rows_reparsed':len(slot_reference),
    'meeting_fields_compared':sum(len(s) for s in slot_reference),
    'meeting_mismatches':slot_mismatches,
    'unparsed_time_parts':unparsed, 'time_room_type_alignment_errors':alignment_errors,
    'engineering_degree_counts':dict(Counter(r['이수과정'] for r in sections if r['개설대학']=='공과대학')),
    'capacity_parenthesized_pairs':sum(m is not None for m in capacity_pairs),
    'unequal_capacity_pairs':sum(m is not None and m[1]!=m[2] for m in capacity_pairs),
    'bare_zero_capacity_rows':sum(r['정원']=='0' for r in sections),
    'all_enrollment_zero':all(r['수강신청인원']=='0' for r in sections),
    'circled_c_sections':sum('ⓒ' in r['비고'] for r in sections),
    'lab_subgroup_slots':sum(s['possible_lab_subgroup']=='True' for s in slot_reference),
    'interpretation':'Checks extraction parity, not actual class attendance, headcount, commute or shuttle demand.',
}
(OUT/'handoff_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
assert not cell_mismatches and not slot_mismatches and not unparsed and not alignment_errors
assert audit['sha256_matches_handoff_metadata']
print(json.dumps(audit,ensure_ascii=False,indent=2))
