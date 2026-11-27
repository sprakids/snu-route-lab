"""Measure walking legs used in integrated runs and wholly covered by the campus polygon."""
import argparse
import csv
import gzip
import json
import math
from pathlib import Path

from shapely.geometry import LineString, Point, shape
from shapely.ops import unary_union
from shapely.prepared import prep

from terrain import HERE, elevation, horizontal, slope_profile


def load(path):
    with (gzip.open if path.suffix=='.gz' else open)(path,'rt',encoding='utf8') as stream:
        return json.load(stream)


def boundary(obj):
    if obj['type']=='FeatureCollection':
        return unary_union([boundary(f) for f in obj['features']])
    if obj['type']=='Feature':
        return boundary(obj['geometry'])
    return shape(obj)


def compute(file):
    area=boundary(load(file))
    assert area.is_valid and area.geom_type in ('Polygon','MultiPolygon') and area.covers(Point(126.95259,37.45016))
    campus=prep(area)
    common=load(HERE/'viewer-data'/'common.json.gz')
    metrics=load(HERE/'walking_surface.json.gz')
    locations=[([r['lat'],r['lon']],r['name']) for r in common['buildings']+common['nodes']]
    names={'dorm_ug':'학부 기숙사','dorm_grad':'대학원 기숙사','daehak':'대학동','snu':'서울대입구역',
           'nak':'낙성대역','gwanaksan_4411':'관악산(서울대)역'}
    locations = [(p,names[k]) for k,p in common['destinations'].items()]+locations
    def nearest(p):
        distance,label=min(((horizontal(p,q),s) for q,s in locations),key=lambda t:t[0])
        return label if distance<2 else f'{label} 인근({distance:.0f}m)'
    cases=list((HERE/'runs').glob('*/attempt-*/result.json'))
    assert len(cases)==10
    uses=set().union(*(load(c)['walk_paths_used'] for c in cases))
    assert all(str(i) in metrics for i in uses)
    rows=[]
    for pid in sorted(uses):
        m=metrics[str(pid)]
        if m['flat']<.01:
            continue
        pts=common['paths'][pid]
        if not campus.covers(LineString([(lon,lat) for lat,lon in pts])):
            continue
        z0=elevation(*pts[0])
        z1=elevation(*pts[-1])
        assert math.isclose(z1-z0,m['rise']-m['fall'],abs_tol=.001)
        rows.append(dict(path=pid,start=nearest(pts[0]),end=nearest(pts[-1]),start_lat=pts[0][0],start_lon=pts[0][1],
                         end_lat=pts[-1][0],end_lon=pts[-1][1],start_m=z0,end_m=z1,net_m=z1-z0,
                         cumulative_up_m=m['rise'],cumulative_down_m=m['fall'],flat_m=m['flat'],surface_m=m['surface'],
                         surface_extra_m=m['surface']-m['flat']))
    assert rows
    fields=[('net_up','net_m',1),('net_down','net_m',-1),('cumulative_up','cumulative_up_m',1),
            ('cumulative_down','cumulative_down_m',1),('surface_extra','surface_extra_m',1)]
    winners={}
    for key,field,sign in fields:
        extreme=max(rows,key=lambda r:sign*r[field])
        path=common['paths'][extreme['path']]
        winners[key]=dict(**extreme,
            samples={str(s):dict(zip(('planar','surface','rise','fall'),slope_profile(path,s))) for s in (15,25,50)})
    with (HERE/'교내_사용된_도보구간.csv').open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary=dict(used_paths=len(uses),on_campus_nonzero_paths=len(rows),cases=len(cases),boundary=file.name,
                 scope='walking legs used in integrated weekday runs; whole polyline within campus polygon',winners=winners)
    (HERE/'campus_walks.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf8')
    for key,r in winners.items():
        print(key,r['start'],r['end'],round(r['net_m'],1),round(r['cumulative_up_m'],1),round(r['cumulative_down_m'],1))


if __name__=='__main__':
    args=argparse.ArgumentParser(description=__doc__)
    args.add_argument('polygon',type=Path,help='WGS84 GeoJSON of the campus grounds')
    compute(args.parse_args().polygon)
