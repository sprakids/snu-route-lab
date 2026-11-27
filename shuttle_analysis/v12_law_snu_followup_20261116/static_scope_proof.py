from pathlib import Path
import ast,hashlib,json
ROOT=Path(__file__).resolve().parent;w=Path(json.loads((ROOT/'candidate.json').read_bytes())['path']);p=w.parent/'261116122336'
def read(x):return json.loads(x.read_bytes())
def sha(x):return hashlib.sha256(x.read_bytes()).hexdigest()
start=read(next((w/'runs').glob('*/attempt_01/started.json')))
old=read(p/'config.json');new=read(w/'config.json');numeric={k:v for k,v in old.items() if type(v) in (int,float)}
assert all(new[k]==v for k,v in numeric.items())
changed=[n for n in start['code_sha256'] if not (p/n).exists() or sha(p/n)!=sha(w/n)]
assert set(changed)=={'prepare.py','behavioral_policy.py','direct_restoration.py','run_case.py'},changed
for n in ['engine.py','physics.py','operations.py','capacity.py','hazard.py','preferences.py','perception.py','time_profiles.py','empirical_v12.py','fares.py']:
    assert sha(w/n)==sha(p/n),n
prep=read(w/'preparation-catalog-audit.json');assert prep['status']=='PASS_PREPARATION_ONLY'
manifest=read(w/'repair_manifest.json')
for n,h in manifest['frozen_payloads'].items():assert sha(w/n)==sha(p/n)==h,n
result={'status':'PASS_STATIC_SCOPE','runtime_modules':18,'changed_runtime_modules':changed,
    'existing_numeric_parameters_unchanged':numeric,'same_frozen_payloads':len(manifest['frozen_payloads']),
    'preparation_unchanged_domains':prep['unchanged_domains'],'new_origin_options':prep['added_origin_options'],
    'restored_count':prep['enabled']['catalog_report']['restored_count'],'production_writes':False}
out=w/'static-scope-proof.json';assert not out.exists();out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('STATIC_SCOPE_PROOF_PASS',changed,len(numeric),flush=True)
