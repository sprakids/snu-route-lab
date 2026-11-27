"""Reconstruct a past model state without feeding later arrivals or outcomes to it."""
from collections import defaultdict
from pathlib import Path
import bisect,gzip,json,sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import engine
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def main():
    target=ROOT/'thu_queue_forecast_replay.json';assert not target.exists()
    folder=ROOT/'runs/distribution_v8-combined-peak-thu/attempt_01'
    audit=read(folder/'audit-peak-thu.json.gz');bundle=read(ROOT/'frozen/prepared_capacity44_pair.json.gz')
    t=61967.96325056685;n=79;uid=674864
    owner=next(m for m in audit['wait_audit'] if m['id']==uid and m['node']==n and m['arrival']<=t<m['end'])
    current=[m for m in audit['wait_audit'] if m['node']==n and m['ready']<=t<m['end'] and m['ticket']<owner['ticket']]
    past_seats=defaultdict(list)
    for e in audit['events']:
        if e[0]<=t:past_seats[e[11],e[12]].append((e[0],e[3]-e[4]+e[5]))
    past_seats={k:v[-3:] for k,v in past_seats.items()}
    fleet=[]
    for v in audit['vehicles']:
        fleet.append({**v,'onboard':[],'last_stop':bisect.bisect_right(v['times'],t)-1,
                      'seat_history':past_seats,'seat_forecast_horizon_seconds':1800,'seat_history_seconds':1800,'seat_history_count':3})
    for trip in audit['legs']:
        for leg in trip['legs']:
            if leg[0]!=3 or not(leg[1]<=t<leg[2]):continue
            vid=leg[6];times=fleet[vid]['times'];dest=bisect.bisect_left(times,leg[2]-1e-6)
            assert abs(times[dest]-leg[2])<1e-5
            fleet[vid]['onboard'].append((dest,{'w':trip['weight']}))
    services=[(s['rid'],s['board']) for s in bundle['prepared']['common']['nodes'][n]['services']]
    rows=sorted((v['times'][k],v['id'],k) for v in fleet for rid,k in services if v['rid']==rid)
    def stage(eligibility):return {'pool':[{'rid':rid,'board':k} for rid,k in eligibility]}
    old=[];new=[];changed=[]
    for m in current:
        rejected={(d['route'],d['stop_index']) for d in audit['boarding_choices'] if d['uid']==m['id'] and d['node']==n
                  and m['arrival']<=d['time']<=t and d['board_cost']-d['wait_cost']>24}
        original=[tuple(s) for s in m['eligibility']];updated=[s for s in original if s not in rejected]
        old.append({'w':m['weight'],'stages':[stage(original)],'stage':0})
        new.append({'w':m['weight'],'stages':[stage(updated)],'stage':0})
        if updated!=original:changed.append({'weight':m['weight'],'removed_from_predicted_clearance':sorted(rejected),'actual_eligibility_preserved':original})
    own=stage(owner['eligibility']);ready=max(t,owner['ready'])
    def forecast(waiting):
        value=engine.first_boardable(rows,fleet,ready,t,own,owner['weight'],waiting)
        return None if value is None else {'when':value[0],'vehicle':value[1],'route':value[3]['rid']}
    result={'status':'CAUSAL_STATE_REPLAY_NOT_A_RERUN','query_second':t,'owner_uid':uid,'node':n,'owner_weight':owner['weight'],
            'ahead_current_weight':sum(m['weight'] for m in current),'known_strong_decline_weight':sum(m['weight'] for m in changed),
            'original_forecast':forecast(old),'past_decline_aware_forecast':forecast(new),'changed_patterns':changed,
            'inputs':'Queues ready and still present at t, onboard rides active at t, only passage/decline records at or before t. Fixed future exogenous clocks remain known as in R7.',
            'diagnostic_outcome_not_forecast_input':'At62592.932 the02-2 hadzero free seats and this traveler later walked away; not used by either forecast.'}
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k!='changed_patterns'},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
