from pathlib import Path
import json,gzip,hashlib,sys,math
w=Path(sys.argv[1]).resolve();p=w/'runs/primaryfix-combined-regular-tue/attempt_01/audit-regular-tue.json.gz'
a=json.loads(gzip.decompress(p.read_bytes()));tail=json.loads((w/'new-tail-diagnosis.json').read_bytes())
r=tail['worst'];now=r['student_first_release']['time'];eta=tail['reconsiderations'][0]['current_eta']
lastwalk=tail['finished_branches'][0]['legs'][-1];walk=lastwalk[2]-lastwalk[1]
fleet=[v for v in a['vehicles'] if v['rid']=='100100251']
v=min(fleet,key=lambda v:abs(v['times'][12]+walk-eta));assert abs(v['times'][12]+walk-eta)<1e-5
target=2;known=[]
for z in a['wait_audit']:
    if z['vehicle']!=v['id'] or z['outcome']!='boarded' or z['arrival']>now or z['end']<=now:continue
    intent=z['boarding_intent']
    if intent['board']<target and intent['alight']>target:
        eligible=next((q['services'] for q in reversed(z['eligibility_periods']) if q['from']<=now),[])
        if [v['rid'],intent['board']] in eligible:known.append(z)
events=[e for e in a['events'] if e[2]==v['id']]
arrival=next(e for e in events if e[12]==target)
past=[e for e in a['events'] if e[1]==r['node'] and e[11]==v['rid'] and e[12]==target and 0<=now-e[0]<=1800]
out={'information_time':now,'uid':r['id'],'predicted_vehicle':v['id'],'predicted_board_at':v['times'][target],
     'predicted_finish':eta,'actual_target_arrival_event':arrival,
     'known_upstream_queue_members_later_on_that_vehicle_weight':math.fsum(z['weight'] for z in known),
     'known_upstream_waiting_rows':known,'recent_free_before_target_queue':[{'time':e[0],'free':e[3]-e[4]+e[5]} for e in past[-3:]],
     'scope':'Retrospective diagnosis of omitted demand already waiting at forecast time; future outcomes used ONLY to diagnose, never as predictor input.'}
f=w/'known-upstream-omission.json';assert not f.exists();f.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print({k:v for k,v in out.items() if k!='known_upstream_waiting_rows'},flush=True)
