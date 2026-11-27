"""Check source coverage, witness paths, and sensitivity to finer DEM sampling."""
import gzip
import hashlib
import json
import math
from shapely.geometry import LineString
from survey import HERE, OSM, boundaries, elevation, forward, graph, gradients, save

result=json.loads((HERE/'result.json').read_text(encoding='utf8'))
with gzip.open(OSM,'rt',encoding='utf8') as f:
    data={(e['type'],e['id']):e for e in json.load(f)['elements']}
city,campus,_=boundaries(data)
features=json.loads((HERE/'extremes.geojson').read_text(encoding='utf8'))['features']
checks={}
for scope,region,core in [('school',city,False),('everyday',city.intersection(campus),True)]:
    baseline=result['cases'][scope]
    for feature in features:
        props=feature['properties']
        if props['scope']!=scope:
            continue
        points=[forward(*q) for q in feature['geometry']['coordinates']]
        line=LineString(points)
        assert region.buffer(.01).covers(line)
        row=baseline[props['metric']]
        assert abs(line.length-row['horizontal_route_m'])<.01
        assert abs(elevation(*points[-1])-elevation(*points[0])-row['net_m'])<.01
    g,_=graph(data,region,core,2.5)
    windows,ends=gradients(g)
    grades=[elevation(*end)-g.nodes[s]['z'] for s,u,v,end,along in ends]
    assert all(g.has_edge(v,u) for u,v in g.edges)
    max_grade=max(map(abs,grades))
    max_range=max(g.nodes[k]['z'] for k in g)-min(g.nodes[k]['z'] for k in g)
    checks[scope]=dict(sample_step_m=2.5,windows=windows,max_absolute_grade_pct=max_grade,
                       difference_vs_5m_pct_points=max_grade-baseline['grade_up']['grade_percent'],
                       full_height_range_m=max_range,verified_witnesses=sum(f['properties']['scope']==scope for f in features))
checks['result_sha256']=hashlib.sha256((HERE/'result.json').read_bytes()).hexdigest()
save('verification.json',checks)
print(json.dumps(checks))
