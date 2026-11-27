"""Measure reachable height changes and 100 m walking grades on mapped public ways.

Requires pyproj, shapely, pyshp, networkx and Pillow. Use the two archived inputs
next to this script. Terrain uses the same pixel-center convention as terrain.py.
"""
from collections import Counter
from functools import lru_cache
import gzip
import hashlib
import heapq
import io
import json
import math
from pathlib import Path
import subprocess
import zipfile
from urllib.request import urlopen

import networkx as nx
from PIL import Image
from pyproj import CRS, Transformer
import shapefile
from shapely.geometry import LineString, Point, box, mapping, shape
from shapely.ops import linemerge
from shapely import transform
from shapely.prepared import prep

HERE = Path(__file__).resolve().parent
ARCHIVE = HERE/'seoul-UQ155-202609.zip'
OSM = HERE/'osm-map.json.gz'
METRIC = 5186
forward = Transformer.from_crs(4326, METRIC, always_xy=True).transform
inverse = Transformer.from_crs(METRIC, 4326, always_xy=True).transform
ALLOWED = set('footway steps pedestrian residential living_street path service track unclassified primary secondary tertiary primary_link secondary_link tertiary_link road'.split())
DENIED = {'no','private','permit','customers','use_sidepath','agricultural','forestry'}
EXPLICIT = {'yes','designated','permissive','official'}
PAVED = {'paved','asphalt','concrete','paving_stones','concrete:plates','sett','compacted'}
GRIDS = set()


def save(name, value):
    (HERE/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')


def boundaries(data):
    with zipfile.ZipFile(ARCHIVE) as z:
        streams = {p.rsplit('.',1)[-1]:io.BytesIO(z.read(p)) for p in z.namelist() if p.endswith(('.dbf','.shx','.shp'))}
        src_crs = CRS.from_wkt(z.read(next(p for p in z.namelist() if p.endswith('.prj'))).decode())
        records = [r for r in shapefile.Reader(**streams,encoding='cp949').iterShapeRecords() if r.record['DGM_NM']=='서울대학교']
        assert len(records)==1 and src_crs.to_epsg()==5174
        r = records[0]
        raw = shape(r.shape.__geo_interface__)
        assert abs(raw.area-r.record['SHAPE_AREA'])<1
        city = transform(raw,Transformer.from_crs(src_crs,METRIC,always_xy=True).transform,interleaved=False)
    relation=data['relation',11917142]
    rings=[]
    assert all(m['role']=='outer' for m in relation['members'])
    for m in relation['members']:
        rings.append(LineString([point_xy(data['node',n]) for n in data['way',m['ref']]['nodes']]))
    ring=linemerge(rings)
    assert ring.is_ring
    from shapely.geometry import Polygon
    osm=Polygon(ring)
    assert city.is_valid and osm.is_valid
    return city,osm,dict(feature_id=r.record['PRESENT_SN'],native_area_m2=raw.area,source_crs=src_crs.to_epsg(),
                         osm_relation=relation['id'],osm_version=relation['version'],osm_area_m2=osm.area,
                         intersection_m2=city.intersection(osm).area)


def point_xy(n):
    return forward(n['lon'],n['lat'])


@lru_cache(maxsize=40)
def tile(x,y):
    name=f'{x}-{y}.png'
    path=HERE.parent/'terrain'/name
    if not path.exists():
        path=HERE/'terrain'/name
        if not path.exists():
            path.parent.mkdir(exist_ok=True)
            url=f'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/14/{x}/{y}.png'
            with urlopen(url,timeout=30) as response:
                raw=response.read()
            with Image.open(io.BytesIO(raw)) as image:
                assert image.size==(256,256)
            path.write_bytes(raw)
    GRIDS.add(path)
    with Image.open(path) as image:
        return image.convert('RGB')


@lru_cache(maxsize=180000)
def elevation(x,y):
    lon,lat=inverse(x,y)
    size=2**14*256
    px=(lon+180)/360*size-.5
    py=(1-math.asinh(math.tan(math.radians(lat)))/math.pi)*size/2-.5
    ix,iy=math.floor(px),math.floor(py)
    z=0.
    for u in [ix,ix+1]:
        for v in [iy,iy+1]:
            r,g,b=tile(u//256,v//256).getpixel((u%256,v%256))
            z+=(1-abs(u-px))*(1-abs(v-py))*(256*r+g+b/256-32768)
    return z


def outdoor(t):
    access=t.get('foot',t.get('access'))
    h=t.get('highway')
    return (access not in DENIED and (h in ALLOWED or (h in {'cycleway','trunk','trunk_link'} and access in EXPLICIT))
            and t.get('area')!='yes' and t.get('indoor','no')=='no' and t.get('tunnel')!='building_passage_indoor'
            and not (t.get('route')=='ferry' or 'construction' in (h,)))


def ordinary(t):
    return (not any(k in t for k in ('sac_scale','trail_visibility')) and t['highway']!='track'
            and (t['highway']!='path' or t.get('surface') in PAVED))


def graph(data,region,core,step):
    inside=prep(region)
    graph=nx.DiGraph()
    way_tags={}
    for (kind,wid),w in data.items():
        t=w.get('tags',{})
        if kind!='way' or not outdoor(t) or (core and not ordinary(t)):
            continue
        way_tags[wid]=t
        direction=t.get('oneway:foot','no')
        assert direction in ('no','yes','1','-1')
        for u,v in zip(w['nodes'],w['nodes'][1:]):
            nodes=[data['node',key] for key in (u,v)]
            if any(n.get('tags',{}).get('foot',n.get('tags',{}).get('access')) in DENIED or n.get('tags',{}).get('barrier') in ('wall','fence','block') for n in nodes):
                continue
            a,b=map(point_xy,nodes)
            if math.dist(a,b)<1e-6:
                continue
            edge=LineString([a,b])
            if not inside.intersects(edge):
                continue
            clipped=edge if inside.covers(edge) else region.intersection(edge)
            parts=clipped.geoms if hasattr(clipped,'geoms') else [clipped]
            for part in parts:
                if part.geom_type!='LineString' or part.length<.01:
                    continue
                start,end=part.coords[0],part.coords[-1]
                if math.dist(start,a)>math.dist(end,a):
                    start,end=end,start
                length=math.dist(start,end)
                count=math.ceil(length/step)
                chain=[]
                for i in range(count+1):
                    f=i/count
                    xy=(start[0]+f*(end[0]-start[0]),start[1]+f*(end[1]-start[1]))
                    # Connect only at original shared OSM nodes or on the same original edge.
                    key=u if math.dist(xy,a)<.001 else v if math.dist(xy,b)<.001 else (min(u,v),max(u,v),round(xy[0],3),round(xy[1],3))
                    if key not in graph:
                        graph.add_node(key,xy=xy,z=elevation(*xy))
                    chain.append(key)
                for l,r in zip(chain,chain[1:]):
                    if direction!='-1':
                        graph.add_edge(l,r,length=length/count,way=wid)
                    if direction not in ('yes','1'):
                        graph.add_edge(r,l,length=length/count,way=wid)
    return graph,way_tags


def landmarks(data):
    out=[]
    for (kind,_),w in data.items():
        t=w.get('tags',{})
        if kind!='way' or not t.get('name') or not t.get('building'):
            continue
        points=[point_xy(data['node',n]) for n in w['nodes']]
        if len(points)>=2:
            ref=t.get('ref') or t.get('addr:housename')
            out.append((t['name']+(f' ({ref})' if ref else ''),LineString(points)))
    return out


def describe(xy,land):
    point=Point(xy)
    dist,name=min((g.distance(point),name) for name,g in land)
    lon,lat=inverse(*xy)
    return dict(lat=lat,lon=lon,elevation_m=elevation(*xy),nearest_named_building=name,distance_to_outline_m=dist)


def gradients(g):
    # Test exactly 100 m shortest walking distance from every sampled vertex,
    # interpolating the last edge. The reverse approach must not give a shortcut.
    keys=list(g)
    index={k:i for i,k in enumerate(keys)}
    xy=[g.nodes[k]['xy'] for k in keys]
    z=[g.nodes[k]['z'] for k in keys]
    adj=[[(index[v],e['length'],g.has_edge(v,k)) for v,e in g[k].items()] for k in keys]
    best=[(-math.inf,None),(-math.inf,None)]
    checked=0
    for s in range(len(keys)):
        d={s:0.}
        heap=[(0.,s)]
        boundary=[]
        while heap:
            length,u=heapq.heappop(heap)
            if length!=d[u]:
                continue
            for v,edge,reverse in adj[u]:
                candidate=length+edge
                if candidate>=100:
                    boundary.append((u,v,100-length,edge,reverse))
                elif candidate<d.get(v,math.inf):
                    d[v]=candidate
                    heapq.heappush(heap,(candidate,v))
        for u,v,along,edge,reverse in boundary:
            if reverse and d.get(v,math.inf)+edge-along<100-1e-7:
                continue
            f=along/edge
            end=tuple(a+f*(b-a) for a,b in zip(xy[u],xy[v]))
            dz=elevation(*end)-z[s]
            checked+=1
            for i,score in enumerate((dz,-dz)):
                if score>best[i][0]:
                    best[i]=(score,(keys[s],keys[u],keys[v],end,along))
    return checked,[row[1] for row in best]


def analysis(g,tags,land):
    components=sorted(nx.weakly_connected_components(g),key=len,reverse=True)
    strong=list(nx.strongly_connected_components(g))
    # Account for any signed foot direction. Compare reachable component extrema.
    dag=nx.condensation(g,strong)
    limits=[(min(c,key=lambda k:g.nodes[k]['z']),max(c,key=lambda k:g.nodes[k]['z'])) for c in strong]
    best=[(-math.inf,None),(-math.inf,None)]
    for c in reversed(list(nx.topological_sort(dag))):
        low,high=limits[c]
        low_end,high_end=low,high
        for v in dag[c]:
            low_end=min((low_end,limits[v][0]),key=lambda k:g.nodes[k]['z'])
            high_end=max((high_end,limits[v][1]),key=lambda k:g.nodes[k]['z'])
        for i,(u,v) in enumerate(((low,high_end),(high,low_end))):
            dz=abs(g.nodes[v]['z']-g.nodes[u]['z'])
            if dz>best[i][0]:
                best[i]=(dz,(u,v))
        limits[c]=(low_end,high_end)
    checked,steep=gradients(g)
    traces={}
    def report(label,src,dst,edge=None,chain=None):
        if chain is None:
            chain=nx.shortest_path(g,src,dst,weight='length')
        coords=[g.nodes[k]['xy'] for k in chain]
        ways=[g[u][v]['way'] for u,v in zip(chain,chain[1:])]
        if edge:
            next_key,end,along=edge
            coords.append(end)
            ways.append(g[dst][next_key]['way'])
        length=sum(math.dist(a,b) for a,b in zip(coords,coords[1:]))
        dz=elevation(*coords[-1])-elevation(*coords[0])
        heights=[elevation(*p) for p in coords]
        ascent=sum(max(0,b-a) for a,b in zip(heights,heights[1:]))
        descent=sum(max(0,a-b) for a,b in zip(heights,heights[1:]))
        assert math.isclose(ascent-descent,dz,abs_tol=.001)
        if edge:
            assert math.isclose(length,100,abs_tol=.001)
        traces[label]=[list(inverse(*p)) for p in coords]
        return dict(start=describe(coords[0],land),end=describe(coords[-1],land),net_m=dz,
                    horizontal_route_m=length,grade_percent=100*dz/length,cumulative_up_m=ascent,cumulative_down_m=descent,
                    osm_ways={str(w):{k:tags[w][k] for k in ('name','highway','sac_scale','surface','bridge','tunnel','layer') if k in tags[w]} for w in dict.fromkeys(ways)})
    results={}
    for name,(_,pair) in zip(('net_up','net_down'),best):
        results[name]=report(name,*pair)
    for name,(s,u,v,end,along) in zip(('grade_up','grade_down'),steep):
        results[name]=report(name,s,u,(v,end,along))
    # Each fully reversible witness is also a valid 100 m window in reverse,
    # including the direction starting at the interpolated endpoint.
    if all(g.has_edge(v,u) for u,v in g.edges):
        src,dst=sorted(('grade_up','grade_down'),key=lambda k:abs(results[k]['net_m']),reverse=True)
        r=results[src]
        results[dst]={**r,'start':r['end'],'end':r['start'],'net_m':-r['net_m'],'grade_percent':-r['grade_percent'],
                      'cumulative_up_m':r['cumulative_down_m'],'cumulative_down_m':r['cumulative_up_m']}
        traces[dst]=traces[src][::-1]
    keys=list(g)
    idx={k:i for i,k in enumerate(keys)}
    inp=dict(z=[g.nodes[k]['z'] for k in keys],adj=[[(idx[v],e['length']) for v,e in g[k].items()] for k in keys])
    out=json.loads(subprocess.run(['node',str(HERE/'cumulative.cjs')],input=json.dumps(inp),
                                  capture_output=True,text=True,check=True).stdout)
    for name,row,field in zip(('cumulative_up','cumulative_down'),out['best'],('cumulative_up_m','cumulative_down_m')):
        chain=[keys[i] for i in row['chain']]
        r=results[name]=report(name,chain[0],chain[-1],chain=chain)
        assert math.isclose(r['horizontal_route_m'],nx.shortest_path_length(g,chain[0],chain[-1],weight='length'),abs_tol=.001)
        assert math.isclose(row['meters'],r[field],abs_tol=.001)
    results['reachable_ordered_pairs']=out['pairs']
    for field,func in [('minimum',min),('maximum',max)]:
        k=func(g,key=lambda k:g.nodes[k]['z'])
        results[field]=describe(g.nodes[k]['xy'],land)
    edges=g.to_undirected(as_view=True).edges(data=True)
    lengths=Counter()
    for _,_,e in edges:
        lengths[tags[e['way']]['highway']]+=e['length']
    results.update(nodes=len(g),osm_ways=len({e['way'] for _,_,e in edges}),components=len(components),
                   largest_component_nodes=len(components[0]),strong_components=len(strong),
                   network_m=sum(lengths.values()),way_length_m=lengths,exact_100m_windows=checked)
    return results,traces


def main():
    with gzip.open(OSM,'rt',encoding='utf8') as f:
        src=json.load(f)
    data={(e['type'],e['id']):e for e in src['elements']}
    city,osm,info=boundaries(data)
    bbox=src['bounds']
    coverage=box(bbox['minlon'],bbox['minlat'],bbox['maxlon'],bbox['maxlat'])
    city_wgs=transform(city,inverse,interleaved=False)
    assert coverage.covers(city_wgs)
    save('seoul-school-boundary.geojson',dict(type='Feature',properties=dict(source=info['feature_id'],source_crs=5174,unit='WGS84 lon/lat',dataset='서울특별시 OA-20961, 2026-09'),geometry=mapping(city_wgs)))
    land=landmarks(data)
    features=[]
    cases={}
    for name,region,core in [('school',city,False),('everyday',city.intersection(osm),True)]:
        g,tags=graph(data,region,core,5)
        cases[name],paths=analysis(g,tags,land)
        for metric,coords in paths.items():
            features.append(dict(type='Feature',properties=dict(scope=name,metric=metric),
                                 geometry=dict(type='LineString',coordinates=coords)))
        print(name,len(g),[(m,round(cases[name][m]['net_m'],1)) for m in paths],flush=True)
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    info.update(snu_brochure_area_m2=4109000,osm_bbox=bbox,network_source='https://api.openstreetmap.org/api/0.6/map.json?bbox=126.9465,37.4430,126.9711,37.4700',
                seoul_source='https://data.seoul.go.kr/dataList/OA-20961/F/1/datasetView.do',
                terrain_source='https://registry.opendata.aws/terrain-tiles/',horizontal_crs=METRIC,
                point_spacing_max_m=5,grade_baseline_m=100,sha256={p.name:digest(p) for p in [ARCHIVE,OSM,*sorted(GRIDS)]})
    save('result.json',dict(sources=info,cases=cases))
    save('extremes.geojson',dict(type='FeatureCollection',features=features))


if __name__=='__main__':
    main()
