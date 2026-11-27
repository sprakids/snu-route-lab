"""Simulate a terrain-aware weekday and validate it against the common fleet."""
import argparse
from collections import Counter, defaultdict
import os
import shutil

from slope_model import HERE, DATA, INPUTS, MODEL, DAYS, previous, ref, prepare, bundle, load
from run_integrated import audit_case


def run(day, service, rail, retry=False):
    name = f'{service}-{DAYS[day]}'
    case = HERE/('runs' if rail else 'controls')/name
    case.mkdir(parents=True,exist_ok=True)
    existing = sorted(case.glob('attempt-*/result.json'))
    if existing:
        result = load(existing[-1])
        assert result['status']=='verified' and result['model']==MODEL
        return result
    attempts = sorted(case.glob('attempt-*'))
    if attempts and not retry:
        raise ValueError(f'Inspect existing attempt in {case}')
    out = case/f'attempt-{len(attempts)+1:02}'
    out.mkdir()
    b, patch, donors, upper = bundle(day,rail)
    b['prepared']['common']['candidate_id']=MODEL
    ref.engine.WORK = ref.engine.OUT = ref.base.OUT = out
    ref.engine.simulate(b,day,service)
    result = audit_case(b,day,service,out,patch,donors,rail)
    plans = {p[0]:p[1] for p in b['prepared']['plans'][day]}
    ledger = load(out/f'audit-{name}.json.gz')
    finished = defaultdict(Counter)
    walking = set()
    for trip in ledger['legs']:
        walking.update(leg[3] for leg in trip['legs'] if leg[0]==0)
        uid = trip['id']
        group = plans[uid]+'|'+b['destination_keys'][str(uid)]
        if group in upper:
            row = finished[group]
            row['total'] += trip['weight']
            if not trip['unserved'] and not any(leg[0]==3 for leg in trip['legs']):
                row['end_to_end_walk'] += trip['weight']
    result.update(model=MODEL,upper_initial=upper,upper_completed=finished,walk_paths_used=sorted(walking))
    if rail:
        dest = DATA/f'{name}.json.gz'
        tmp = dest.with_suffix('.tmp')
        shutil.copyfile(out/f'{name}.json.gz',tmp)
        os.replace(tmp,dest)
    previous.SAVE(out/'result.tmp',result)
    os.replace(out/'result.tmp',out/'result.json')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--day',choices=DAYS,default='월')
    parser.add_argument('--service',choices=('regular','peak'),default='regular')
    parser.add_argument('--without-rail',action='store_true')
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--new-attempt',action='store_true')
    args=parser.parse_args()
    if args.prepare:
        prepare()
    else:
        assert (INPUTS/'weekday_targets.json').is_file()
        result=run(args.day,args.service,not args.without_rail,args.new_attempt)
        print(MODEL,result['day'],result['service'],result['status'],flush=True)
