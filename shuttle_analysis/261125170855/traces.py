"""Extract terminal presence changes without exporting vehicle identifiers."""
import gzip
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

HERE=Path(__file__).resolve().parent
TRAIN=['2026-11-'+str(i) for i in range(17,21)]
ROUTES={'41843':(3,6),'41841':(4,10)}

def get(day,creds):
    origin=creds['url']
    assert (urlsplit(origin).scheme,urlsplit(origin).hostname)==('https','snu-route-collector.touchline-atlas-june.workers.dev')
    req=Request(origin+'/shuttle/export?day='+day,headers={'Authorization':'Bearer '+creds['token'],'User-Agent':'SNU-Route-Lab/0.4'})
    try:
        with urlopen(req,timeout=40) as r: raw=r.read()
    except HTTPError as e:
        if e.code!=404: raise
        return {'status':404}
    midnight=datetime.fromisoformat(day).replace(tzinfo=timezone(timedelta(hours=9))).timestamp()
    polls=defaultdict(dict)
    for line in gzip.decompress(raw).splitlines():
        for item in json.loads(line)['routes']:
            rid=item['route']; value=item.get('value') or {}
            if rid not in ROUTES or 'captured_at' not in value: continue
            t=round(value['captured_at']-midnight,3)
            if not 0<=t<86400: continue
            positions={}
            for vehicle in value.get('vehicles',[]):
                p=vehicle.get('position') or {}
                if p.get('segment_index') is not None:
                    positions[vehicle['id']]=(p['segment_index'],p.get('at_stop_index') if p.get('at_stop') else None)
            polls[rid][t]=positions
    result={}
    for rid,samples in polls.items():
        terminal,size=ROUTES[rid]
        events=[]; complete=[]; inside={}
        for (lo,prev),(hi,cur) in zip(sorted(samples.items()),sorted(samples.items())[1:]):
            if hi-lo>180:
                inside.clear()
                continue
            for lost in inside.keys()-cur.keys():
                del inside[lost]
            for v in prev.keys()&cur.keys():
                before,after=prev[v],cur[v]
                if before[1]==terminal and after[1]!=terminal:
                    # Include downstream skips as tagged lower-certainty evidence.
                    steps=(after[0]-terminal)%size
                    if steps<=size//2:
                        events.append(dict(interval=[lo,hi],type='exit',steps=steps))
                        if v in inside and inside[v][1]<lo:
                            complete.append(dict(arrival=inside[v],departure=[lo,hi],exit_steps=steps))
                    inside.pop(v,None)
                elif after[1]==terminal and before[1]!=terminal:
                    steps=(terminal-before[0])%size
                    if 1<=steps<=size//2:
                        events.append(dict(interval=[lo,hi],type='enter',steps=steps))
                        inside[v]=[lo,hi]
        result[rid]=dict(polls=len(samples),events=events,linked_visits=complete)
    return dict(status=200,sha256=hashlib.sha256(raw).hexdigest(),routes=result)

if __name__=='__main__':
    sys.path.insert(0,str(HERE.parent/'collector'))
    from export_history import credentials
    creds=credentials()
    result={d:get(d,creds) for d in ['2026-11-09','2026-11-10',*TRAIN,'2026-11-23','2026-11-24','2026-11-25']}
    (HERE/'terminal_transitions.json').write_text(json.dumps(result,separators=(',',':')),encoding='utf8')
    for day,record in result.items():
        branch=record.get('routes',{}).get('41843',{})
        print(day,record['status'], [(round(sum(e['interval'])/120,1),e['steps']) for e in branch.get('events',[]) if e['type']=='exit' and 14.8*7200<=sum(e['interval'])<16.1*7200])
