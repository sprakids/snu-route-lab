"""Score already-completed pilots; independently integrate immutable queue traces."""
from pathlib import Path
from datetime import datetime,timezone
from bisect import bisect_right
import argparse,csv,gzip,hashlib,json,math
ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent
MODELS={'261112164617':1.,'261112165437':.75,'261112165438':.5,
        '261112170547':1.25,'261112170548':1.5,'261112171315':1.125}
PRIMARY=['20261109-1653-admin-snu-queue-01','20261109-1703-snu-gate-queue-01',
         '20261110-1523-admin-snu-queue-wait-01']
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
def integrate(points,start,low,high):
    # Independent boundary construction instead of the producer's forward sweep.
    times=[p[0] for p in points];end=start+60
    edges=sorted({start,end,*[t for t in times if start<t<end]})
    pieces=[]
    for a,b in zip(edges,edges[1:]):
        k=bisect_right(times,(a+b)/2)-1;q=points[k][1] if k>=0 else 0.
        pieces.append((q,b-a))
    assert abs(math.fsum(dt for q,dt in pieces)-60)<1e-7
    return math.fsum(q*dt for q,dt in pieces)/60,math.fsum(max(low-q,0,q-high)*dt for q,dt in pieces)/60
def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['initial','extended','final'],required=True);a=p.parse_args()
    target=ROOT/f'calibration_selection_{a.stage}.json';assert not target.exists()
    models=dict(list(MODELS.items())[:3 if a.stage=='initial' else 5 if a.stage=='extended' else 6])
    scores=[];evidence={}
    for stamp,alpha in models.items():
        work=ANALYSIS/stamp;d=read(work/'observations-diagnostics.json');v=read(work/'observations-validation.json')
        evidence[stamp]={name:sha(work/name) for name in ('observations-field-comparison.csv','observations-diagnostics.json','observations-validation.json','experiment_lock.json')}
        fields=[r for r in rows(work/'observations-field-comparison.csv') if r['model']==stamp and r['scenario']=='regular']
        assert len(fields)==4 and len(v['results'])==2
        components=[]
        for event in d['historical_queue_observations']:
            row=next(r for r in fields if r['observation_id']==event['observation_id'])
            result=next(r for r in v['results'] if r['case']['day']==event['day'])
            did='mon' if event['day']=='월' else 'tue'
            trace=read(Path(result['source_directory'])/f'regular-{did}.json.gz')['queue_timeline'][event['node']]
            mean,loss=integrate(trace,event['second'],event['low'],event['high'])
            assert abs(mean-float(row['uniform_minute_mean']))<1e-7
            assert abs(loss-float(row['expected_absolute_distance_to_count_or_interval']))<1e-7
            midpoint=(event['low']+event['high'])/2
            components.append({'observation_id':event['observation_id'],'date':'2026-11-09' if event['day']=='월' else '2026-11-10',
              'monday_date_inferred':event['day']=='월','reported_minute':event['minute'],'stop':event['stop'],
              'direction_confirmed':event['observation_id'] in PRIMARY,'observed_interval':[event['low'],event['high']],
              'midpoint_denominator':midpoint,'uniform_minute_mean':mean,'minute_minimum':float(row['minute_minimum']),
              'minute_maximum':float(row['minute_maximum']),'expected_absolute_interval_error':loss,
              'normalized_component':loss/midpoint,'primary':event['observation_id'] in PRIMARY})
        feasible=d['all_invariant_audits_pass'] and d['all_continuous_waits_under20'] and d['unserved_trip_weight']<1e-7
        score=math.fsum(x['normalized_component'] for x in components if x['primary'])/3
        scores.append({'model':stamp,'alpha':alpha,'primary_normalized_loss':score,'pilot_internally_feasible':feasible,
          'components':components,'max_continuous_wait_min':max(r['extended_diagnostics']['all_recorded_time_max_continuous_wait_min'] for r in v['results']),
          'full10_conditions_checked':(work/'grid-diagnostics.json').exists()})
    ranked=sorted((s for s in scores if s['pilot_internally_feasible']),key=lambda s:(s['primary_normalized_loss'],abs(s['alpha']-1)))
    parent_fields=[r for r in rows(ANALYSIS/'261112132736/grid-field-comparison.csv') if r['model']=='261112132736' and r['scenario']=='regular' and r['observation_id'] in PRIMARY]
    assert len(parent_fields)==3
    parent_loss=math.fsum(float(r['expected_absolute_distance_to_count_or_interval'])/((float(r['observed_low'])+float(r['observed_high']))/2) for r in parent_fields)/3
    out={'status':'PILOT_SELECTION_ONLY_FULL_GRID_REQUIRED','stage':a.stage,'scored_at':datetime.now(timezone.utc).isoformat(),
      'criterion':'mean E_uniform-minute[d(Q,[L,U])]/midpoint over three direction-confirmed reports',
      'scores':scores,'ranking':[s['model'] for s in ranked],'selected_for_full_grid':ranked[0]['model'],
      'parent_model':'261112132736','parent_primary_normalized_loss':parent_loss,
      'alpha_only_control_model':'261112164617','reused_queue_reports_not_independent_holdout':True,
      'stage2_grid_expanded_after_initial_results':a.stage!='initial','final_midpoint_after_coarse_tradeoff':a.stage=='final','new_day_outcomes_opened':False,
      'source_sha256':evidence,'production_replacement_allowed':False}
    target.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
    print('PILOT_RANKING',[(s['model'],s['alpha'],round(s['primary_normalized_loss'],6)) for s in ranked],flush=True)
    print('PARENT_LOSS',parent_loss,'FULL_GRID_REQUIRED',ranked[0]['model'],flush=True)
if __name__=='__main__':main()
