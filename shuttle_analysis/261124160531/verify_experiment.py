"""Check all frozen A/B outputs and distinguish platform exposure from time until dispatch."""
import math
from collections import Counter
from timing_inputs import HERE, REFERENCE, MODEL, ref
from mechanism_check import summarize


def main():
    cases=[]
    for day,did in ref.DAYS.items():
        hashes=set()
        for service in ('peak','regular'):
            key=f'{service}-{did}'
            source=HERE/'runs'/key/'attempt-01'
            r=ref.load(source/'result.json')
            old=ref.load(REFERENCE/'runs'/key/'attempt-01/result.json')
            assert r['model']==MODEL and r['status']=='verified' and r['initial']==old['initial']
            hashes.add(r['timing']['demand_sha256'])
            a=ref.load(source/f'audit-{key}.json.gz')
            date=ref.load(HERE/'viewer-data'/f'{key}.json.gz')
            old_trips=ref.load(REFERENCE/'runs'/key/'attempt-01'/f'audit-{key}.json.gz')['legs']
            def ids(rows):
                mass=Counter()
                for t in rows: mass[t['id']]+=t['weight']
                return mass
            nu,prev=ids(a['legs']),ids(old_trips)
            assert set(nu)==set(prev) and max(abs(nu[i]-prev[i]) for i in nu)<1e-6
            doors={vid:(node,opened,dep,cap) for node,vid,opened,dep,cap in date['door_windows']}
            count=Counter()
            cutoff=0.
            for r0 in a['wait_audit']:
                if r0['outcome']!='boarded':continue
                v=doors.get(r0['vehicle'])
                if not v or r0['node']!=v[0] or r0['end']>=v[2]:continue
                assert v[1]<=r0['end']<v[2]
                t=v[2]-r0['physical_stop_entry']
                if t>1200+1e-6:count['over20_boarded_weight']+=r0['weight']
                cutoff=max(cutoff,t/60)
                count['early_boardings']+=r0['weight']
                count['parked_person_minutes']+=r0['weight']*(v[2]-r0['end'])/60
            assert math.isclose(count['early_boardings'],sum(e[3] for e in date['preboard_events']),abs_tol=1e-5)
            assert math.isclose(count['parked_person_minutes'],sum((dep-t)*w/60 for t,n,v,w,total,dep in date['preboard_events']),abs_tol=1e-5)
            cases.append(dict(day=day,service=service,demand=r['weekday_demand'],verified_original_cohorts=len(nu),
                timing=r['timing'],unserved=r['unserved'],over20_outside_weight=r['over20_weight'],
                capacity_violations=r['capacity_violations'],max_outside=r['max_continuous_wait'],
                early_boarded_over20_until_depart_weight=count['over20_boarded_weight'],
                max_until_depart_for_early_boarded=cutoff,early_boarded=count['early_boardings'],
                rail_arrivals=r['station_arrivals']))
        assert len(hashes)==1
    factors={k:ref.load(HERE/'single_factor'/k/'summary.json')['metrics'] for k in ['timing_only','boarding_only']}
    for label,root in [('baseline',REFERENCE),('combined',HERE)]:
        factors[label]=summarize(ref.load(root/'viewer-data/peak-tue.json.gz'))
    ref.previous.SAVE(HERE/'experiment_check.json',dict(cases=cases,tuesday_peak_factor_comparison=factors))


if __name__=='__main__':
    main()
