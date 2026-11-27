"""Compare published V11 with the candidate on identical observations. Read-only production access."""
import copy
import csv
import gzip
import hashlib
import json
import math
import statistics
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
R = HERE.parent
BASE = R.parent
SIM = BASE / 'simulation_viewer_2026-11-07'
V11 = SIM / 'public/data/capacity_v11'
AUDIT = SIM / 'peak_pair_correction_2026-11-10'
sys.path.insert(0, str(BASE/'261124160531/report'))
from compare import Curve, field_records, read, riders, seconds
sys.path.insert(0, str(BASE/'app'))
from queue_release import accepted_compatibilities, compatibility

LAB = 'https://snu-shuttle-simulation.vercel.app'
API = 'https://snu-route-lab.vercel.app/api/queue-model'
DAYS = ('mon','tue','wed','thu','fri')
SERVICES = ('regular','peak')


def get(url):
    req = Request(url, headers={'User-Agent':'SNU-Route-Lab/0.4','Accept-Encoding':'identity'})
    with urlopen(req,timeout=35) as response:
        return response.read()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify_map(key):
    raw = get(f'{LAB}/data/capacity_v11/{key}.json')
    local = sha((V11/f'{key}.json').read_bytes())
    if raw[:1] == b'{':
        remote = sha(raw)
    elif raw[:2] == b'\x1f\x8b':
        remote = sha(gzip.decompress(raw))
    else:
        js = "const b=require('node:zlib').brotliDecompressSync(require('node:fs').readFileSync(0));process.stdout.write(require('node:crypto').createHash('sha256').update(b).digest('hex'));"
        remote = subprocess.run(['node','-e',js],input=raw,stdout=subprocess.PIPE,check=True).stdout.decode()
    assert remote == local, (key,remote,local)
    assert sha(gzip.decompress((V11/f'{key}.json.gz').read_bytes())) == local
    return key, remote


def production():
    manifest = json.loads(get(LAB+'/routing-model/latest.json'))
    api = json.loads(get(API))
    payload = get(LAB+manifest['payload_path'])
    assert manifest['model_id']==api['model_id']==api['sync']['active_model_id']=='261110162302'
    assert manifest['sha256']==sha(payload)==api['sync']['payload_sha256']
    assert api['sync']['status']=='active' and manifest['source_simulation']=='capacity_v11'
    published = json.loads(payload)
    assert published['routes']['shuttle-41843']['capacity']==60
    changed = copy.deepcopy(published)
    changed['routes']['shuttle-41843']['capacity']=44
    seed = read(BASE/'app/data/auto_queue_inputs.json')
    allowed = accepted_compatibilities(seed)
    assert compatibility(published)==manifest['compatibility_sha256'] and compatibility(published) in allowed
    assert compatibility(changed) not in allowed
    keys=['common',*(f'{s}-{d}' for s in SERVICES for d in DAYS)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        verified = dict(pool.map(verify_map,keys))
    return dict(checked_utc=datetime.now(timezone.utc).isoformat(),manifest=manifest,api_model=api['model_id'],
                api_algorithm=api['boarding_algorithm'],api_sync=api['sync']['status'],map_sha256=verified,
                original_compatibility=compatibility(published),daehak_44_only_compatibility=compatibility(changed),
                accepts_daehak_44_only=False)


def write_rows(path, rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def main():
    verified=production()
    refs=field_records()
    totals=[]; snapshots=[]; boarding=[]; departures=[]
    old_nodes=read(V11/'common.json.gz')['hot_nodes']
    new_nodes=read(R/'viewer-data/common.json.gz')['hot_nodes']
    assert old_nodes==new_nodes
    for service in SERVICES:
        for day in DAYS:
            key=f'{service}-{day}'
            old=read(V11/f'{key}.json.gz')
            folder=R/'runs/candidate'/key
            new=read(folder/f'{key}.json.gz')
            comparison=read(folder/'summary.json')
            checks=read(AUDIT/f'analysis-{key}.json')
            assert math.isclose(old['report']['input_weight'],new['report']['input_weight'],abs_tol=1e-6)
            for name, replay, maximum, over in (
                    ('V11',old,checks['maximum_continuous_wait_min'],checks['over_20_minute_weight']),
                    ('R',new,comparison['max_continuous_wait'],comparison['over20_weight'])):
                rep=replay['report']
                totals.append(dict(model=name,day=day,service=service,weight=rep['input_weight'],
                                   max_wait_min=maximum,over20_weight=over,unserved=rep['unserved_trip_weight'],
                                   capacity_violations=rep['capacity_violations'],travel_min=rep['mean_finished_trip_minutes'],
                                   switch_trip_weight=rep['switched_trip_weight'],switches_per_trip=rep['realized_mean_route_changes'],
                                   outside_riders_included=rep['external_background_passengers_included']))
                for oid,wd,stop,clock,kind,span in refs['records']:
                    if wd!=day or kind!='outside':continue
                    t=seconds(clock)
                    values=Curve(replay['queue_timeline'][old_nodes[stop]]).stats(t,t+60,span)
                    if name=='R':
                        assert abs(values['mean']-comparison['observations'][oid]['mean'])<1e-7
                    snapshots.append(dict(model=name,service=service,obs=oid,day=day,stop=stop,time=clock,
                                          observed_min=span[0],observed_max=span[1],**values))
                if day=='mon':
                    t=seconds('16:59')
                    node=old_nodes['admin_daehak']
                    event=min((e for e in replay['events'] if e[1]==node),key=lambda e:abs(e[0]-t))
                    departures.append(dict(model=name,service=service,expected_second=event[0],load=event[7],
                                           capacity=event[3],outside_after=Curve(replay['queue_timeline'][node]).at(event[0])))
                if day in ('mon','tue','wed'):
                    clock={'mon':'12:20','tue':'15:23','wed':'16:00'}[day]
                    if name=='R':
                        cohort=comparison['episodes'][clock]
                    else:
                        cohort=riders(read(AUDIT/f'audit-{key}.json.gz'),replay['events'],old_nodes['admin_snu'],seconds(clock))
                    wait=cohort['outside_s']
                    boarding.append(dict(model=name,day=day,service=service,time=clock,served_joiners=cohort['boarded_mass'],
                                         same_minute_weight=cohort['same_minute_boards_mass'],
                                         min_seconds=wait['minimum'] if wait else None,
                                         median_seconds=wait['median'] if wait else None,
                                         max_seconds=wait['maximum'] if wait else None))
    scores={}
    for s in SERVICES:
        scores[s]={}
        for model in ('V11','R'):
            sampled=[r for r in snapshots if r['model']==model and r['service']==s]
            assert len(sampled)==7
            scores[s][model]=statistics.mean(r['expected_abs_error'] for r in sampled)
    write_rows(HERE/'관측별_1분_비교.csv',snapshots)
    write_rows(HERE/'평일별_비교.csv',totals)
    (HERE/'비교결과.json').write_text(json.dumps(dict(production=verified,scores=scores,departures=departures,
        boarding=boarding,observations=snapshots,weekdays=totals),ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(scores=scores,boarding=boarding,departures=departures),ensure_ascii=False))


if __name__=='__main__':
    main()
