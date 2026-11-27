"""Small isolated refit of the existing initial-gate coefficient after behavior changes.

Only previously reallocated initial plans can return to their frozen v5 route.
IDs, weights, buildings, destinations, departure times, supply and speeds stay fixed.
This is calibration on the same three reports, not independent validation.
"""
from pathlib import Path
from collections import Counter
import argparse,copy,csv,time,json
import capacity_model as base
from prepare_walk_choices import ROOT,read
import walk_choice_model as model
from gate_access_calibration import minute_summary

SOURCE=ROOT/'crowding_walk_choices_2026-11-10/congestion_trigger_G'
WORK=ROOT/'crowding_walk_choices_2026-11-10/initial_refit_H'
ALPHA=.70

def prepare():
    WORK.mkdir(exist_ok=True);path=WORK/'prepared.json.gz'
    if path.exists():
        bundle=read(path);assert bundle['initial_gate_refit']['alpha']==ALPHA;return bundle
    bundle=read(SOURCE/'prepared.json.gz');prior=read(ROOT/'city_bus_model_2026-11-08/prepared.json.gz')
    original=read(ROOT/'gate_access_calibration_2026-11-09/candidates/alpha_075/prepared.json.gz')
    assert bundle['prepared']['common']['route_info']==original['prepared']['common']['route_info']
    assert original['prepared']['common']['route_info']==prior['prepared']['common']['route_info']
    frozen={p[0]:p for plans in prior['prepared']['plans'].values() for p in plans}
    current={p[0]:p for plans in bundle['prepared']['plans'].values() for p in plans};restored=[]
    with (ROOT/'gate_access_calibration_2026-11-09/candidates/alpha_075/reallocated_particles.csv').open(encoding='utf-8-sig') as stream:
        for row in csv.DictReader(stream):
            probability=ALPHA*max(0.,1-float(row['gate_walk_seconds'])/900)
            if float(row['stable_uniform'])<probability:continue
            uid=int(row['particle_id']);p=current[uid];old=frozen[uid];assert p[:5]==old[:5]
            for pid in [old[5][0],*[s['next_walk'][0] for s in old[6]]]:
                assert bundle['prepared']['common']['paths'][pid]==prior['prepared']['common']['paths'][pid]
            p[5:]=copy.deepcopy(old[5:]);restored.append({**row,'new_alpha':ALPHA})
    for day,plans in bundle['prepared']['plans'].items():
        before=original['prepared']['plans'][day];assert [p[:5] for p in plans]==[p[:5] for p in before]
    changes=Counter()
    for r in restored:changes[r['weekday']]+=float(r['weight'])
    meta={'alpha':ALPHA,'previous_alpha':.75,'selection_observations':3,'not_independent_validation':True,
          'changed_only_initial_route_reallocation':True,'source_prepared_sha256':base.sha(SOURCE/'prepared.json.gz'),
          'restored_weight_by_day':dict(changes),'source_helper_sha256':base.sha(Path(__file__))}
    bundle['initial_gate_refit']=meta
    common=bundle['prepared']['common'];common['gate_access_calibration']={**common['gate_access_calibration'],'alpha':ALPHA,'refit_for_walk_choices':meta}
    bundle['gate_access_calibration']=common['gate_access_calibration'];common['walk_choice_behavior']['initial_gate_refit']=meta
    base.packed(path,bundle);base.save(WORK/'preparation_verification.json',{'status':'PASS','same_demand_ids_weights_origins_destinations_departures':True,
                         'same_supply_speed_capacities':True,'metadata':meta})
    with (WORK/'initial_routes_restored.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,list(restored[0]));writer.writeheader();writer.writerows(restored)
    return bundle

def run(day,scenario):
    bundle=prepare();did=base.DAYS[day];receipt=WORK/f'run-{scenario}-{did}.json'
    if receipt.exists():assert read(receipt)['status']=='PASS';return
    startfile=WORK/f'started-{scenario}-{did}.json';assert not startfile.exists()
    sha=base.sha(Path(model.__file__));base.save(startfile,{'model_sha256':sha,'prepared_sha256':base.sha(WORK/'prepared.json.gz')})
    model.WORK=WORK;model.OUT=WORK/'public_data';model.OUT.mkdir(exist_ok=True);base.OUT=model.OUT
    t=time.perf_counter();data=model.simulate(bundle,day,scenario)
    result={'status':'PASS','model_sha256':sha,'elapsed_seconds':time.perf_counter()-t,'scenario':scenario,'weekday':day,'report':data['report']}
    if day=='월':result['observation_fit']=minute_summary(data,bundle['prepared']['common'])
    base.save(receipt,result);print('REFIT_DONE',json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--day',default='월',choices=list(base.DAYS));p.add_argument('--scenario',default='peak',choices=list(base.SCENARIOS));args=p.parse_args();run(args.day,args.scenario)
