"""Keep a physical return, the boarding turn, and the planned departure distinct."""
import cmath
import json
import math
from pathlib import Path
from policy import TEMPLATE, return_template

HERE=Path(__file__).resolve().parent

def town_returns(day, clocks, samples, dated=False):
    date='2026-11-24' if dated else f'2026-11-{TEMPLATE[day]}'
    archive=samples[date]['routes']['41843']
    events=archive['events']
    visits=archive['linked_visits']
    out={}; claims={}
    for slot in clocks:
        if not 11*3600<=slot<19*3600: continue
        band=int(slot//7200)
        phases=[]
        for e in events:
            t=sum(e['interval'])/2
            if int(t//7200)==band and e['type']=='exit':
                phases.append(t)
        # Infer the phase modulo the documented 10-min headway from multiple
        # exits. A few seconds around +5/-5 min must not average to zero.
        if len(phases)<3: continue
        vector=sum(cmath.exp(2j*math.pi*t/600.) for t in phases)/len(phases)
        if abs(vector)<.5: continue
        offset=cmath.phase(vector)*600/(2*math.pi)
        anchor=slot+offset
        located=[v for v in visits if max(abs(t-anchor) for t in v['departure'])<300 and
                 (sum(v['departure'])-sum(v['arrival']))/2<=1800]
        if len(located)==1:
            v=located[0]
            out[slot]=(sum(v['departure'])/2,[(sum(v['departure'])-sum(v['arrival']))/2])
            claims.setdefault(tuple(v['departure']),[]).append(slot)
        # The second bus may be missing from telemetry. Its nominal time
        # remains independent of the phase inferred for the visible vehicle.
    for slots in claims.values():
        if len(slots)>1:
            for s in slots:out.pop(s,None)
    return out

def windows(bundle,day,rid,clocks,size,scenario):
    templates=return_template(day,rid,clocks,size)
    if rid=='shuttle-daehak':
        templates={s:v for s,v in templates.items() if not 11*3600<=s<19*3600}
        templates.update(town_returns(day,clocks,bundle['transitions'],bundle.get('dated')=='nov24'))
    elif rid=='shuttle-41841' and bundle.get('dated')=='nov10':
        # Only the observed pair is dated. Preserve neighbouring regular slots.
        # No reported queue or passenger count enters any schedule.
        field=bundle['pair_observation']
        times=field['derived_time_windows']
        def sec(stamp):
            h,m,s=map(int,stamp.split('T')[1][:8].split(':'))
            return h*3600+m*60+s
        dep=(sec(times['departure_window_start'])+sec(times['departure_window_end_exclusive']))/2
        board=(sec(times['boarding_window_start'])+sec(times['boarding_window_end_exclusive']))/2
        joined=(sec(field['queue_join_window_start'])+sec(field['queue_join_window_end_exclusive']))/2
        # Bounds use event ordering only. Fraction is chosen before scoring.
        opened=joined+(board-joined)*bundle.get('arrival_fraction',.5)
        slot=min(clocks,key=lambda t:abs(t-dep))
        templates[slot]=(dep,[dep-opened]*size(slot))
    return templates

def apply_stays(b,day,donors,timing,max_minutes):
    courses=timing.ref.ref.class_events(timing.ref.load(timing.ref.ref.COURSES))
    rows=b['prepared']['plans'][day]
    changed=0.
    for i,p in enumerate(rows):
        parent=donors.get(p[0],p[0])
        e=courses[(parent-1)//48]
        if e['end_minute']>18*60 or timing.uniform(f'trip/{parent}')>=timing.STAY_RATE: continue
        start=p[4]+60*max_minutes*timing.uniform(f'extended-activity/{parent}')
        assert p[4]<=start<86400
        rows[i]=[*p[:4],start,*p[5:]]
        changed+=p[3]
    return changed
