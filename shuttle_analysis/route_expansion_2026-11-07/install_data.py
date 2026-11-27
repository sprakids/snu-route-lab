"""Install verified additions; preserve the existing five route and shuttle records."""
from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parent
APP=ROOT.parent/'app'
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
network=load(APP/'data/network.json');additions=load(ROOT/'prepared_routes.json')['routes'];paths=load(ROOT/'prepared_paths.json')
for route in additions:
    if route['id'] not in {r['id'] for r in network['routes']}:network['routes'].append(route)
assert len(network['routes'])==8
dump(APP/'data/network.json',network)
roads=load(APP/'data/road_geometry.json');roads['routes'].update(paths)
roads['version']='road-v2-'+hashlib.sha256(json.dumps(roads['routes'],sort_keys=True,separators=(',',':')).encode()).hexdigest()[:12]
dump(APP/'data/road_geometry.json',roads)
official=load(APP/'data/official_route_paths.json');official.update(paths);dump(APP/'data/official_route_paths.json',official)
dump(ROOT.parent/'collector/route_stops.json',{r['id']:r['stops'] for r in network['routes']})
print(json.dumps({'routes':len(network['routes']),'geometry_version':roads['version'],'added':{r['id']:r['name'] for r in additions}}))
