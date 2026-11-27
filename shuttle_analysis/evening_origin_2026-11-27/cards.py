"""Only publish passenger-count aggregates. Previous tags are not building observations."""
import csv
from collections import Counter, defaultdict
import io
import json
from pathlib import Path
import sys
from zipfile import ZipFile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
ARCHIVES=ROOT/'tdata_campus_cards_2026-11-10/archives'
PAIR={'120000173','120000174'}
SECOND={'120000173','120000238'}
NAK={'120900119','120900110'}
SNU='120000150'


def extract(z,predicate):
    for name in ('DC','DD','DX'):
        with z.open(f'VW_KSCC_{name}_CARD.csv') as f:
            fields=next(csv.reader([f.readline().decode('utf-8-sig')]))
            assert fields[0]=='TRCR_ID'
            for line in f:
                if predicate(line):
                    yield dict(zip(fields,next(csv.reader([line.decode('utf8')]))))


def clock(t):
    return int(t[8:10])*3600+int(t[10:12])*60+int(t[12:14])


def band(seconds):
    return '6시간 이상' if seconds>=21600 else '3~6시간' if seconds>=10800 else '90분~3시간' if seconds>=5400 else '30~90분' if seconds>=1800 else '30분 미만'


def main(day):
    with ZipFile(ARCHIVES/('TAIMS_20261109.zip' if day=='20261105' else json.loads((HERE/f'source_{day}.json').read_text())['file'])) as z:
        with z.open('VW_KSCC_DH_CARD.csv') as f:
            known={r['BSST_ID'] for r in csv.DictReader(io.TextIOWrapper(f,encoding='utf-8-sig'))}
        scope=json.loads((ROOT/'seoul_boardings_2026-11-10/stop_scope.json').read_text(encoding='utf-8'))['stops']
        campus={r['stop_id'] for r in scope if r['zone'] in ('campus_core','campus_annex')}
        anchors=[]; histories=defaultdict(list)
        for r in extract(z,lambda b:b'120000173' in b or b'120000174' in b):
            t=r['RIDE_DTM']
            if r['STDR_DE']==day and t.startswith(day) and 18<=int(t[8:10])<=20 and r['RIDE_BSST_ID'] in PAIR and r['ROUTE_ID']:
                anchors.append((r['TRCR_ID'],t,r['RIDE_BSST_ID'],r['ALGH_BSST_ID'],r['ROUTE_ID'],r['TRTR_FCNT'],int(r['PSNG_NUM'])))
        assert anchors,day
        cards={a[0].encode() for a in anchors if a[0]}
        for r in extract(z,lambda b:b.partition(b',')[0].strip(b'"') in cards):
            if r['STDR_DE']==day and r['RIDE_DTM'].startswith(day):
                histories[r['TRCR_ID']].append((r['RIDE_DTM'],r['ALGH_DTM'],r['ALGH_BSST_ID'],r['ROUTE_ID'],int(r['PSNG_NUM'])))
    counts=Counter()
    for card,t,s,b,rid,transfer,n in anchors:
        h=int(t[8:10])
        direction='낙성대' if b in NAK else '서울대입구' if b==SNU else '기타교내' if b in campus else '기타교외' if b in known else '하차미상'
        for scope in ('전체',direction):
            def add(measure,category):
                counts[day,s,h,scope,measure,str(category)]+=n
            add('승차', '계');add('승차15분',int(t[10:12])//15*15);add('노선',rid)
            add('환승여부','첫 유료 승차' if transfer=='0' else '유료 환승' if transfer.isdigit() else '미상')
            loc='불확실';gap=None;last_time=None
            history=histories.get(card,[])
            earlier=[row for row in history if row[0]<t]
            valid=[row for row in earlier if row[1].startswith(day) and len(row[1])==14 and row[0]<=row[1]<=t and row[4]==1]
            single=(n==1 and card and sum(row[0]==t for row in history)==1)
            local=[row for row in valid if row[3] and row[2] in campus] if single else []
            add('당일선행교내하차','확인' if local else '미확인')
            morning=[row for row in local if int(row[1][8:10])<12]
            add('정오전교내하차','확인' if morning else '미확인')
            if single and not earlier:loc='앞선 태그 없음'
            elif single:
                latest=max(row[0] for row in earlier)
                tied=[row for row in earlier if row[0]==latest]
                if len(tied)==1 and tied[0] in valid:
                    _,last_time,a,route,_=tied[0]
                    if route and a in SECOND:loc='제2공학관'
                    elif route and a=='120000174':loc='제1공학관'
                    elif route and a in campus:loc='그 외 교내'
                    elif a and (not route or a in known):loc='그 외 버스·철도'
                    gap=clock(t)-clock(last_time)
            add('직전하차',loc)
            if loc in ('제2공학관','제1공학관','그 외 교내'):
                add('직전교내하차_간격',band(gap))
                add('직전교내하차_시각',int(last_time[8:10]))
                if loc!='그 외 교내':add('직전두공학관하차_간격',band(gap))
    with (HERE/f'카드_{day}.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['date','boarding_stop','hour','direction','measure','category','passengers'])
        w.writerows([*k,v] for k,v in sorted(counts.items()))
    for s in PAIR:
        for h in range(18,21):
            for direction in ('전체','낙성대','서울대입구'):
                sel={k[4:]:v for k,v in counts.items() if k[:4]==(day,s,h,direction)}
                total=sel.get(('승차','계'),0)
                for metric in ('직전하차','승차15분','노선','환승여부','당일선행교내하차','정오전교내하차'):
                    assert sum(v for (m,_),v in sel.items() if m==metric)==total
                assert sum(v for (m,_),v in sel.items() if m=='직전교내하차_간격')==sum(sel.get(('직전하차',a),0) for a in ('제1공학관','제2공학관','그 외 교내'))
    print(day,'verified',sum(n for _,_,_,_,_,_,n in anchors),flush=True)


if __name__=='__main__':main(sys.argv[1])
