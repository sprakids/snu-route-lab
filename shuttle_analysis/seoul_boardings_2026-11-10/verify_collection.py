"""Check preserved sources, joins, dates, and point anomalies without model changes."""
from pathlib import Path
from collections import Counter
import csv
import hashlib
import io
import json

ROOT=Path(__file__).resolve().parent


def read(path,encoding='utf-8-sig'):
    with path.open(encoding=encoding,newline='') as source:return list(csv.DictReader(source))


def key(row):return tuple(row[c] for c in ['사용일자','노선번호','표준버스정류장ID','역명'])


def main():
    profile=json.loads((ROOT/'collection_quality.json').read_text(encoding='utf-8'))
    archive=read(ROOT/'sources/daily_8_routes_202610_archive.csv')
    archive_map={key(row):row for row in archive}
    assert len(archive)==len(archive_map)
    compared=0;differences=[];date_sets={}
    for source in (ROOT/'sources').glob('daily_route_*.csv'):
        rows=read(source,'cp949')
        date_sets[source.stem.removeprefix('daily_route_')]=sorted({r['사용일자'] for r in rows})
        for row in rows:
            if not row['사용일자'].startswith('202610'):continue
            original=archive_map.get(key(row))
            if original is None:
                differences.append({'key':key(row),'issue':'missing_in_monthly_archive'});continue
            compared+=1
            if any(row[c]!=original[c] for c in ['승차총승객수','하차총승객수']):
                differences.append({'key':key(row),'issue':'count_difference'})
    daily=read(ROOT/'outputs/campus_daily_20261013_20261109_available.csv')
    monthly=read(ROOT/'outputs/campus_hourly_monthly_202610.csv')
    monthly_keys=[tuple(r[c] for c in ['사용년월','노선번호','표준버스정류장ID','역명','교통수단타입코드']) for r in monthly]
    assert len(monthly_keys)==len(set(monthly_keys))
    flags=[]
    for label,rows in [('monthly_hourly',monthly),('daily',daily)]:
        for row in rows:
            if row['stop_sequence']=='999':
                flags.append({'dataset':label,'period':row.get('사용일자',row.get('사용년월')),
                    'route_no':row['노선번호'],'stop_id':row['표준버스정류장ID'],
                    'stop_name':row['역명'],'issue':'source_stop_sequence_999',
                    'interpretation':'Preserved source record; regular route-stop membership not confirmed. Do not infer normal service from this record.'})
    required=['표준버스정류장ID','노선번호','역명']
    assert all(row[c] for row in daily for c in required+['사용일자','승차총승객수','하차총승객수'])
    outputs=[{'file':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
             for p in sorted((ROOT/'outputs').glob('*.csv'))]
    quality={'status':'passed_with_documented_source_gaps',
        'monthly_archive_vs_route_exports':{'compared_records':compared,'differences':differences,
                                           'scope':'Same October day/route/stop/sequence; matching source extracts, not independent observations'},
        'october_27_missing_in_both_public_sources':not any(r['사용일자']=='20261027' for r in archive)
            and all('20261027' not in dates for dates in date_sets.values()),
        'monthly_duplicate_composite_keys':len(monthly_keys)-len(set(monthly_keys)),
        'daily_duplicate_composite_keys':len(daily)-len({key(r) for r in daily}),
        'available_days':len(profile['available_dates']),
        'missing_dates':profile['missing_dates'],
        'flags':flags,'source_dates_by_route':date_sets,'outputs':outputs,
        'missing_dates_imputed_as_zero':False,'models_modified':False,'deployments_changed':False}
    assert not differences
    (ROOT/'verification.json').write_text(json.dumps(quality,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in quality.items() if k not in ['outputs','source_dates_by_route']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
