"""Summarize verified integrated ledgers for the map and the route-planning team."""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import time

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
MODEL=HERE.parent
SIM=MODEL.parent/'simulation_viewer_2026-11-07'
sys.path.insert(0,str(SIM))
from aggregate_half_hour import aggregate

DAYS={'mon':'월','tue':'화','wed':'수','thu':'목','fri':'금'}
SCENARIOS=('regular','peak')
STATION='gwanaksan_4411'
VERSION='R261124102753'


def read(path):
    with (gzip.open if path.suffix=='.gz' else open)(path,'rt',encoding='utf-8') as f:
        return json.load(f)


def publish(path,obj):
    raw=json.dumps(obj,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
    staging=path.with_suffix('.tmp')
    staging.write_bytes(gzip.compress(raw,compresslevel=5,mtime=0))
    staging.replace(path)


def case(audit_file,replay_file,original_dest,patch,common,day,service):
    verified=read(audit_file.parent/'result.json')
    assert verified['model']==VERSION and verified['status']=='verified' and verified['rail_included']
    audit=read(audit_file)
    data=read(replay_file)
    dest=dict(original_dest)
    for row in patch['replacements']:
        plan=row['plan']
        dest[plan[0]]=plan[2]
    assert patch['model']==common['candidate_id']==VERSION
    assert data['report']['weekday']==audit['report']['weekday']==patch['weekday']==DAYS[day]
    assert data['report']['scenario']==audit['report']['scenario']==service
    assert all(dest[t[7]]==t[2] for t in data['trips'])
    vehicle={v[0]:v[1] for v in data['vehicles']}
    totals=Counter()
    station=defaultdict(lambda:defaultdict(Counter))
    station_unserved=0.
    for r in audit['legs']:
        key=dest[r['id']]
        w=r['weight']
        totals[key]+=w
        if key!=STATION:
            continue
        if r['unserved']:
            station_unserved+=w
            continue
        legs=r['legs']
        assert common['paths'][legs[-1][3]][-1]==common['destinations'][STATION]
        rides=[vehicle[l[6]] for l in legs if l[0]==3]
        mode='walk' if not rides else ('shuttle' if rides[-1].startswith('shuttle') else 'city')
        h=str(int(legs[-1][2]//3600))
        stats=station[h][mode]
        stats['arrivals']+=w
        stats['access_person_minutes']+=w*(legs[-1][2]-r['start'])/60
        stats['wait_person_minutes']+=w*sum(l[2]-l[1] for l in legs if l[0]==1)/60
    total=sum(totals.values())
    assert abs(total-data['report']['input_weight'])<1e-6
    assert abs(totals[STATION]-patch['station_demand'])<1e-6
    assert abs(sum(g['arrivals'] for h in station.values() for g in h.values())+station_unserved-totals[STATION])<1e-6
    assert set(station)==set(verified['station_arrivals'])
    for h,groups in station.items():
        assert math.isclose(sum(g['arrivals'] for g in groups.values()),verified['station_arrivals'][h],abs_tol=1e-6)
    for key,n in totals.items():
        members=('dorm_ug','dorm_grad') if key=='dorm' else (key,)
        assert abs(n-sum(verified['initial'][k]['total'] for k in members))<1e-6
    halves=aggregate(audit['waits'],len(common['nodes']))
    # The public hourly boarded weights and the exact arrival-cohort half hours have the same denominator.
    for node,bins in halves.items():
        for h,row in data['hourly'][node].items():
            served=sum(v['served_weight'] for t,v in bins.items() if int(t)//3600==int(h))
            assert abs(row['served_weight']-served)<1e-6
    counts=dict(model=VERSION,weekday=DAYS[day],scenario=service,total=total,destinations=totals)
    access=dict(demand=totals[STATION],unserved=station_unserved,by_marker_arrival_hour=station)
    return halves,counts,access


def build(wait):
    src=read(SIM/'peak_pair_correction_2026-11-10/prepared.json.gz')
    dest={day:{p[0]:p[2] for p in plans} for day,plans in src['prepared']['plans'].items()}
    del src
    common=read(MODEL/'viewer-data/common.json.gz')
    halves={s:{} for s in SCENARIOS}
    runs={s:{} for s in SCENARIOS}
    access={s:{} for s in SCENARIOS}
    hashes={}
    pending=[(d,s) for d in DAYS for s in SCENARIOS]
    while pending:
        completed=[]
        for day,service in pending:
            key=f'{service}-{day}'
            replay=MODEL/'viewer-data'/f'{key}.json.gz'
            results=sorted((MODEL/'runs'/key).glob('attempt-*/result.json'))
            if not results or not replay.exists():
                continue
            patch=read(MODEL/'inputs'/f'{day}.json.gz')
            audit=results[-1].parent/f'audit-{key}.json.gz'
            assert hashlib.sha256(replay.read_bytes()).digest()==hashlib.sha256(
                (audit.parent/replay.name).read_bytes()).digest()
            halves[service][day],runs[service][day],access[service][day]=case(
                audit,replay,dest[DAYS[day]],patch,common,day,service)
            hashes[key]=hashlib.sha256(audit.read_bytes()).hexdigest()
            completed.append((day,service))
            print('verified',key,round(runs[service][day]['destinations'][STATION],2),flush=True)
        pending=[item for item in pending if item not in completed]
        if pending and not wait:
            raise ValueError(f'Missing verified weekday/scenario runs: {pending}')
        if pending and not completed:
            time.sleep(4)
    publish(HERE/'map-stats.json.gz',dict(interval_seconds=1800,scenarios=halves,runs=runs))
    publish(HERE/'station-access.json.gz',dict(model=VERSION,destination=STATION,station_code='4411',
        station_marker=common['destinations'][STATION],time_zone='Asia/Seoul',
        event='building departure to station map marker; indoor and train time excluded',
        unit='weighted simulated trips; person-minutes divided by arrivals give mean minutes',
        data_kind='experimental scenario',runs=access,audit_sha256=hashes))


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--wait',action='store_true',help='process cases as their verified ledgers become available')
    build(cli.parse_args().wait)
