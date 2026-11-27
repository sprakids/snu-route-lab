"""Deidentified stop, route and hour aggregates for the matched November 5 card file."""
import csv
from collections import Counter
import io
import json
from pathlib import Path
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
TARGET='120000173'
NEXT='120000174'


def extract():
    scope=json.loads((ROOT/'seoul_boardings_2026-11-10/stop_scope.json').read_bytes())['stops']
    campus={s['stop_id'] for s in scope if s['zone'] in ('campus_core','campus_annex')}
    counts=Counter()
    with zipfile.ZipFile(ROOT/'tdata_campus_cards_2026-11-10/archives/TAIMS_20261109.zip') as z:
        with z.open('VW_KSCC_DH_CARD.csv') as f:
            labels={r['BSST_ID']:r['BSST_NM'] for r in csv.DictReader(io.TextIOWrapper(f,encoding='utf-8-sig'))}
        with z.open('VW_KSCC_DO_CARD.csv') as f:
            routes={r['ROUTE_ID']:r['ROUTE_NM'] for r in csv.DictReader(io.TextIOWrapper(f,encoding='utf-8-sig'))}
        for table in ('DC','DD','DX'):
            with z.open(f'VW_KSCC_{table}_CARD.csv') as f:
                fields=next(csv.reader([f.readline().decode('utf-8-sig')]))
                for line in f:
                    if b'120000173' not in line and b'120000174' not in line:
                        continue
                    r=dict(zip(fields,next(csv.reader([line.decode('utf8')]))))
                    t=r['RIDE_DTM']
                    if r['RIDE_BSST_ID'] in (TARGET,NEXT) and r['STDR_DE']=='20261105' and t.startswith('20261105'):
                        counts[r['RIDE_BSST_ID'],r['ROUTE_ID'],int(t[8:10]),r['ALGH_BSST_ID']]+=int(r['PSNG_NUM'])
    rows=[]
    for (board,route,hour,stop),weight in sorted(counts.items()):
        rows.append([route,routes.get(route,''),hour,stop,labels.get(stop,''),'campus' if stop in campus else 'outside' if stop in labels else 'unknown',weight,board])
    assert [sum(r[6] for r in rows if r[7]==TARGET and r[5]=='outside' and r[2]==h) for h in range(15,19)]==[132,200,250,341]
    with (HERE/'11월5일_두정류장_하차지.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['route_id','route','hour','alight_id','alight_name','zone','measured','board_id']);w.writerows(rows)


if __name__=='__main__':
    extract()
