"""Preparation-only audit: no vehicle events or new field outcomes."""
from pathlib import Path
from collections import Counter
import copy,hashlib,json,sys,gc
ROOT=Path(__file__).resolve().parent;w=Path(sys.argv[1]).resolve();sys.path.insert(0,str(w))
from prepare import prepare
from walking_opportunities import WalkingOpportunities
def read(p):return json.loads(p.read_bytes())
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
case=next(c for c in read(w/'experiment_lock.json')['pilot_cases'] if c['day']=='화' and not c['case'].startswith('ablation'))
cfg=read(w/'config.json');cfg.update(physics='path_local_4p8',behavior='sequential',origin_choice=True,boarding_choice=True,operations=case['operations'])
summaries={};keys={};old_options={}
for enabled in [False,True]:
    effective={**cfg,'restore_known_snu_direct_policies':enabled};b=prepare(case,effective)
    nodes=b['prepared']['common']['nodes'];lookup={n['id']:i for i,n in enumerate(nodes)}
    def nf(e):
        k=f"{e['rid']}|{e['board']}"
        return lookup[k] if e['rid'].startswith('shuttle') else b['city_node_lookup'][k]
    catalog=b['student_origin_catalog']
    keys[enabled]={k:{o['key'] for o in os} for k,os in catalog.items()}
    if not enabled:old_options={k:{o['key']:digest(o) for o in os} for k,os in catalog.items()}
    else:
        assert set(keys[False])<=set(keys[True])
        for k,options in old_options.items():
            new={o['key']:o for o in catalog[k]}
            assert set(options)<=set(new)
            assert all(digest(new[key])==value for key,value in options.items())
        assert b['catalog_repair_report']['restored_count']==5
        assert {r['key'] for r in b['catalog_repair_report']['restored_policies']}=={f'{node}|snu' for node in [53,54,55,56,57]}
    summary={'plans':digest(b['prepared']['plans']),'parent_ids':digest(b['parent_ids']),'source_parent_mass':digest(b['source_parent_mass']),
        'destination_keys':digest(b['destination_keys']),'walk_scales':digest(b['walk_scales']),
        'global_compatible_catalog':digest(b['compatible_route_policies']),
        'global_single_stage_catalog':digest(b['compatible_single_stage_pools']),
        'alternatives':digest(b['alternatives']),'supply':digest(b['supply']),'operations':digest(b['operations']),
        'physical_paths':digest(b['physical_paths']),
        'student_origin_groups':len(catalog),'student_origin_options':sum(map(len,catalog.values())),
        'catalog_report':b.get('catalog_repair_report')}
    op=WalkingOpportunities(b,nf,effective)
    summary['enroute_entries']=digest(sorted((repr(key),repr([(svc,entry) for svc,entry in services.items()])) for key,services in op.entries.items()))
    summary['enroute_walk_ids']=digest(sorted(op.walk_ids))
    summaries[enabled]=summary
    del op,b;gc.collect()
checked=['plans','parent_ids','source_parent_mass','destination_keys','walk_scales','global_compatible_catalog',
         'global_single_stage_catalog','alternatives','supply','operations','physical_paths','enroute_entries','enroute_walk_ids']
for name in checked:assert summaries[False][name]==summaries[True][name],name
out=w/'preparation-catalog-audit.json';assert not out.exists()
out.write_text(json.dumps({'status':'PASS_PREPARATION_ONLY','model_events_executed':0,'case':case,
    'unchanged_domains':checked,'disabled':summaries[False],'enabled':summaries[True],
    'existing_origin_options_preserved':True,'added_origin_options':summaries[True]['student_origin_options']-summaries[False]['student_origin_options'],
    'new_date_accuracy':'NOT_EVALUATED','production_writes':False},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('PREPARATION_CATALOG_AUDIT_PASS','new options',summaries[True]['student_origin_options']-summaries[False]['student_origin_options'],flush=True)
