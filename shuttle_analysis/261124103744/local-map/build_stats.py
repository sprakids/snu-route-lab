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
VERSION='R261124103744'
PREVIOUS=MODEL.parent/'261124102753'
UPPER_BUILDINGS={'300','301','302'}


def read(path):
    with (gzip.open if path.suffix=='.gz' else open)(path,'rt',encoding='utf-8') as f:
        return json.load(f)


def publish(path,obj):
    raw=json.dumps(obj,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
    staging=path.with_suffix('.tmp')
    staging.write_bytes(gzip.compress(raw,compresslevel=5,mtime=0))
    staging.replace(path)


def upper_dorm(legs,upper_ids):
    total=completed=walked=0.
    for row in legs:
        if row['id'] not in upper_ids:
            continue
        w=row['weight']
        total+=w
        if not row['unserved']:
            completed+=w
            if all(leg[0]!=3 for leg in row['legs']):
                walked+=w
    return dict(total=total,completed=completed,without_vehicle=walked)


def case(audit_file,replay_file,original_dest,upper_ids,patch,common,day,service):
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
    previous_result=sorted((PREVIOUS/'runs'/f'{service}-{day}').glob('attempt-*/result.json'))[-1]
    assert read(previous_result)['status']=='verified'
    baseline=upper_dorm(read(previous_result.parent/audit_file.name)['legs'],upper_ids)
    now=upper_dorm(audit['legs'],upper_ids)
    assert math.isclose(baseline['total'],now['total'],abs_tol=1e-6) and now['total']<=totals['dorm']+1e-6
    counts=dict(model=VERSION,weekday=DAYS[day],scenario=service,total=total,destinations=totals,
                upper_dorm=dict(previous=baseline,current=now))
    access=dict(demand=totals[STATION],unserved=station_unserved,by_marker_arrival_hour=station)
    return halves,counts,access


def build(wait):
    src=read(SIM/'peak_pair_correction_2026-11-10/prepared.json.gz')
    dest={day:{p[0]:p[2] for p in plans} for day,plans in src['prepared']['plans'].items()}
    upper_ids={day:{p[0] for p in plans if str(p[1]) in UPPER_BUILDINGS and p[2]=='dorm'}
               for day,plans in src['prepared']['plans'].items()}
    del src
    common=read(MODEL/'viewer-data/common.json.gz')
    previous_common=read(PREVIOUS/'viewer-data/common.json.gz')
    assert previous_common['paths']==common['paths'] and previous_common['destinations']==common['destinations']
    del previous_common
    catalog={(tuple(r['origin']),r['dorm']):r for r in read(MODEL.parent/'261124101820/dorm_paths.json.gz')['routes']}
    for row in read(MODEL/'terrain.json')['rows']:
        saved=catalog.get((tuple(row['origin']),row['dorm']))
        if saved is None:
            assert 'path' not in row
            continue
        assert all(saved[k]==row[k] for k in ('path','meters','seconds'))
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
            previous_patch=read(PREVIOUS/'inputs'/f'{day}.json.gz')
            assert [(r['donor'],r['plan']) for r in patch['replacements']]==[
                (r['donor'],r['plan']) for r in previous_patch['replacements']]
            audit=results[-1].parent/f'audit-{key}.json.gz'
            assert hashlib.sha256(replay.read_bytes()).digest()==hashlib.sha256(
                (audit.parent/replay.name).read_bytes()).digest()
            halves[service][day],runs[service][day],access[service][day]=case(
                audit,replay,dest[DAYS[day]],upper_ids[DAYS[day]],patch,common,day,service)
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


def verify_exports():
    report=read(MODEL/'terrain_results.json')
    stats=read(HERE/'map-stats.json.gz')['runs']
    access=read(HERE/'station-access.json.gz')['runs']
    assert report['model']==VERSION and report['runs']==report['controls']==10
    days={v:k for k,v in DAYS.items()}
    seen=set()
    for row in report['cases']:
        day,service=days[row['요일']],row['배차']
        assert (day,service) not in seen
        seen.add((day,service))
        batch=stats[service][day]
        station=access[service][day]
        groups=[(key,val) for hour in station['by_marker_arrival_hour'].values() for key,val in hour.items()]
        matched={'전체_하교':batch['total'],'관악산역_배정':station['demand'],
                 '관악산역_도달':sum(v['arrivals'] for _,v in groups)}
        for key,column in [('walk','역접근_차량미이용'),('city','역접근_시내버스'),('shuttle','역접근_교내셔틀')]:
            matched[column]=sum(v['arrivals'] for mode,v in groups if mode==key)
        matched['역접근_평균분']=sum(v['access_person_minutes'] for _,v in groups)/matched['관악산역_도달']
        assert all(math.isclose(value,row[key],abs_tol=1e-5) for key,value in matched.items())
        run=read(sorted((MODEL/'runs'/f'{service}-{day}').glob('attempt-*/result.json'))[-1])
        upper=batch['upper_dorm']['current']
        assert math.isclose(upper['without_vehicle'],sum(v.get('end_to_end_walk',0) for v in run['upper_completed'].values()),abs_tol=1e-5)
        assert math.isclose(upper['total'],sum(v['total'] for v in run['upper_completed'].values()),abs_tol=1e-5)
    assert seen=={(day,service) for day in DAYS for service in SCENARIOS}
    print(f'{VERSION}: verified 10 map cases against terrain_results.json and upper_completed.')


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--wait',action='store_true',help='process cases as their verified ledgers become available')
    cli.add_argument('--verify',action='store_true',help='compare existing map files with the final terrain report')
    args=cli.parse_args()
    if not args.verify:
        build(args.wait)
    if args.verify or (MODEL/'terrain_results.json').is_file():
        verify_exports()
