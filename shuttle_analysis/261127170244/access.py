"""Connect archived initial walks to the two engineering stops via the project's OSM graph."""
import gzip
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(ROOT/'app'))
from routing import WalkingGraph, distance
sys.path.insert(0,str(ROOT/'261124110718'))
from grade_demand import segment


def read(path):
    with (gzip.open(path,'rt',encoding='utf8') if path.suffix=='.gz' else path.open(encoding='utf8')) as f:
        return json.load(f)


def main():
    data=ROOT/'app/data'
    graph=WalkingGraph(read(data/'walking_osm.json'),read(data/'building_access.json'))
    c=read(ROOT/'261125170855/viewer-data/common.json.gz')
    targets={s['stop_id']:(s['lat'],s['lon']) for s in c['nodes'] if s.get('stop_id') in ('120000173','120000174')}
    walks=read(ROOT/'261124110718/choice_distance.json.gz')
    paths={}; options={}; cache={}
    for pid in sorted(map(int,walks)):
        old=c['paths'][pid]
        for stop,coordinate in targets.items():
            if distance(old[0],coordinate)>805:continue
            prefix=0.
            for i,point in enumerate(old):
                if i:prefix+=distance(old[i-1],point)
                if prefix>120:break
                endpoint=graph.endpoint(point)
                if not endpoint or distance(endpoint[2],point)>.15:continue
                key=tuple(point),stop
                if key not in cache:cache[key]=graph.walk(point,coordinate)
                route=cache[key]
                if not route or distance(route['geometry'][-1],coordinate)>.15:continue
                if prefix+route['meters']>805:break
                geom=[*old[:i],point,*route['geometry'][1:-1],list(coordinate)]
                legs=[segment(tuple(a),tuple(b)) for a,b in zip(geom,geom[1:])]
                meters=sum(x for x,_ in legs)
                if 0<meters<=800:
                    shape=tuple(map(tuple,geom))
                    if shape not in paths:
                        paths[shape]=dict(polyline=geom,meters=meters,felt=sum(x for _,x in legs))
                    options[f'{pid}|{stop}']=shape
                break
    idx={shape:i for i,shape in enumerate(paths)}
    out=dict(paths=list(paths.values()),options={k:idx[v] for k,v in options.items()})
    (HERE/'access_paths.json').write_text(json.dumps(out,separators=(',',':')),encoding='utf8')
    print(len(paths),'geometries;',len(options),'connections',flush=True)


if __name__=='__main__':main()
