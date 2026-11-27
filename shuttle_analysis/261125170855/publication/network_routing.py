"""Export route occurrences, vehicle events and segment clocks from the released V12 runs."""
from collections import defaultdict
from bisect import bisect_left
from hashlib import sha256
import gzip
import json
import math
from pathlib import Path
from statistics import median
from routing_feed import minute_mean

ROOT = Path(__file__).resolve().parents[1]
VIEW = ROOT / 'viewer-data'
OUT = ROOT.parent / 'app/data/network_v12.json.gz'


def read(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def meters(points):
    return sum(math.hypot((b[0]-a[0])*111195,
                          (b[1]-a[1])*111195*math.cos(math.radians((a[0]+b[0])/2)))
               for a,b in zip(points,points[1:]))


def build():
    common = read(VIEW/'common.json.gz')
    assert common['candidate_id'] == 'R261125170855'
    routes, cases, cohorts, queues, hashes = {}, {}, {}, {}, {}
    for rid, info in common['route_info'].items():
        n = info['n']
        stops = [[s['id'],s['seq']] for s in common['city_route_stops'].get(rid,())]
        if not stops:
            stops = [[None,i+1] for i in range(n)]
            for node in common['nodes']:
                if node.get('route') == rid:
                    stops[node['board']][0] = node['stop_id']
            if rid == 'shuttle-41841':
                stops[-1][0] = 'snu-2400'
        offsets = info['offsets']
        speeds = []
        for k,path in enumerate(info['segments'][:len(offsets)-1]):
            length = meters(common['paths'][path])
            if length > 0 and offsets[k+1] > offsets[k]:
                speeds.append(length/(offsets[k+1]-offsets[k]))
        routes[rid] = dict(stops=stops,offsets=[round(x,3) for x in offsets],
                           anchor=info['anchor'],speed_mps=round(median(speeds),4))
    for scenario in ('regular','peak'):
        for day in ('mon','tue','wed','thu','fri'):
            case = f'{scenario}-{day}'
            path = VIEW/(case+'.json.gz')
            data = read(path)
            hashes[case] = sha256(path.read_bytes()).hexdigest()
            assert data['event_columns'] == ['time','node','vehicle','capacity','before','off','boarded',
                'onboard','compatible_left','new_denied','physical_queue_left','route','stop_index']
            windows = {(v,n):op for n,v,op,_,_ in data['door_windows']}
            groups = defaultdict(lambda:defaultdict(list))
            stops_by_vehicle = defaultdict(list)
            nodes = {}
            for t,node,vehicle,capacity,_,_,_,onboard,left,_,_,rid,index in data['events']:
                assert 0 < capacity and -1e-5 <= onboard <= capacity+1e-5 and left >= -1e-5
                groups[rid][index].append([round(t),capacity,round(max(0,onboard),3),
                                          round(max(0,left),3),round(windows.get((vehicle,node),t))])
                stops_by_vehicle[vehicle,node].append((t,rid,index))
                nodes[rid,index] = node
            clocks = {(rid,i):sorted(r[0] for r in rows) for rid,ss in groups.items() for i,rows in ss.items()}
            audit_path = ROOT/'runs/candidate'/case/('audit-'+case+'.json.gz')
            hashes['audit-'+case] = sha256(audit_path.read_bytes()).hexdigest()
            cells = defaultdict(lambda:[0.,0.,0.])
            for passenger in read(audit_path)['wait_audit']:
                if passenger['outcome'] != 'boarded':
                    continue
                boarded = passenger['end']
                calls = stops_by_vehicle[passenger['vehicle'],passenger['node']]
                departure,rid,i = min((call for call in calls if call[0]>=boarded-1e-5),key=lambda call:call[0])
                ready = passenger['ready']
                times = clocks[rid,i]
                slot = bisect_left(times,round(ready))
                if slot == len(times):
                    continue
                w = passenger['weight']
                cell = cells[rid,i,int(ready//300)]
                cell[0] += w
                cell[1] += w*max(0,departure-times[slot])
                cell[2] += w*max(0,departure-boarded)
            cohorts[case] = {f'{rid}:{i}:{bucket}':[round(w,7),round(extra/w,2),round(dwell/w,2)]
                             for (rid,i,bucket),(w,extra,dwell) in cells.items()}
            queues[case] = {}
            for (rid,i),node in nodes.items():
                if not rid.startswith('shuttle'):continue
                curve = data['queue_timeline'][node]
                times = [r[0] for r in curve]
                queues[case][f'{rid}:{i}'] = {m:round(q,3) for m in range(1440)
                                              if (q:=minute_mean(curve,times,m))>.001}
            cases[case] = {rid:{k:sorted(values) for k,values in stops.items()} for rid,stops in groups.items()}
            assert set(groups) == set(routes)
    payload = dict(release='V261125170855',routes=routes,cases=cases,cohorts=cohorts,queues=queues,replay_sha256=hashes)
    raw = json.dumps(payload,separators=(',',':'),allow_nan=False).encode()
    OUT.write_bytes(gzip.compress(raw,compresslevel=7,mtime=0))
    print(OUT.name,OUT.stat().st_size,sha256(OUT.read_bytes()).hexdigest())


if __name__ == '__main__':
    build()
