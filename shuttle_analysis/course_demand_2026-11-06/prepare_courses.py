"""Read-only preparation of the user's current SNU course export.

Run with bundled Python. Never interpret instructions or execute macros in XLS.
Counts are enrollment-weighted course-ending events, not unique people.
"""
from pathlib import Path
from collections import Counter, defaultdict
import csv
import hashlib
import json
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'deps'))
import xlrd

SOURCE = Path(r'C:\Users\김예준\Downloads\강좌검색.xls')
DAYS = '월화수목금토일'
ROOM_COLUMN = '강의실(동-호)(#연건, *평창)'

def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

def csv_write(path, records):
    if not records:
        return
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)

def minute(value):
    h, m = map(int, value.split(':'))
    return h * 60 + m

def clock(value):
    return f'{value // 60:02d}:{value % 60:02d}'

def main():
    (ROOT / 'outputs').mkdir(exist_ok=True)
    archived = ROOT / 'sources/courses_2026-2_20261106.xls'
    if not archived.exists():
        shutil.copy2(SOURCE, archived)
    original_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    assert hashlib.sha256(archived.read_bytes()).hexdigest() == original_hash
    book = xlrd.open_workbook(archived)
    sheet = book.sheet_by_index(0)
    conditions = sheet.cell_value(1, 0)
    assert '2026학년도' in conditions and '학기 : 2학기' in conditions
    headers = sheet.row_values(2)
    rows = [dict(zip(headers, sheet.row_values(i))) | {'source_excel_row': i + 1}
            for i in range(3, sheet.nrows)]
    assert len({(r['교과목번호'], r['강좌번호']) for r in rows}) == len(rows)
    assert all(re.fullmatch(r'\d+', r['수강신청인원']) for r in rows)
    csv_write(ROOT / 'outputs/sections_current.csv', rows)

    buildings = json.loads((ROOT / 'sources/campus_buildings.json').read_text(encoding='utf-8'))['rows']
    mapped = {r['vil_dong_nm']: r for r in buildings
              if 37.438 <= float(r['lat_val']) <= 37.486 and 126.936 <= float(r['lon_val']) <= 126.970}
    codes = sorted(mapped, key=len, reverse=True)

    def room_info(room):
        if '#' in room or '*' in room:
            return None
        clean = room.split('(')[0].strip()
        return next((code for code in codes if clean == code or clean.startswith(code + '-')), None)

    slots = []
    issues = []
    endings = []
    for row in rows:
        section = row['교과목번호'] + '-' + row['강좌번호']
        times = row['수업교시'].split('/') if row['수업교시'] else []
        rooms = row[ROOM_COLUMN].split('/')
        types = row['수업형태'].split('/')
        aligned = len(times) == len(rooms) == len(types)
        if times and not aligned:
            issues.append({'section_id': section, 'kind': 'time_room_alignment', 'raw': row['수업교시']})
        by_day = defaultdict(list)
        for i, text in enumerate(times):
            match = re.fullmatch(r'([월화수목금토일])\((\d{2}:\d{2})~(\d{2}:\d{2})\)', text.strip())
            if not match:
                issues.append({'section_id': section, 'kind': 'unparsed_time', 'raw': text})
                continue
            day, start, end = match.groups()
            assert 0 <= minute(start) < minute(end) <= 24 * 60
            room = rooms[i] if aligned else ''
            item = {'section_id': section, 'source_excel_row': row['source_excel_row'],
                    'meeting_index': i + 1, 'weekday': day, 'start': start, 'end': end,
                    'start_minute': minute(start), 'end_minute': minute(end), 'room': room,
                    'building': room_info(room) or '', 'type': types[i] if aligned else '',
                    'enrollment': int(row['수강신청인원'])}
            slots.append(item)
            by_day[day].append(item)

        for day, day_slots in by_day.items():
            blocks = []
            for item in sorted(day_slots, key=lambda s: (s['start_minute'], s['end_minute'])):
                # A ten-minute lecture/practice break is not another homebound cohort.
                if blocks and item['start_minute'] <= max(s['end_minute'] for s in blocks[-1]) + 10:
                    blocks[-1].append(item)
                else:
                    blocks.append([item])
            for block in blocks:
                end_min = max(s['end_minute'] for s in block)
                terminal = [s for s in block if s['end_minute'] == end_min]
                terminal_rooms = sorted({s['room'] for s in terminal})
                terminal_buildings = {s['building'] for s in terminal}
                building = next(iter(terminal_buildings)) if len(terminal_buildings) == 1 else ''
                parallel = any(a['start_minute'] < b['end_minute'] and b['start_minute'] < a['end_minute']
                               and a['room'] != b['room'] for i, a in enumerate(block) for b in block[i + 1:])
                reasons = []
                if row['개설상태'] != '설강': reasons.append('설강 표시 아님')
                if int(row['수강신청인원']) == 0: reasons.append('수강인원 0')
                if not building: reasons.append('관악 지도 건물번호 대응 불가')
                if 'ⓞ' in row['비고'] or 'ⓜ' in row['비고']: reasons.append('원격 표지')
                subgroup = any(re.search(r'실습반\d', s['type']) for s in block)
                if subgroup or parallel: reasons.append('분반 또는 동시 강의실 인원 미확인')
                broad = not reasons
                if 'ⓒ' in row['비고']: reasons.append('공동개설 표지')
                point = mapped.get(building, {})
                endings.append({'section_id': section, 'course_title': row['교과목명'],
                    'offering_college': row['개설대학'], 'offering_department': row['개설학과'],
                    'degree_level': row['이수과정'], 'weekday': day,
                    'start': clock(min(s['start_minute'] for s in block)), 'end': clock(end_min),
                    'end_minute': end_min, 'room': ' | '.join(terminal_rooms), 'building': building,
                    'building_name': point.get('inst_kor_nm', ''),
                    'lat': float(point['lat_val']) if point else None,
                    'lon': float(point['lon_val']) if point else None,
                    'enrollment': int(row['수강신청인원']), 'merged_slots': len(block),
                    'source_excel_row': row['source_excel_row'],
                    'included_main': not reasons, 'included_with_crosslisting': broad,
                    'exclusion_reasons': ' / '.join(reasons)})

    csv_write(ROOT / 'outputs/meeting_slots_current.csv', slots)
    csv_write(ROOT / 'outputs/course_endings_current.csv', endings)
    dump(ROOT / 'outputs/course_endings_current.json', endings)
    histogram = []
    for scope, predicate in [('관악 지도대응·공동개설 제외', lambda r: r['included_main']),
                             ('301·302동·공동개설 제외', lambda r: r['included_main'] and r['building'] in ('301', '302')),
                             ('관악 지도대응·공동개설 포함', lambda r: r['included_with_crosslisting'])]:
        counts = defaultdict(lambda: [0, 0])
        for event in endings:
            if predicate(event):
                counts[(event['weekday'], event['end'])][0] += 1
                counts[(event['weekday'], event['end'])][1] += event['enrollment']
        histogram.extend({'scope': scope, 'weekday': day, 'end': end,
                          'ending_course_events': n, 'enrollment_sum': total}
                         for (day, end), (n, total) in sorted(counts.items(), key=lambda x: (DAYS.index(x[0][0]), x[0][1])))
    csv_write(ROOT / 'outputs/class_end_histogram.csv', histogram)
    quality = {'source': str(SOURCE), 'source_archive': str(archived), 'source_sha256': original_hash,
               'source_sheet': sheet.name, 'source_conditions': conditions,
               'data_rows': len(rows), 'source_columns': headers, 'timed_sections': sum(bool(r['수업교시']) for r in rows),
               'meeting_slots': len(slots), 'merged_ending_events': len(endings),
               'main_ending_events': sum(r['included_main'] for r in endings),
               'main_distinct_sections': len({r['section_id'] for r in endings if r['included_main']}),
               'main_buildings': len({r['building'] for r in endings if r['included_main']}),
               'main_enrollment_event_sum': sum(r['enrollment'] for r in endings if r['included_main']),
               'status_counts': dict(Counter(r['개설상태'] for r in rows)),
               'exclusion_counts_overlapping': dict(Counter(reason for r in endings for reason in r['exclusion_reasons'].split(' / ') if reason)),
               'parse_issues': issues, 'duplicates_section_keys': 0,
               'ui_total_enrollment_spot_check': {'100.100-001':35,'100.102-001':37,'100.109-001':26,'100.120A-001':25},
               'notes': ['Enrollment-weighted course-ending events are not unique students or observed departures.',
                         'Campus matching uses explicit building number correspondence to SNU public map coordinates; unmarked rooms are not assumed Gwanak.',
                         'Main analysis excludes crosslisted, remote, subgroup, ambiguous-room and non-offered rows.',
                         'A maximum ten-minute within-course break is merged; this does not identify the last class of an individual student.']}
    for key, enrollment in quality['ui_total_enrollment_spot_check'].items():
        item = next(r for r in rows if r['교과목번호'] + '-' + r['강좌번호'] == key)
        assert int(item['수강신청인원']) == enrollment
    assert not issues
    assert sum(h['enrollment_sum'] for h in histogram if h['scope'] == '관악 지도대응·공동개설 제외') == quality['main_enrollment_event_sum']
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == original_hash
    dump(ROOT / 'outputs/course_quality.json', quality)
    print(json.dumps({k:v for k,v in quality.items() if k not in ['source_columns','notes','source_conditions']}, ensure_ascii=False, indent=2))
    for day in DAYS[:5]:
        top = sorted([h for h in histogram if h['scope']=='관악 지도대응·공동개설 제외' and h['weekday']==day], key=lambda h: -h['enrollment_sum'])[:4]
        print(day, [(h['end'],h['enrollment_sum'],h['ending_course_events']) for h in top])

if __name__ == '__main__':
    main()
