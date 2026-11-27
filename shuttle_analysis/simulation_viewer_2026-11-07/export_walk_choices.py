"""Export only a fully verified v9; retain v3-v8 and every private trial."""
from pathlib import Path
import gzip,json,shutil,hashlib,html
from collections import Counter
import capacity_model as base
from prepare_walk_choices import ROOT,read
from selected_walk_choice import selected_work
from walk_choice_model import walking_weight

def immutable_copy(source,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        assert target.read_bytes()==source.read_bytes(),f'Existing immutable export differs: {target}'
    else:shutil.copy2(source,target)

def main():
    WORK=selected_work()
    verified=read(WORK/'independent_verification.json')
    assert verified['status']=='PASS' and verified['simulation_runs']==10
    assert verified['all_stop_quality']['all_cases_pass']
    public=ROOT/'public';target=public/'data/capacity_v9'
    for name in ['common','charts',*[f'{s}-{d}' for s in ('peak','regular') for d in base.DAYS.values()]]:
        for suffix in ('.json','.json.gz'):immutable_copy(WORK/'public_data'/f'{name}{suffix}',target/f'{name}{suffix}')
    for suffix in ('.json','.json.gz'):
        immutable_copy(WORK/'public_data'/f'half_hour{suffix}',public/'data/half_hour_v1'/f'capacity_v9{suffix}')
    review=read(WORK/'all_stops_waits.json')
    review['route_change_distribution']={}
    for scenario in ('peak','regular'):
        review['route_change_distribution'][scenario]={}
        for day in base.DAYS.values():
            audit=read(WORK/f'audit-{scenario}-{day}.json.gz');hist=Counter()
            for trip in audit['legs']:hist[len(trip['history'])]+=trip['weight']
            total=sum(hist.values());mean=sum(n*w for n,w in hist.items())/total
            assert abs(mean-audit['report']['realized_mean_route_changes'])<1e-8
            review['route_change_distribution'][scenario][day]={'mean':mean,'input_weight':total,
                       'weight_by_count':dict(sorted(hist.items())),'maximum_observed_changes':max(hist),'hard_limit':None}
    review['walking_curve']=[[d,walking_weight(d)] for d in range(0,2001,5)]
    review['distance_curve_meaning']='Unstressed relative consideration weight; not the share of students who walk. Stress and ETA also affect actual choices.'
    old_out=base.OUT;base.OUT=public/'data/walk_review_v1';base.OUT.mkdir(exist_ok=True)
    base.public('report.json',review);base.OUT=old_out
    immutable_copy(WORK/'all_stops_waits.csv',public/'walk-choice-waits.csv')
    base.save(WORK/'export_verification.json',{'status':'PASS','dataset':'capacity_v9','scientific_model_sha256':verified['model_sha256'],
                                            'previous_versions_preserved':True,'private_audits_published':False})
    print('Exported verified v9 and 990 stop/scenario/day records; no activation yet')

if __name__=='__main__':main()
