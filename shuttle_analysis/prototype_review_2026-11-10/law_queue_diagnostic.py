"""Post-hoc queue ledgers under matched4.8km/h, demand and V8 clocks."""
from pathlib import Path
import bisect,csv,gzip,hashlib,json,math
ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    target=ROOT/'law_queue_diagnostic.json';assert not target.exists()
    settings=[('previous_behavior',ANALYSIS/'prototype_followup_261110165541','distribution_v8-physics-regular-mon'),
              ('candidate_behavior',ANALYSIS/'prototype_followup_261110181553','distribution_v8-combined-regular-mon')]
    rows=[];proof=[]
    for kind,root,name in settings:
        folder=root/'runs'/name/'attempt_01';data=read(folder/'regular-mon.json.gz');audit=read(folder/'audit-regular-mon.json.gz')
        f=read(root/'frozen/prepared_capacity44_pair.json.gz');nodes=f['prepared']['common']['nodes']
        parents={p[0]:p for p in f['prepared']['plans']['월']}
        for node,meta in enumerate(nodes):
            if not meta.get('city') or meta['name']!='법대.사회대입구':continue
            peak=max(data['queue_timeline'][node],key=lambda x:x[1]);t=peak[0];a=t-900
            visits=[r for r in audit['waits'] if r[0]==node]
            inflow=math.fsum(r[3] for r in visits if a<=r[1]<=t)
            boarded=math.fsum(r[3] for r in visits if r[-1]=='boarded' and a<=r[2]<=t)
            away=math.fsum(r[3] for r in visits if r[-1]=='switched' and a<=r[2]<=t)
            before=math.fsum(r[3] for r in visits if r[1]<a<=r[2])
            mass=math.fsum(r[3] for r in visits if r[1]<=t<r[2]);assert abs(mass-peak[1])<2e-5
            mix={}
            for v in audit['wait_audit']:
                if v['node']!=node or not(v['arrival']<=t<v['end']):continue
                parent=v.get('parent_id',v['id']);dest=parents[parent][2]
                mix[dest]=mix.get(dest,0.)+v['weight']
            assert abs(math.fsum(mix.values())-mass)<2e-5
            denials=math.fsum(e[8] for e in audit['events'] if e[1]==node and a<=e[0]<=t)
            rows.append({'behavior':kind,'node':node,'stop':meta['name'],'ars':meta['ars'],'queue_peak_second':t,
                         'queue_peak_hms':f'{int(t//3600):02}:{int(t//60)%60:02}:{int(t%60):02}',
                         'maximum_queue_weight':peak[1],'queue_at_15min_start_weight':before,
                         'inflow_visit_weight_prior15min':inflow,'boarding_weight_prior15min':boarded,
                         'walk_away_visit_weight_prior15min':away,'denial_event_weight_prior15min':denials,
                         'destination_mix_json':json.dumps(mix,ensure_ascii=False)})
        proof.append({'behavior':kind,'folder':str(folder),'audit_sha256':sha(folder/'audit-regular-mon.json.gz')})
        del audit,data,f
    assert len(rows)==4
    with (ROOT/'law_queue_diagnostic.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)
    target.write_text(json.dumps({'status':'POSTHOC_SCENARIO_MECHANISM_NOT_OBSERVED_CAUSE','rows':rows,'proof':proof,
        'same_original_demand_and_V8_clocks_and4p8_physics':True,'different_peak_times_not_same_instant_causal_effect':True,
        'denial_event_weight_may_count_a_waiter_repeatedly':True,'destination_mix_is_scenario_not_observed_OD':True,
        'model_not_modified_by_this_diagnostic':True},ensure_ascii=False,indent=2),encoding='utf8')
    print('LAW_QUEUE_DIAGNOSTIC_DONE',json.dumps(rows,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
