"""Package frozen R inputs privately; never modify the experiment or public feed."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import gzip, hashlib, json

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'empirical_transport_R261116170142'
DEST=ROOT/'app/shadow_transport'
DEST.mkdir(exist_ok=True)
names=['parent_transport','transport_v2','empirical_transport','candidate_runtime','recent_history','review_runtime']
manifest={'source_model':'R261116170142','shadow_model':'R'+datetime.now(timezone(timedelta(hours=9))).strftime('%y%m%d%H%M%S'),'operating_model':'V11','automatic_promotion':False,'sources':{}}
if (DEST/'manifest.json').exists():manifest['shadow_model']=json.loads((DEST/'manifest.json').read_text(encoding='utf-8'))['shadow_model']
for name in names:
    raw=(SOURCE/(name+'.py')).read_bytes();text=raw.decode('utf-8')
    for module in names:text=text.replace('from '+module+' import','from .'+module+' import')
    if name=='candidate_runtime':
        text=text.replace('network_sha256, patch_gate=True):','network_sha256, patch_gate=False):')
        text=text.replace("    if network_sha256 != profile.data['network_sha256']:","    if patch_gate:raise ValueError('Global gate replacement is forbidden in the paired runtime')\n    if network_sha256 != profile.data['network_sha256']:")
    if name=='review_runtime':
        text=text.replace('import json','import json, gzip')
        text=text.replace("json.loads((ROOT/'artifacts/profile.json').read_text(encoding='utf-8'))","json.loads(gzip.decompress((ROOT/'candidate.json.gz').read_bytes()))")
        text=text.replace("json.loads((ROOT.parent/'empirical_transport_261116162001/artifacts/profile.json').read_text(encoding='utf-8'))","json.loads(gzip.decompress((ROOT/'parent.json.gz').read_bytes()))")
        text=text.replace("ROOT/'artifacts/final_component_policy.json'","ROOT/'policy.json'")
        text=text.replace('    return install_raw_candidate(planner, model, enabled, network_sha256)',
            '    from .candidate_runtime import common_gate_adapter\n    from gate_service import add_common_gate\n    undo=install_raw_candidate(planner, model, enabled, network_sha256, patch_gate=False)\n    planner.common_gate_service=common_gate_adapter(add_common_gate,model,enabled)\n    return undo')
    (DEST/(name+'.py')).write_text(text,encoding='utf-8')
    manifest['sources'][name]=hashlib.sha256(raw).hexdigest()
    manifest.setdefault('packaged_sources',{})[name]=hashlib.sha256((DEST/(name+'.py')).read_bytes()).hexdigest()
(DEST/'__init__.py').write_text('"""Private, opt-in shadow components. Never an active queue feed."""\n',encoding='utf-8')
for label,path in [('candidate',SOURCE/'artifacts/profile.json'),('parent',ROOT/'empirical_transport_261116162001/artifacts/profile.json')]:
    raw=path.read_bytes();compressed=gzip.compress(raw,compresslevel=9,mtime=0)
    (DEST/(label+'.json.gz')).write_bytes(compressed)
    manifest[label]={'sha256':hashlib.sha256(raw).hexdigest(),'compressed_bytes':len(compressed)}
(DEST/'policy.json').write_bytes((SOURCE/'artifacts/final_component_policy.json').read_bytes())
(DEST/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in manifest.items() if k!='sources'}))
