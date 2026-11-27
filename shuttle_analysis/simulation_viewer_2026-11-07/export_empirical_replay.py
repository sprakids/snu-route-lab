"""Add derived UI metadata and copy the independently verified replay only."""
from pathlib import Path
import gzip,json,shutil,hashlib
import empirical_speed_replay as model


def main():
    check=json.loads((model.WORK/'independent_verification.json').read_text(encoding='utf-8'))
    assert check['status']=='PASS' and check['simulation_runs']==10
    identity=json.loads((model.WORK/'release_identity.json').read_text(encoding='utf-8'))
    bundle=json.loads(gzip.decompress((model.WORK/'prepared.json.gz').read_bytes()))
    src=model.OUT;public=model.ROOT/'public'
    common=json.loads((src/'common.json').read_text(encoding='utf-8'))
    common['empirical_speed_reference']['release_name']=identity['name']
    common['city_route_stops']={rid:[{k:s.get(k) for k in ('id','seq','name','ars','lat','lon')} for s in route['stops']]
                               for rid,route in bundle['prepared']['routes'].items() if not rid.startswith('shuttle')}
    raw=json.dumps(common,ensure_ascii=False,separators=(',',':')).encode()
    (src/'common.json').write_bytes(raw);(src/'common.json.gz').write_bytes(gzip.compress(raw,mtime=0))
    target=public/'data/capacity_v6';target.mkdir(exist_ok=True)
    files=[]
    for f in src.glob('*.json*'):
        dest=(public/'data/half_hour_v1'/('capacity_v6.json.gz' if f.suffix=='.gz' else 'capacity_v6.json')) if f.name.startswith('half_hour.') else target/f.name
        if dest.exists():assert dest.read_bytes()==f.read_bytes(),'Existing replay asset differs: '+str(dest)
        shutil.copy2(f,dest);files.append({'path':dest.relative_to(public).as_posix(),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
    (model.WORK/'export_verification.json').write_text(json.dumps({'status':'PASS','release':identity,'files':files,'ui_metadata_only_added':'city_route_stops'},indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'PASS','release_name':identity['name'],'files':len(files)}))


if __name__=='__main__':main()
