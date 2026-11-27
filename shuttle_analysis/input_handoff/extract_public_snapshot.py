"""Read-only extraction of the officially published SNU 2026-2 XLS snapshot.
The source workbook is never modified. No current enrollment is inferred.
"""
from pathlib import Path
import csv, json, re, hashlib
from collections import Counter
import xlrd

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'raw/2026_2_courses_published_2026_07_03_revised.xls'
BOOK = xlrd.open_workbook(SOURCE)
SHEET = BOOK.sheet_by_index(0)
HEADERS = SHEET.row_values(2)
rows = [dict(zip(HEADERS, SHEET.row_values(i))) | {'source_excel_row': i + 1} for i in range(3, SHEET.nrows)]

def write_csv(path, records, fields):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)

write_csv(ROOT / 'sections_raw.csv', rows, HEADERS + ['source_excel_row'])
events, unparsed, unmatched = [], [], []
for row in rows:
    times = row['수업교시'].split('/') if row['수업교시'] else []
    rooms = row['강의실(동-호)(#연건, *평창)'].split('/')
    types = row['수업형태'].split('/')
    if times and (len(times) != len(rooms) or len(times) != len(types)):
        unmatched.append({'section_id': row['교과목번호'] + '-' + row['강좌번호'], 'times':len(times), 'rooms':len(rooms), 'types':len(types)})
    for i, part in enumerate(times):
        match = re.fullmatch(r'([월화수목금토일])\((\d{2}:\d{2})~(\d{2}:\d{2})\)',part.strip())
        if not match:
            unparsed.append({'source_excel_row':row['source_excel_row'],'raw_time':part})
            continue
        day, start, end = match.groups()
        # Never replicate one classroom/type into several meeting slots implicitly.
        room = rooms[i] if len(rooms) == len(times) else ''
        typ = types[i] if len(types) == len(times) else ''
        campus = '연건: source # marker' if '#' in room else '평창: source * marker' if '*' in room else '미확정'
        events.append({
            'section_id':row['교과목번호']+'-'+row['강좌번호'],
            'source_excel_row':row['source_excel_row'],
            'meeting_index':i+1,'weekday':day,'start':start,'end':end,
            'meeting_room_raw':room,'meeting_type_raw':typ,
            'campus_source_marker':campus,
            'capacity_raw':row['정원'],
            'offering_college':row['개설대학'],'offering_department':row['개설학과'],
            'course_category':row['교과구분'],'degree_level':row['이수과정'],
            'course_title':row['교과목명'],
            'notes_raw':row['비고'],
            'has_circled_c_marker':'ⓒ' in row['비고'],
            'possible_lab_subgroup':bool(re.search(r'실습반\d',typ)),
        })
write_csv(ROOT/'meeting_slots_raw.csv', events, list(events[0]))
duplicates = Counter((r['교과목번호'],r['강좌번호']) for r in rows)
metadata = {
    'retrieved_at_utc':'2026-10-21T14:36:06Z',
    'published_snapshot_basis_kst':'2026-07-03T10:00:00+09:00',
    'source_workbook_title':SHEET.cell_value(0,0),
    'source_workbook_warning':SHEET.cell_value(1,0),
    'source_notice_url':'https://gsep.snu.ac.kr/boards/notice/41324/detail/news/notice/?page=1&paginate_by=10',
    'source_download_url':'https://gsep.snu.ac.kr/!/download/?path=/media/43/board/2026/07/13/3._2026%ED%95%99%EB%85%84%EB%8F%84_2%ED%95%99%EA%B8%B0_%EA%B0%9C%EC%84%A4%EA%B0%95%EC%A2%8C%EB%AA%A9%EB%A1%9D_%EC%88%98%EC%A0%95.xls&filename=3.%202026%ED%95%99%EB%85%84%EB%8F%84%202%ED%95%99%EA%B8%B0%20%EA%B0%9C%EC%84%A4%EA%B0%95%EC%A2%8C%EB%AA%A9%EB%A1%9D%20(%EC%88%98%EC%A0%95).xls&ct=76&oi=23450',
    'alternative_notice_same_published_basis':'https://www.math.snu.ac.kr/bbs/board.php?bo_table=Math_Notice&wr_id=1001',
    'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    'revision_note':'Source notice still states July 3 10:00 basis; attachment name says revised; embedded last-saved metadata is July 13 2026 05:39:48 UTC. Do not represent this as a fresh October export.',
    'filters':'None. Entire published workbook retained, no exclusions in sections_raw.csv. All officially supplied meeting slots retained in meeting_slots_raw.csv when standard time expression parses.',
    'source_sheet':'Sheet1', 'source_header_excel_row':3,
    'row_count':len(rows), 'unique_section_ids':len(duplicates),
    'duplicate_section_keys':sum(n-1 for n in duplicates.values() if n>1),
    'degree_level_counts':dict(Counter(r['이수과정'] for r in rows)),
    'course_category_counts':dict(Counter(r['교과구분'] for r in rows)),
    'offering_college_counts':dict(Counter(r['개설대학'] for r in rows)),
    'engineering_offered_sections':sum(r['개설대학']=='공과대학' for r in rows),
    'engineering_degree_counts':dict(Counter(r['이수과정'] for r in rows if r['개설대학']=='공과대학')),
    'source_enrollment_counts':dict(Counter(r['수강신청인원'] for r in rows)),
    'all_source_enrollment_zero':all(r['수강신청인원']=='0' for r in rows),
    'sections_with_time':sum(bool(r['수업교시']) for r in rows),
    'meeting_slot_count':len(events),
    'sections_with_parsed_time':len({e['section_id'] for e in events}),
    'unique_section_weekday_end_events':len({(e['section_id'],e['weekday'],e['end']) for e in events}),
    'unparsed_time_parts':unparsed,
    'time_room_type_alignment_issues':unmatched,
    'raw_circled_c_marker_count':sum('ⓒ' in r['비고'] for r in rows),
    'meeting_lab_subgroup_count':sum(e['possible_lab_subgroup'] for e in events),
    'limitations':[
        'July pre-registration snapshot, not the latest courses, capacities, cancellations, or enrolled headcounts.',
        'All 수강신청인원 values are 0. These must not be used as current enrollment or interpreted as empty October classes.',
        '정원 is retained verbatim, commonly N (N). Outer and parenthesized numbers must not be added. Parenthesis definition is not supplied in this workbook.',
        '수업형태 means lecture/practice activity, not verified in-person versus remote modality. No complete explicit delivery-mode field is available.',
        'Rooms use # for Yeongeon and * for Pyeongchang. Unmarked rooms are NOT automatically classified as Gwanak, and blank/unknown rooms remain unclassified.',
        'Crosslisted/shared classrooms and circled-c markers require checking before people/capacity totals. Neither independence nor capacity sharing is established by this extraction.',
        'Lab subgroup slots may represent alternative subgroups, not the full section capacity at every slot.',
        'Meeting slots are not actual passenger flows or last class of the day. Back-to-back lecture/practice and internal breaks require event logic.',
        'College of Engineering offerings identify an offering unit, not the major of each enrolled student. General-education section capacity cannot be assigned entirely to engineering students.',
    ]
}
(ROOT/'provenance_and_coverage.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in metadata.items() if k.endswith('count') or k.endswith('counts') or k in ['row_count','unique_section_ids','engineering_offered_sections','sections_with_time','sections_with_parsed_time','unique_section_weekday_end_events','unparsed_time_parts','time_room_type_alignment_issues']}, ensure_ascii=False, indent=2))
