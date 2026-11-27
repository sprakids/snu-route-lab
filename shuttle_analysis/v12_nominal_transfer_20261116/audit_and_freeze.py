"""Preparation and provenance only; no simulated vehicle events."""
from pathlib import Path
from datetime import datetime,timezone
import gc,hashlib,json,sys,py_compile
ROOT=Path(__file__).resolve().parent;w=Path(json.loads((ROOT/'candidate.json').read_bytes())['path']);P=w.parent/'261116153200'
sys.path.insert(0,str(w));from prepare import prepare
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def save(p,v):
    assert not p.exists(),p
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
assert not (w/'pilot-started.json').exists()
for p in w.glob('*.py'):py_compile.compile(str(p),doraise=True)
cfg=read(w/'config.json');prior=read(P/'config.json')
nums={k:v for k,v in prior.items() if type(v) in (int,float)}
assert all(cfg[k]==v for k,v in nums.items())
unchanged=['engine.py','prepare.py','physics.py','operations.py','hazard.py','preferences.py','capacity.py','walking_opportunities.py','direct_restoration.py','perception.py','v12_supply.py','empirical_v12.py']
assert all(sha(w/n)==sha(P/n) for n in unchanged)
case=next(x for x in read(w/'experiment_lock.json')['pilot_cases'] if x['day']=='화' and not x['case'].startswith('ablation'))
checks={}
for enabled in [False,True]:
    effective={**cfg,'anticipated_transfer_headways':enabled,'physics':'path_local_4p8','behavior':'sequential','origin_choice':True,'boarding_choice':True,'operations':case['operations']}
    b=prepare(case,effective)
    checks[enabled]={name:digest(obj) for name,obj in {
        'plans':b['prepared']['plans'],'mass':b['source_parent_mass'],'parents':b['parent_ids'],'destinations':b['destination_keys'],
        'walk_scales':b['walk_scales'],'full_catalog':b['compatible_route_policies'],'single_catalog':b['compatible_single_stage_pools'],
        'origin_catalog':b['student_origin_catalog'],'alternatives':b['alternatives'],'supply':b['supply'],
        'operations':b['operations'],'physical_paths':b['physical_paths'],'routes':b['prepared']['routes'],
        'direct_restoration':b['catalog_repair_report']}.items()}
    del b;gc.collect()
assert checks[False]==checks[True]
save(w/'preparation-catalog-audit.json',{'status':'PASS_PREPARATION_ONLY','model_events_executed':0,'unchanged_domains':list(checks[True]),
    'disabled':checks[False],'enabled':checks[True],'production_writes':False,'new_date_accuracy':'NOT_EVALUATED'})
manifest=read(w/'repair_manifest.json');count=0
for path,h in manifest['protected'].items():assert sha(Path(path))==h,path;count+=1
for n,h in manifest['frozen_payloads'].items():assert sha(w/n)==sha(P/n)==h,n
save(w/'static-scope-proof.json',{'status':'PASS_STATIC_SCOPE','unchanged_runtime_modules':unchanged,'numeric_coefficients_unchanged':nums,
    'protected_artifacts_checked':count,'frozen_payloads':len(manifest['frozen_payloads']),'new_same_main_downstream_weight_rule':False,
    'new_queue_cap_or_forced_abandonment':False,'production_writes':False})
future=read(P/'future_evaluation_plan.json');names=list(dict.fromkeys([*future['frozen_sha256'],'nominal_transfer.py','test_nominal_transfer.py']))
future.update(release_id=w.name,declared_at=datetime.now(timezone.utc).isoformat(),
    scope='User clarification: anticipate normal transfer headways, not future queues/full buses. Existing four observations reused; no new-date outcomes.',
    frozen_sha256={n:sha(w/n) for n in names})
save(w/'future_evaluation_plan.json',future)
save(w/'protocol-reference.json',{'path':str(ROOT/'PROTOCOL.md'),'sha256':sha(ROOT/'PROTOCOL.md'),'registered_before_model_run':True,'production_writes':False})
print('PREPARATION_EQUAL',len(checks[True]),'NUMERIC_FIXED',len(nums),'FUTURE_HASHES',len(names),'PROTECTED',count,flush=True)
