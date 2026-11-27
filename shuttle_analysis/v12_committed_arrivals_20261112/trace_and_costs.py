"""Weighted source-ID trace and independent arithmetic for decline cost vectors."""
from pathlib import Path
import argparse,gzip,hashlib,json,math
ROOT=Path(__file__).resolve().parent;PARENT=ROOT.parent/'261112171315'
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def scalar(pred,taste,event,cfg,changing):
    a=event['completed_wait_seconds']+max(0.,event['time']-event['physical_stop_entry']);future=pred['wait']+pred['prep']
    base=(pred['ride']+taste['walk']*pred['walk']+taste['wait']*future)/60+taste['transfer']*pred['transfers']+taste['crowd']*pred['crowd_exposure']/60+taste['fatigue']*pred['fatigue']/60
    if cfg['fare_in_choice']:base+=60*pred['fare']/taste['vot']
    if changing:base+=taste['change']*(1+.5*event['change_count'])
    q=cfg['predicted_queue_curvature_coefficient']*(2*a*future+future*future)/cfg['predicted_queue_curvature_scale_seconds']
    if cfg['integrate_future_wait_discomfort']:q+=(a*a*future+a*future*future+future**3/3)/cfg['waiting_discomfort_age_scale_seconds']**2
    base+=taste['wait']*q/60
    if not changing:base+=taste['wait']*cfg['waiting_discomfort_full_sensitivity']*event['full_passes']*pred['first_wait']/60
    return base
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');p.add_argument('--group',default='grid');a=p.parse_args();w=Path(a.candidate).resolve()
    out=w/f'{a.group}-trace-and-costs.json';assert not out.exists();traces=[];costchecks=0;maxerror=0.;maxclock=0.;source={}
    for model in (PARENT,w):
        v=read(model/('grid-validation.json' if model==PARENT else a.group+'-validation.json'))
        for r in v['results']:
            if r['case']['day']!='화' or r['case']['scenario']!='regular':continue
            path=Path(r['source_directory'])/'audit-regular-tue.json.gz';assert sha(path)==r['audit_sha256'];source[str(path)]=sha(path);audit=read(path)
            items=[x for x in audit['legs'] if x['id']==1205536];mass=math.fsum(x['weight'] for x in items);assert mass>0
            details=[]
            for t in items:
                parts={name:math.fsum(l[2]-l[1] for l in t['legs'] if l[0]==kind)/60 for name,kind in [('walk',0),('queue',1),('ride',3)]}
                total=(t['finish_time']-t['start'])/60;assert abs(math.fsum(parts.values())-total)<1e-6
                details.append({'weight':t['weight'],'duration_min':total,'leg_times':parts,'route_changes':len(t['history']),'history':t['history']})
            traces.append({'model':model.name,'uid':1205536,'parent_id':75346,'fragment_count':len(items),'mass':mass,
              'weighted_mean_total_min':math.fsum(x['weight']*x['duration_min'] for x in details)/mass,
              'maximum_total_min':max(x['duration_min'] for x in details),'fragments':details})
            if model==w:
                cfg=audit['prototype_config']
                for e in audit['boarding_choices']:
                    for predkey,costkey,changing in [('board_prediction','board_cost',False),('wait_prediction','wait_cost',False),('selected_prediction','selected_cost',e['selected_key'] not in ('board','wait'))]:
                        pred=e.get(predkey)
                        if pred is None:continue
                        physical_error=abs(pred['eta']-e['time']-math.fsum(pred[k] for k in ('walk','wait','ride','prep')))
                        maxclock=max(maxclock,physical_error);assert physical_error<1e-5,(e['uid'],predkey,physical_error)
                        error=abs(scalar(pred,e['traits'],e,cfg,changing)-e[costkey]);maxerror=max(maxerror,error);costchecks+=1
                        assert error<1e-6,(e['uid'],e['time'],predkey,error)
    assert len(traces)==2 and abs(traces[0]['mass']-traces[1]['mass'])<1e-9
    result={'status':'PASS_TARGET_MASS_TIME_AND_DECLINE_COST_ARITHMETIC','traces':traces,'cost_vectors_checked':costchecks,
      'maximum_cost_error_minutes':maxerror,'maximum_physical_prediction_clock_error_seconds':maxclock,
      'cost_check_scope':'Tuesday regular declined opportunities only; other weekday/scenario physical ledgers audited separately',
      'source_audits':source,'scope':'Existing weighted model traces, not actual people; not a causal estimate from one UID; cost arithmetic does not validate preference coefficients.'}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print('TRACE_COST_PASS',[(x['model'],x['weighted_mean_total_min'],x['fragment_count']) for x in traces],'vectors',costchecks,flush=True)
if __name__=='__main__':main()
