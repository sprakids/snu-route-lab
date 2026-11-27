"""Compare the November 5 OD counts to V12 by boarding stop and five-minute bin."""
from bisect import bisect_left
from collections import Counter
import csv
import gzip
import io
import json
from pathlib import Path
import zipfile

HERE=Path(__file__).resolve().parent
MODEL=HERE.parent
ROOT=MODEL.parent


def read(path):
    if path.suffix=='.gz':
        with gzip.open(path,'rt',encoding='utf8') as f:return json.load(f)
    return json.loads(path.read_bytes())


def cards(core,bounds):
    counts=Counter()
    stop_bytes={x.encode() for x in core}
    with zipfile.ZipFile(ROOT/'tdata_campus_cards_2026-11-10/archives/TAIMS_20261109.zip') as z:
        with z.open('VW_KSCC_DH_CARD.csv') as f:
            known={r['BSST_ID'] for r in csv.DictReader(io.TextIOWrapper(f,encoding='utf-8-sig'))}
        off_campus=known-bounds
        for table in ('DC','DD','DX'):
            with z.open(f'VW_KSCC_{table}_CARD.csv') as f:
                header=next(csv.reader([f.readline().decode('utf-8-sig')]))
                idx=header.index('RIDE_BSST_ID')
                for line in f:
                    if line.split(b',',idx+1)[idx].strip(b'"') not in stop_bytes:continue
                    r=dict(zip(header,next(csv.reader([line.decode('utf8')]))))
                    t=r['RIDE_DTM']; src=r['RIDE_BSST_ID']; dst=r['ALGH_BSST_ID']
                    if r['STDR_DE']=='20261105' and t.startswith('20261105') and src in core and dst in off_campus:
                        counts[src,(int(t[8:10])*60+int(t[10:12]))//5]+=int(r['PSNG_NUM'])
    return counts


def simulated(service,common,core,bounds):
    key=service+'-thu'
    audit=read(MODEL/f'runs/candidate/{key}/audit-{key}.json.gz')
    seq=common['city_route_stops']; nodes=common['nodes']; events={}; boards=Counter()
    for t,n,v,cap,before,off,on,after,left,new,physical,rid,i in audit['events']:
        if rid in seq and nodes[n]['stop_id'] in core:
            assert seq[rid][i]['id']==nodes[n]['stop_id']
            events[v,n,t]=(rid,i,on)
    counts=Counter()
    for trip in audit['legs']:
        for mode,t,end,path,n,_,v,*_ in trip['legs']:
            if mode!=3 or not nodes[n].get('city') or nodes[n]['stop_id'] not in core:continue
            rid,i,_=events[v,n,t]; offsets=common['route_info'][rid]['offsets']
            j=bisect_left(offsets,offsets[i]+end-t-1e-5)
            assert j>i and abs((offsets[j]-offsets[i])-(end-t))<1e-5
            boards[v,n,t]+=trip['weight']
            if seq[rid][j]['id'] not in bounds:
                counts[nodes[n]['stop_id'],int(t//300)]+=trip['weight']
    assert all(abs(boards[k]-v[2])<1e-5 for k,v in events.items())
    return counts, {nodes[n]['stop_id'] for v,n,t in events}


def main():
    scope=read(ROOT/'seoul_boardings_2026-11-10/stop_scope.json')['stops']
    core={s['stop_id'] for s in scope if s['zone']=='campus_core'}
    bounds={s['stop_id'] for s in scope if s['zone'] in ('campus_core','campus_annex')}
    names={s['stop_id']:s.get('stop_name') or s.get('name') for s in scope}
    known=read(MODEL/'card_phase.json')
    ref=known['stops']
    actual=cards(core,bounds)
    assert [sum(actual[s,i] for s in ref) for i in range(288)]==known['measured']
    common=read(MODEL/'viewer-data/common.json.gz')
    regular,served=simulated('regular',common,core,bounds)
    peak,other=simulated('peak',common,core,bounds)
    assert served==other
    with (HERE/'교내정류장별_5분_승차대조.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f);w.writerow(['승차정류장ID','승차정류장명','시작시각','교외하차_카드승객수','V12기준_통행','V12피크_통행','V12_승차지지원','기존18곳'])
        for s in sorted(core):
            for i in range(288):
                key=s,i
                w.writerow([s,names[s],f'{i//12:02d}:{i%12*5:02d}',actual[key],round(regular[key],4) if s in served else '',
                            round(peak[key],4) if s in served else '',int(s in served),int(s in ref)])
    with (ROOT/'seoul_boardings_2026-11-10/outputs/campus_hourly_monthly_202610_long.csv').open(encoding='utf-8-sig') as f:
        monthly=Counter()
        for row in csv.DictReader(f):
            if row['stop_id'] in ref:monthly[int(row['hour_kst'])]+=int(row['monthly_boardings'])
    with (HERE/'18개정류장_시간대별_승차대조.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f);w.writerow(['시작시','11월5일_실측','V12기준','V12피크','10월전체_모든하차지승차'])
        for h in range(24):
            totals=[sum(data[s,i] for s in ref for i in range(12*h,12*h+12)) for data in (actual,regular,peak)]
            w.writerow([h,totals[0],round(totals[1],3),round(totals[2],3),monthly[h]])
    print('core',len(core),'supported',len(served),'original comparison',len(ref))

if __name__=='__main__':main()
