"""Five-minute boarding profiles. No card identifiers are retained."""
import csv
import gzip
import io
import json
import math
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

HERE=Path(__file__).resolve().parent
PRIOR=HERE.parent/'261125164654'
TABLES=('DC','DD','DX')

def read(path):
    with (gzip.open if path.suffix=='.gz' else open)(path,'rt',encoding='utf-8-sig') as f:
        return json.load(f)

def bins():
    scope=read(HERE.parent/'seoul_boardings_2026-11-10/stop_scope.json')
    campus={s['stop_id'] for s in scope['stops'] if s['zone']=='campus_core'}
    bounds={s['stop_id'] for s in scope['stops'] if s['zone'] in ('campus_core','campus_annex')}
    packed={s.encode() for s in campus}
    rows=Counter()
    with zipfile.ZipFile(HERE.parent/'tdata_campus_cards_2026-11-10/archives/TAIMS_20261109.zip') as z:
        with z.open('VW_KSCC_DH_CARD.csv') as f:
            known={r['BSST_ID'] for r in csv.DictReader(io.TextIOWrapper(f,encoding='utf-8-sig'))}
        for table in TABLES:
            with z.open(f'VW_KSCC_{table}_CARD.csv') as f:
                header=next(csv.reader([f.readline().decode('utf-8-sig')]))
                idx=header.index('RIDE_BSST_ID')
                for line in f:
                    cells=line.split(b',')
                    if cells[idx].strip(b'"') not in packed: continue
                    r=dict(zip(header,next(csv.reader([line.decode('utf8')]))))
                    t=r['RIDE_DTM']
                    if r['STDR_DE']!='20261105' or not t.startswith('20261105') or r['RIDE_BSST_ID'] not in campus: continue
                    if r['ALGH_BSST_ID'] not in known or r['ALGH_BSST_ID'] in bounds: continue
                    clock=(int(t[8:10])*60+int(t[10:12]))//5
                    rows[r['RIDE_BSST_ID'],clock]+=int(r['PSNG_NUM'])
    source=PRIOR/'runs/release/regular-thu'
    data=read(source/'regular-thu.json.gz')
    common=read(PRIOR/'viewer-data/common.json.gz')
    nodes=common['nodes']
    audits=read(source/'audit-regular-thu.json.gz')
    # A city vehicle's alight time maps to the stop event for that vehicle.
    events={(e[2],e[0]):e for e in data['events'] if e[11] not in ('shuttle-41841','shuttle-daehak')}
    simulated=Counter()
    paired=[]
    for trip in audits['legs']:
        for mode,start,end,path,node,_,v,*_ in trip['legs']:
            if mode!=3 or not nodes[node].get('city') or nodes[node]['stop_id'] not in campus: continue
            e=events.get((v,end))
            if e is None or nodes[e[1]]['stop_id'] in bounds: continue
            simulated[nodes[node]['stop_id'],int(start//300)]+=trip['weight']
            paired.append((trip['id'],nodes[node]['stop_id'],start,trip['weight']))
    matched=sorted({stop for stop,t in rows}&{stop for stop,t in simulated})
    def totals(counts):
        return [sum(counts[s,t] for s in matched) for t in range(288)]
    sys.path.insert(0,str(HERE.parent/'261124160531'))
    import timing_inputs as timing
    ref=timing.ref
    courses=ref.ref.class_events(ref.load(ref.ref.COURSES))
    donors={r['plan'][0]:r['donor'] for r in ref.load(ref.INPUTS/'thu.json.gz')['replacements']}
    def loss(a,b,hours):
        # Average within-hour differences in the four fifteen-minute shares.
        gaps=[]
        for h in hours:
            x=[sum(a[h*12+i:h*12+i+3]) for i in (0,3,6,9)]
            y=[sum(b[h*12+i:h*12+i+3]) for i in (0,3,6,9)]
            if sum(x) and sum(y):
                gaps.extend(abs(n/sum(x)-m/sum(y)) for n,m in zip(x,y))
        return sum(gaps)/len(gaps)
    measured=totals(rows)
    trials=[]
    for minutes in (0,30,60,90):
        projected=[0.]*288
        for uid,s,t,w in paired:
            if s not in matched: continue
            parent=donors.get(uid,uid)
            c=courses[(parent-1)//48]
            if c['end_minute']<=18*60 and timing.uniform(f'trip/{parent}')<timing.STAY_RATE:
                t+=minutes*60*timing.uniform(f'extended-activity/{parent}')
            projected[min(287,int(t//300))]+=w
        trials.append(dict(minutes=minutes,train=loss(measured,projected,(12,14,16,18)),
                           validation=loss(measured,projected,(13,15,17,19))))
    best=min(trials,key=lambda r:r['train'])
    chosen=best['minutes'] if best['validation']<trials[0]['validation'] else 0
    return dict(date='2026-11-05',scope='matched core stops to off-campus bus stops',stops=matched,
                measured=measured,modeled=totals(simulated),trials=trials,selected_minutes=chosen,
                train_hours=[12,14,16,18],validation_hours=[13,15,17,19])

if __name__=='__main__':
    result=bins()
    (HERE/'card_phase.json').write_text(json.dumps(result,separators=(',',':')),encoding='utf8')
    print(len(result['stops']),sum(result['measured']),sum(result['modeled']))
