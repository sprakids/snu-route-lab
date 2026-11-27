"""Read the supplied probe only; no credential access or network requests."""
from pathlib import Path
import json
import re
import hashlib
from collections import Counter

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'probes/20261107T061004_965606Z/response.txt'
raw=SOURCE.read_bytes()
obj=json.loads(raw.decode('utf-8-sig'))

def find_rows(x):
    if isinstance(x,list):
        if x and all(isinstance(r,dict) for r in x) and 'routeId' in x[0]:
            yield x
        else:
            for y in x:yield from find_rows(y)
    elif isinstance(x,dict):
        for v in x.values():yield from find_rows(v)

sets=list(find_rows(obj))
assert len(sets)==1,len(sets)
rows=sets[0]
fields=sorted(set().union(*(r.keys() for r in rows)))
safe_fields=[f for f in fields if re.search('date|de$|dt$|ymd|route|sta|sn$|stdr',f,re.I)]
safe_fields=[f for f in safe_fields if not re.search('key|token|auth|secret|password',f,re.I)]

def number(x):
    if x is None or x=='':return None
    if isinstance(x,str) and x.strip().lower() in ('null','none'):return None
    return float(x)

families={}
for label,patt in [('sum_load',r'a18SumLoadPsngNum\d\dh'),('mean_load',r'a18Num\d\dh'),
                   ('max_load',r'maxA18Num\d\dh'),('runs',r'a18FcntNum\d\dh')]:
    columns=[f for f in fields if re.fullmatch(patt,f)]
    parsed=[number(r.get(f)) for r in rows for f in columns]
    vals=[v for v in parsed if v is not None]
    families[label]={'columns':columns,'cells':len(parsed),'null_cells':len(parsed)-len(vals),
                    'zero_cells':sum(v==0 for v in vals),'negative_cells':sum(v<0 for v in vals),
                    'positive_cells':sum(v>0 for v in vals),'minimum_nonnull':min(vals) if vals else None,
                    'maximum_nonnull':max(vals) if vals else None}

ids=['routeId','fromStaId','toStaId','staSn']
duplicated_keys=sum(c-1 for c in Counter(tuple(str(r.get(f)) for f in ids) for r in rows).values() if c>1)
targets={'100100250','100100251','100100253','120900011','120900012'}
daily=[]
for r in rows:
    vals=[number(r.get(f'a18SumLoadPsngNum{h:02d}h')) for h in range(24)]
    known=sum(x for x in vals if x is not None)
    total=number(r.get('a18SumLoadPsng'))
    daily.append({'route_id':r['routeId'],'from_stop':r['fromStaId'],'to_stop':r['toStaId'],
        'known_hour_partial_sum':known,'null_hours':sum(x is None for x in vals),'reported_daily_sum':total,
        'daily_minus_known_hours':None if total is None else total-known})
record={'source':str(SOURCE),'source_sha256':hashlib.sha256(raw).hexdigest(),
        'scope':'10-row supplied probe only; not full-date coverage or Seoul campus-route coverage',
        'rows':len(rows),'field_count':len(fields),'fields':fields,
        'safe_identity_sample':[{f:r.get(f) for f in safe_fields} for r in rows[:3]],
        'route_ids':sorted({str(r.get('routeId')) for r in rows}),
        'dates':sorted({str(r.get('stdrDe')) for r in rows}),
        'target_campus_route_rows':sum(str(r.get('routeId')) in targets for r in rows),
        'daily_reconciliation_partial_hours_only':daily,
        'duplicate_route_segment_sequence_keys':duplicated_keys,'families':families,
        'network_requests':0,'credentials_read':False}
(ROOT/'probe_review.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in record.items() if k!='fields'},ensure_ascii=False,indent=2))
