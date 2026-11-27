"""Read the completed V12 ledgers, never run or change a model."""
from pathlib import Path
from collections import Counter
import csv, gzip, hashlib, json, math

ROOT=Path(__file__).resolve().parent
PARENT=ROOT.parent/'261112111627'
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def describe(trip,audit,nodes):
    visits=[]
    for leg in trip['legs']:
        if leg[0]!=1:continue
        if visits and visits[-1]['node']==leg[4] and abs(visits[-1]['end']-leg[1])<1e-5:visits[-1]['end']=leg[2]
        else:visits.append({'node':leg[4],'name':nodes[leg[4]]['name'],'start':leg[1],'end':leg[2]})
    uid=trip['id'];start=trip['start'];end=trip['finish_time']
    decisions=[d for d in audit['behavior_decisions'] if d['uid']==uid and start<=d['time']<=end]
    boards=[d for d in audit['boarding_choices'] if d['uid']==uid and start<=d['time']<=end]
    return {**{k:trip[k] for k in ('id','weight','parent_id','start','finish_time','history','traits')},
        'total_min':(end-start)/60,'walk_min':sum(l[2]-l[1] for l in trip['legs'] if l[0]==0)/60,
        'wait_min':sum(l[2]-l[1] for l in trip['legs'] if l[0]==1)/60,
        'ride_min':sum(l[2]-l[1] for l in trip['legs'] if l[0]==3)/60,
        'visits':visits,'changes':decisions,'boarding_declines':boards}
def main():
    target=ROOT/'baseline_diagnosis.json';assert not target.exists()
    nodes=read(PARENT/'frozen/prepared_capacity44_pair.json.gz')['prepared']['common']['nodes']
    result={'source_release':PARENT.name,'scope':'weighted simulated trips, not observed students','cases':[]}
    for day,scenario in [('tue','regular'),('mon','regular'),('tue','peak')]:
        p=PARENT/f'runs/v12_empirical-combined-{scenario}-{day}/attempt_01/audit-{scenario}-{day}.json.gz'
        a=read(p);finished=[t for t in a['legs'] if not t['unserved']]
        changes=a['behavior_decisions'];declines=a['boarding_choices'];reviews=a['review_diagnostics']
        weight=lambda rows:math.fsum(x['weight'] for x in rows)
        row={'day':day,'scenario':scenario,'audit_sha256':sha(p),'top_keys':list(a),
            'changes':len(changes),'change_weight':weight(changes),'declines':len(declines),'decline_weight':weight(declines),
            'switches_to_later_eta_weight':weight([x for x in changes if x['old_eta'] is not None and x['new_eta']>x['old_eta']+1e-6]),
            'switches_over5min_later_eta_weight':weight([x for x in changes if x['old_eta'] is not None and x['new_eta']>x['old_eta']+300]),
            'most_declined_stops':[{'node':n,'name':nodes[n]['name'],'count':c} for n,c in Counter(x['node'] for x in declines).most_common(8)],
            'worst_all':describe(max(finished,key=lambda x:x['finish_time']-x['start']),a,nodes),
            'worst_after1500':describe(max((x for x in finished if x['start']>=54000),key=lambda x:x['finish_time']-x['start']),a,nodes),
            'review_count_after10min':len(reviews),
            'selected_not_lowest_cost':sum(x['selected']!=x['best_costs'][0][0] for x in reviews if x['best_costs']),
            'over90_weight':weight([x for x in finished if x['finish_time']-x['start']>5400]),
            'over120_weight':weight([x for x in finished if x['finish_time']-x['start']>7200])}
        result['cases'].append(row)
        print(day,scenario,'changes',len(changes),'declines',len(declines),'worst',row['worst_all']['total_min'],
              'worst decline count',len(row['worst_all']['boarding_declines']),flush=True)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
if __name__=='__main__':main()
