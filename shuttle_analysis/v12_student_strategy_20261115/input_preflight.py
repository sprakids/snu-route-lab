"""Prepare once to check candidate destinations and immutable source mass; no simulation."""
from pathlib import Path
import argparse,json,sys,hashlib,math,collections
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');p.add_argument('--output',default='input-preflight.json');a=p.parse_args();w=Path(a.candidate).resolve();sys.path.insert(0,str(w))
    from artifacts import read
    from prepare import prepare
    cfg=read(w/'config.json');cfg.update(behavior='sequential',physics='path_local_4p8',origin_choice=True,operations='v12_empirical',boarding_choice=True)
    c=read(w/'experiment_lock.json')['pilot_cases'][0];b=prepare(c,cfg);common=b['prepared']['common'];lookup={}
    for i,n in enumerate(common['nodes']):
        if n.get('route')!='city':lookup[f"{n.get('route')}|{n.get('board')}"]=i
    lookup.update(b['city_node_lookup']);bad=[];ends=0;groups=0
    def leaf_walks(chain):
        if not chain:return []
        out=[]
        for e in chain[0].get('pool',[chain[0]]):
            tail=e.get('continuation_stages',chain[1:])
            out.extend(leaf_walks(tail) if tail else [e['next_walk'][0]])
        return out
    for key,options in b['student_origin_catalog'].items():
        # Keys are Python tuple reprs generated from trusted frozen inputs.
        import ast
        building,dest,origin=ast.literal_eval(key);target=common['destinations'][dest];groups+=1
        for o in options:
            start=common['paths'][o['walk'][0]][0]
            assert tuple(start)==origin
            walks=leaf_walks(o['stages']) if o['stages'] else [o['walk'][0]]
            for pid in walks:
                end=common['paths'][pid][-1];meters=math.hypot((end[0]-target[0])*111320,(end[1]-target[1])*88200);ends+=1
                if meters>2:bad.append({'dest':dest,'path':pid,'error_m':meters})
    assert abs(sum(b['source_parent_mass'].values())-sum(p[3] for p in b['prepared']['plans'][c['day']]))<1e-6
    result={'status':'PASS' if not bad else 'WRONG_DESTINATION_CANDIDATES','catalog_groups':groups,'candidate_leaf_endpoint_checks':ends,
      'wrong_destination_candidates':bad,'source_mass':sum(b['source_parent_mass'].values()),'prepared_packets':len(b['prepared']['plans'][c['day']]),
      'runtime_not_simulated':True,'production_writes':False}
    out=w/a.output;assert not out.exists();out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(result['status'],groups,ends,'endpoint checks; bad',len(bad),flush=True)
    assert not bad
if __name__=='__main__':main()
