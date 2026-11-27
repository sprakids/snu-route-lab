"""Account for journey changes by original destination/mode and actual first ride."""
from pathlib import Path
import argparse,gzip,json,math,csv,collections
PARENT=Path(__file__).resolve().parent.parent/'261112220847'
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');p.add_argument('--group',default='observations');a=p.parse_args();w=Path(a.candidate).resolve();out=w/(a.group+'-route-diagnosis.json');assert not out.exists()
    frozen=read(w/'frozen/prepared_capacity44_pair.json.gz');common=frozen['prepared']['common'];source={day:{p[0]:p for p in plans} for day,plans in frozen['prepared']['plans'].items()};rows=[]
    for model in (PARENT,w):
        results=read(model/('grid-validation.json' if model==PARENT else a.group+'-validation.json'))['results']
        for r in results:
            c=r['case']
            if c['scenario']!='regular' or c['day'] not in ('월','화'):continue
            did={'월':'mon','화':'tue'}[c['day']];audit=read(Path(r['source_directory'])/f'audit-regular-{did}.json.gz');agg={};stops={};backtrack=0.
            for t in audit['legs']:
                s=source[c['day']][t['parent_id']];dest=frozen['destination_keys'][str(t['parent_id'])];mode='walk' if not s[6] else 'shuttle' if s[6][0]['rid'].startswith('shuttle') else 'city';weight=t['weight'];key=dest+'|'+mode
                row=agg.setdefault(key,collections.Counter());row['mass']+=weight
                for label,kind in [('walk',0),('wait',1),('ride',3)]:row[label]+=weight*sum((min(l[2],83400) if t['unserved'] else l[2])-l[1] for l in t['legs'] if l[0]==kind)/60
                row['unserved_mass']+=weight if t['unserved'] else 0.
                first=next((l for l in t['legs'] if l[0]==3),None)
                if first is not None:
                    node=first[4];stops[node]=stops.get(node,0.)+weight
                    if dest=='snu':
                        target=common['destinations'][dest];path=common['paths'][first[3]]
                        distance=lambda q:math.hypot((q[0]-target[0])*111320,(q[1]-target[1])*88200)
                        extra=max(map(distance,path))-distance(path[0])
                        if extra>500:row['first_ride_away_over500m_mass']+=weight;backtrack+=weight
            rows.append({'model':model.name,'weekday':c['day'],'groups':{k:{**dict(v),'mean_walk':v['walk']/v['mass'],'mean_wait':v['wait']/v['mass'],'mean_ride':v['ride']/v['mass']} for k,v in agg.items()},
              'actual_first_boarding_nodes':{str(k):{'mass':v,'name':common['nodes'][k]['name'],'ars':common['nodes'][k].get('ars')} for k,v in sorted(stops.items(),key=lambda x:-x[1])},
              'snu_first_ride_away_over500m_mass':backtrack,'scope':'500m is a retrospective route-shape diagnostic bin, not a model-fitted cutoff. Censored unfinished waits remain counted.'})
            print('ROUTE_DIAG',model.name,c['day'],'away500m',backtrack,flush=True)
    out.write_text(json.dumps({'cases':rows,'new_outcomes_opened':False,'production_writes':False},ensure_ascii=False,indent=2),encoding='utf8')
if __name__=='__main__':main()
