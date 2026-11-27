"""Find same-vehicle approach and departure brackets near the reported boarding minute."""
from datetime import datetime, timezone, timedelta
import gzip
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
OBS = json.loads((HERE/'boarding_admin_snu_1600.json').read_text(encoding='utf8'))
TZ = timezone(timedelta(hours=9))
DAY = datetime.fromisoformat(OBS['observation_date']).replace(tzinfo=TZ).timestamp()
MARK = 16*3600


def run():
    sys.path.insert(0,str(HERE.parent/'collector'))
    from export_history import credentials
    cfg=credentials()
    url=urlsplit(cfg['url'])
    assert (url.scheme,url.hostname)==('https','snu-route-collector.touchline-atlas-june.workers.dev')
    req=Request(cfg['url']+'/shuttle/export?day='+OBS['observation_date'],
                headers={'Authorization':'Bearer '+cfg['token'],'User-Agent':'SNU-Route-Lab/0.4'})
    with urlopen(req,timeout=20) as response:
        raw=response.read()
    rows=[]
    for line in gzip.decompress(raw).splitlines():
        for item in json.loads(line)['routes']:
            if item['route']!='41841':
                continue
            value=item.get('value') or {}
            if 'captured_at' not in value or 'vehicles' not in value:
                continue
            t=round(value['captured_at']-DAY,3)
            if MARK-3600<=t<=MARK+3600:
                positions={v['id']:(v['position'].get('at_stop_index'),v['position'].get('segment_index'))
                           for v in value['vehicles'] if v.get('position')}
                rows.append((t,positions))
    rows.sort(key=lambda row:row[0])
    marker=4
    matches=[]
    for i in range(1,len(rows)):
        lo,before=rows[i-1]
        hi,now=rows[i]
        if hi<MARK or lo>=MARK+60 or hi-lo>90:
            continue
        for vehicle,pos in now.items():
            prior=before.get(vehicle)
            if not prior or prior[1]!=marker-1 or pos[0]!=marker:
                continue
            trace=[(lo,prior),(hi,pos)]
            departure=None
            for t,locations in rows[i+1:]:
                if t-trace[-1][0]>90 or vehicle not in locations:
                    break
                current=locations[vehicle]
                trace.append((t,current))
                if current[0]!=marker:
                    if current[1] in (marker,marker+1) and t>hi:
                        departure=[trace[-2][0],t]
                    break
            matches.append(dict(arrival=[lo,hi],departure=departure,points=trace))
    out=dict(source='archived operator schematic stop-area observations, received in Asia/Seoul',
             day=OBS['observation_date'],route='41841',route_stop_index=marker,
             source_archive_sha256=hashlib.sha256(raw).hexdigest(),
             bounded_trace_count=len(matches),matches=matches)
    if not matches:
        raise ValueError('No observed directional arrival overlapping the reported minute.')
    (HERE/'arrival_trace.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8')
    print([(r['arrival'],r['departure'],r['points'][-1][0]) for r in matches])


if __name__=='__main__':
    run()
