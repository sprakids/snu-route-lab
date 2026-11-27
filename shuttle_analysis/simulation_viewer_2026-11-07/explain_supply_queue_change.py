"""Exact internal queue ledger at the new report minute, without fitting a second."""
from pathlib import Path
import math
import capacity_model as base
from prepare_walk_choices import read
ROOT=Path(__file__).resolve().parent

def main():
    result=[];a=15*3600+23*60;b=a+60
    for directory,label in [('crowding_walk_choices_2026-11-10/initial_refit_H','v9_60_single'),('capacity44_correction_2026-11-10','44_single'),('peak_pair_correction_2026-11-10','44_pair')]:
        for s in ('regular','peak'):
            audit=read(ROOT/directory/f'audit-{s}-tue.json.gz');rows=[r for r in audit['wait_audit'] if r['node']==1]
            start=math.fsum(r['weight'] for r in rows if r['arrival']<=a<r['end'])
            end=math.fsum(r['weight'] for r in rows if r['arrival']<b<=r['end'])
            arrivals=math.fsum(r['weight'] for r in rows if a<r['arrival']<b)
            leaving={outcome:math.fsum(r['weight'] for r in rows if a<r['end']<b and r['outcome']==outcome) for outcome in ('boarded','switched','unserved')}
            assert abs(start+arrivals-sum(leaving.values())-end)<1e-5
            result.append({'case':label,'scenario':s,'queue_at_15_23':start,'arrivals_in_minute':arrivals,**leaving,'queue_before_15_24_departures':end})
    base.save(ROOT/'peak_pair_correction_2026-11-10/queue_minute_ledger.json',{'status':'PASS','window':'15:23:00 to15:24:00 exclusive departures at15:24',
        'meaning':'internal weighted stop-visit balance, not observed causal behavior or added unique students','rows':result})
    print(result)

if __name__=='__main__':main()
