"""Ex-post reconstruction of known-at-time states, never a simulation input."""
from collections import defaultdict
import bisect,json,sys
from artifacts import ROOT,read,save
from engine import first_boardable

def main():
    audit=read(ROOT/'runs/combined-regular-mon/attempt_04/audit-regular-mon.json.gz')
    bundle=read(ROOT/'frozen/prepared_capacity44_pair.json.gz');common=bundle['prepared']['common'];ri=common['route_info'];uid=2613248;node=70
    # The chosen subject is the longest waiting trajectory in the preserved pilot.
    owner=next(m for m in audit['wait_audit'] if m['id']==uid and m['node']==node and m['end']-m['arrival']>20000)
    trips=audit['legs'];schedule=[]
    vehicles=[]
    for v in audit['vehicles']:
        v={**v,'times':[v['t0']+x for x in ri[v['rid']]['offsets']]};vehicles.append(v)
        lookup=bundle['city_node_lookup'] if ri[v['rid']].get('city') else None
        if lookup is None:continue
        for k,t in enumerate(v['times']):
            if lookup.get(f'{v["rid"]}|{k}')==node and t<=83400:schedule.append((t,v['id'],k))
    schedule.sort();results=[]
    for now in (13*3600,14*3600,15*3600,16*3600,18*3600):
        if not owner['ready']<=now<owner['end']:continue
        for v in vehicles:v['last_stop']=bisect.bisect_right(v['times'],now)-1;v['onboard']=[]
        for trip in trips:
            for leg in trip['legs']:
                if leg[0]==3 and leg[1]<=now<leg[2]:
                    v=vehicles[leg[6]];end=bisect.bisect_left(v['times'],leg[2]-1e-7)
                    v['onboard'].append((end,{'w':trip['weight']}))
        rows=[m for m in audit['wait_audit'] if m['node']==node and m['ticket'] is not None and m['ready']<=now<m['end'] and m['ticket']<owner['ticket']]
        groups=defaultdict(float)
        for m in rows:groups[tuple(tuple(s) for s in m['eligibility'])]+=m['weight']
        waiting=[{'w':w,'stages':[{'pool':[{'rid':rid,'board':k} for rid,k in services]}],'stage':0} for services,w in groups.items()]
        owner_stage={'pool':[{'rid':rid,'board':k} for rid,k in owner['eligibility']]}
        pred=first_boardable(schedule,vehicles,now,now,owner_stage,owner['weight'],waiting)
        events=[e for e in audit['events'] if e[1]==node and now<=e[0]<owner['end'] and [e[11],e[12]] in owner['eligibility']]
        results.append({'time':now,'ahead_weight':sum(m['weight'] for m in rows),'ahead_patterns':len(groups),
            'predicted_first_boarding':pred[0] if pred else None,'actual_boarding':owner['end'],
            'predicted_remaining_minutes':(pred[0]-now)/60 if pred else None,'actual_remaining_minutes':(owner['end']-now)/60,
            'subsequent_compatible_buses':len(events),'subsequent_full_buses':sum(e[8]>0 for e in events)})
    save(ROOT/'long_wait_reconstruction.json',{'subject':owner,'purpose':'diagnostic ex-post reconstruction of current states only, not model fitting or predictive validation','results':results})
    print(json.dumps(results,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
