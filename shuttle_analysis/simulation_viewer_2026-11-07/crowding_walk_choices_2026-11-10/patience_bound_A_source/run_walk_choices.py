"""Run isolated candidate cases; never publish or overwrite the active model."""
from datetime import datetime,timezone,timedelta
import argparse,json,time,traceback
import capacity_model as base
import walk_choice_model as model
from prepare_walk_choices import prepare,WORK,RULE
from gate_access_calibration import minute_summary

def run(day,scenario):
    bundle=prepare();did=base.DAYS[day];out=WORK/'public_data';out.mkdir(exist_ok=True)
    receipt=WORK/f'run-{scenario}-{did}.json';started=WORK/f'started-{scenario}-{did}.json'
    if receipt.exists():
        saved=base.read(receipt);assert saved['status']=='PASS';print('REUSED',scenario,did,flush=True);return
    assert not started.exists(),f'Inspect preserved incomplete run before resuming: {started}'
    model.WORK=WORK;model.OUT=out;base.OUT=out
    source_hash=base.sha(model.__file__)
    base.save(started,{'status':'STARTED','model_sha256':source_hash,'prepared_sha256':base.sha(WORK/'prepared.json.gz'),
                      'case':[scenario,day],'started_at':datetime.now(timezone(timedelta(hours=9))).isoformat(),'rule':RULE})
    t=time.perf_counter()
    try:
        data=model.simulate(bundle,day,scenario)
        result={'status':'PASS','model_sha256':source_hash,'elapsed_seconds':time.perf_counter()-t,
                'scenario':scenario,'weekday':day,'report':data['report']}
        if day=='월':result['observation_fit']=minute_summary(data,bundle['prepared']['common'])
        base.save(receipt,result)
        print('WALK_CHOICE_DONE',json.dumps(result,ensure_ascii=False),flush=True)
    except Exception:
        base.save(WORK/f'failure-{scenario}-{did}.json',{'status':'FAILED','model_sha256':source_hash,'traceback':traceback.format_exc()})
        raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--day',choices=list(base.DAYS),required=True);p.add_argument('--scenario',choices=list(base.SCENARIOS),required=True)
    args=p.parse_args();run(args.day,args.scenario)
