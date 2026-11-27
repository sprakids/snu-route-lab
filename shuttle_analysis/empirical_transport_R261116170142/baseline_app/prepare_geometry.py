"""Bounded public map extraction. Originals are preserved; output has provenance."""
import json,urllib.request,urllib.parse,urllib.error,hashlib,heapq,math
from pathlib import Path
from datetime import datetime,timezone
from road_geometry import meters,length,project,slice_path,Buildings

ROOT=Path(__file__).parent;DATA=ROOT/'data'

def map_extract(b,depth=0):
    u='https://api.openstreetmap.org/api/0.6/map.json?bbox='+','.join(map(str,b))
    try:
        with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SNU-Route-Lab/0.4 academic prototype'}),timeout=55) as r:return r.read(80000000)
    except urllib.error.HTTPError as e:
        reason=e.read(1000).decode(errors='replace')
        if e.code!=400 or 'many nodes' not in reason.lower() or depth>=3:raise
        x,y,z,w=b;mid=(x+z)/2 if z-x>w-y else (y+w)/2
        boxes=[[x,y,mid,w],[mid,y,z,w]] if z-x>w-y else [[x,y,z,mid],[x,mid,z,w]]
        found={}
        for bb in boxes:
            for e in json.loads(map_extract(bb,depth+1))['elements']:found[(e['type'],e['id'])]=e
        return json.dumps({'elements':list(found.values())},separators=(',',':')).encode()

def download_osm():
    # Overpass can be overloaded. The bounded OSM map API supplies the same
    # public source elements without a query-service dependency.
    all_elements={}
    boxes=[('campus_map_osm.json',[126.936,37.438,126.970,37.486]),
           ('north_map_osm.json',[126.921,37.478,126.970,37.499]),
           ('north2_map_osm.json',[126.921,37.499,126.970,37.518]),
           ('west_map_osm.json',[126.921,37.438,126.936,37.478])]
    for filename,b in boxes:
        p=DATA/filename
        if not p.exists():
            u='https://api.openstreetmap.org/api/0.6/map.json?bbox='+','.join(map(str,b))
            raw=map_extract(b)
            doc=json.loads(raw)
            if not doc.get('elements'):raise ValueError('Empty map extraction')
            p.write_bytes(raw)
            (DATA/(filename+'.source.json')).write_text(json.dumps({'url':u,'retrieved_at':datetime.now(timezone.utc).isoformat(),'sha256':hashlib.sha256(raw).hexdigest(),'source':'OpenStreetMap API','license':'ODbL 1.0'}),encoding='utf-8')
        doc=json.loads(p.read_text(encoding='utf-8'))
        for e in doc['elements']:all_elements[(e['type'],e['id'])]=e
        print('map_source',filename,len(doc['elements']),flush=True)
    merged={'elements':list(all_elements.values())}
    (DATA/'roads_osm.json').write_text(json.dumps(merged,separators=(',',':')),encoding='utf-8')
    campus=json.loads((DATA/'campus_map_osm.json').read_text(encoding='utf-8'))
    (DATA/'building_footprints_osm.json').write_text(json.dumps(campus,separators=(',',':')),encoding='utf-8')
    return
class DriveGraph:
    def __init__(self,payload):
        self.nodes={e['id']:[e['lat'],e['lon']] for e in payload['elements'] if e['type']=='node'};self.edges={};self.restrictions={}
        for e in payload['elements']:
            if e['type']=='relation' and e.get('tags',{}).get('type')=='restriction' and 'bus' not in e.get('tags',{}).get('except','').split(';'):
                m={v['role']:v['ref'] for v in e.get('members',[]) if v['type'] in ('way','node')}
                if all(k in m for k in ('from','via','to')):self.restrictions.setdefault((m['from'],m['via']),[]).append((m['to'],e['tags'].get('restriction','')))
            t=e.get('tags',{})
            if e['type']!='way' or t.get('highway') not in ('motorway','trunk','primary','secondary','tertiary','unclassified','residential','service','living_street','motorway_link','trunk_link','primary_link','secondary_link','tertiary_link'):continue
            allowed=t.get('bus',t.get('psv')) in ('yes','designated','permissive')
            if not allowed and any(t.get(k) in ('no','private') for k in ('access','vehicle','motor_vehicle')):continue
            if t.get('motor_vehicle')=='no' and not allowed:continue
            if any(k in t for k in ('access:conditional','vehicle:conditional','motor_vehicle:conditional')) and not allowed:continue
            oneway=t.get('oneway:bus',t.get('oneway','yes' if t.get('junction')=='roundabout' else 'no'))
            for a,b in zip(e['nodes'],e['nodes'][1:]):
                if a not in self.nodes or b not in self.nodes:continue
                d=meters(self.nodes[a],self.nodes[b])
                if oneway!='-1':self.edges.setdefault(a,[]).append((b,d,e['id']))
                if oneway not in ('yes','1','true'):self.edges.setdefault(b,[]).append((a,d,e['id']))
        self.points=[(n,self.nodes[n]) for n in self.edges]

    def nearest(self,p):return min(self.points,key=lambda x:meters(p,x[1]))

    def path(self,start,end):
        a,pa=self.nearest(start);b,pb=self.nearest(end)
        if max(meters(start,pa),meters(end,pb))>100:return None
        source=(a,0);cost={source:0};parents={};queue=[(0,source)]
        while queue:
            d,state=heapq.heappop(queue);node,prior=state
            if d!=cost.get(state):continue
            if node==b:
                chain=[state]
                while chain[-1]!=source:chain.append(parents[chain[-1]])
                poly=[self.nodes[x[0]] for x in reversed(chain)]
                return poly if len(poly)>1 else [pa,pb]
            for other,size,way in self.edges.get(node,[]):
                rules=self.restrictions.get((prior,node),[])
                if any((r.startswith('no_') and way==target) or (r.startswith('only_') and way!=target) for target,r in rules):continue
                v=(other,way);nd=d+size
                if nd<cost.get(v,math.inf):cost[v]=nd;parents[v]=state;heapq.heappush(queue,(nd,v))
        return None

def stop_offsets(poly,stops):
    """Global ordered matching avoids jumping to a later visit of the same road."""
    layers=[]
    for stop in stops:
        choices=[];offset=0
        for a,b in zip(poly,poly[1:]):
            h=project([stop['lat'],stop['lon']],[a,b])
            if h and h['offset_m']<=100:choices.append((h['offset_m'],offset+h['meters']))
            offset+=meters(a,b)
        selected=[]
        for error,at in sorted(choices):
            if all(abs(at-v[1])>=15 for v in selected):selected.append((error,at))
            if len(selected)>=24:break
        if not selected:raise ValueError('Official path does not cover stop '+str(stop['seq']))
        layers.append(sorted(selected,key=lambda x:x[1]))
    total=length(poly);costs=[(error/15)**2+at/300 for error,at in layers[0]];parents=[]
    for i,choices in enumerate(layers[1:],1):
        expected=float(stops[i].get('segment_m') or meters([stops[i-1]['lat'],stops[i-1]['lon']],[stops[i]['lat'],stops[i]['lon']]))
        next_cost=[];parent=[]
        for error,at in choices:
            possible=[(costs[k]+abs(at-before-expected)/max(50,expected*.25)+(error/15)**2,k)
                for k,(_,before) in enumerate(layers[i-1]) if at>=before and math.isfinite(costs[k])]
            score,k=min(possible,default=(math.inf,None));next_cost.append(score);parent.append(k)
        costs=next_cost;parents.append(parent)
    last=min(range(len(costs)),key=lambda k:costs[k]+(total-layers[-1][k][1])/300)
    if not math.isfinite(costs[last]):raise ValueError('Stop order is incompatible with official path')
    hits=[layers[-1][last][1]]
    for i in range(len(parents)-1,-1,-1):last=parents[i][last];hits.append(layers[i][last][1])
    return list(reversed(hits))

def fetch_official():
    import server
    key=server.Transit({'routes':[]}).key;network=json.loads((DATA/'network.json').read_text(encoding='utf-8'))
    cache={};report={'service':'15000193','available':False,'attempted_at':datetime.now(timezone.utc).isoformat()}
    for route in network['routes']:
        u='http://ws.bus.go.kr/api/rest/busRouteInfo/getRoutePath?'+urllib.parse.urlencode({'serviceKey':key,'busRouteId':route['id'],'resultType':'json'})
        try:
            raw=DATA/'raw'/('official_route_path_'+route['id']+'.json')
            if raw.exists():doc=json.loads(raw.read_text(encoding='utf-8'))
            else:
                with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SNU-Route-Lab/0.5'}),timeout=15) as r:doc=json.load(r)
                if str(doc.get('msgHeader',{}).get('headerCd'))=='0':raw.write_text(json.dumps(doc,ensure_ascii=False),encoding='utf-8')
            if str(doc.get('msgHeader',{}).get('headerCd'))!='0':raise ValueError('Provider did not return route geometry')
            rows=(doc.get('msgBody') or {}).get('itemList') or []
            if isinstance(rows,dict):rows=[rows]
            rows.sort(key=lambda x:int(x.get('no',0)))
            poly=[[float(v['gpsY']),float(v['gpsX'])] for v in rows]
            if len(poly)<len(route['stops']):raise ValueError('Incomplete route geometry')
            hits=stop_offsets(poly,route['stops'])
            segments=[]
            for a,b in zip(hits,hits[1:]):
                points=slice_path(poly,a,b);segments.append({'geometry':points,'meters':round(length(points),1)})
            cache[route['id']]={'source':'서울시 공식 노선정보조회 getRoutePath','segments':segments}
        except Exception as e:
            report.update(error=type(e).__name__,detail=str(e) if isinstance(e,ValueError) else None,http_status=getattr(e,'code',None));break
    if len(cache)==len(network['routes']):
        (DATA/'official_route_paths.json').write_text(json.dumps(cache,ensure_ascii=False,separators=(',',':')),encoding='utf-8');report['available']=True
    (DATA/'official_route_path_status.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('official route API',report)

def build():
    roads=DriveGraph(json.loads((DATA/'roads_osm.json').read_text(encoding='utf-8')))
    raw=json.loads((DATA/'building_footprints_osm.json').read_text(encoding='utf-8'))
    nodes={e['id']:e for e in raw['elements'] if e['type']=='node'};buildings=[]
    for e in raw['elements']:
        if e['type']!='way' or 'building' not in e.get('tags',{}) or e['nodes'][0]!=e['nodes'][-1]:continue
        poly=[[nodes[n]['lat'],nodes[n]['lon']] for n in e['nodes'] if n in nodes]
        if len(poly)<4:continue
        entrances=[{'point':[nodes[n]['lat'],nodes[n]['lon']],'source':'OSM entrance','id':n} for n in e['nodes'] if n in nodes and nodes[n].get('tags',{}).get('entrance') not in (None,'no') and nodes[n].get('tags',{}).get('access') not in ('no','private')]
        buildings.append({'id':e['id'],'name':e.get('tags',{}).get('name'),'polygon':poly,'entrances':entrances})
    footprints={'version':'osm-footprints-v1','buildings':buildings,'source':'OpenStreetMap contributors · ODbL 1.0'}
    (DATA/'building_access.json').write_text(json.dumps(footprints,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    barrier=Buildings(footprints)
    network=json.loads((DATA/'network.json').read_text(encoding='utf-8'))
    shuttle=json.loads((DATA/'shuttle_network.json').read_text(encoding='utf-8'))
    specs={};errors=[]
    for route in network['routes']:
        official=DATA/'official_route_paths.json'
        cached=json.loads(official.read_text(encoding='utf-8')).get(route['id']) if official.exists() else None
        if cached and len(cached['segments'])==len(route['stops'])-1:
            specs[route['id']]=cached;continue
        segments=[]
        for a,b in zip(route['stops'],route['stops'][1:]):
            poly=roads.path([a['lat'],a['lon']],[b['lat'],b['lon']])
            segments.append({'geometry':poly,'meters':round(length(poly),1)} if poly else None)
        specs[route['id']]={'source':'OSM 차도·정류소 경유 경로 · 서울시 상세 경로 API 승인 대기','segments':segments}
        errors.extend([route['id']+':'+str(i+1) for i,s in enumerate(segments) if not s])
        print('city_geometry',route['id'],sum(bool(x) for x in segments),len(segments),flush=True)
    for route in shuttle['routes']:
        anchors=route['anchors'];parts=[]
        for a,b in zip(anchors,anchors[1:]+anchors[:1]):
            poly=roads.path([a['lat'],a['lon']],[b['lat'],b['lon']]) if all('lat' in x and 'lon' in x for x in (a,b)) else None
            parts.append({'geometry':poly,'meters':round(length(poly),1)} if poly else None)
        stops=[a for a in anchors if 'lat' in a and (a['board_allowed'] or a['alight_allowed'])]
        seg=[]
        pairs=list(zip(stops,stops[1:]+stops[:1])) if route['loop'] else list(zip(stops,stops[1:]))
        for a,b in pairs:
            path=[];i=a['index'];valid=True
            while i!=b['index']:
                p=parts[i]
                if not p:valid=False;break
                if path and meters(path[-1],p['geometry'][0])>3:valid=False;break
                path.extend(p['geometry'] if not path else p['geometry'][1:]);i=(i+1)%len(anchors)
            seg.append({'geometry':path,'meters':round(length(path),1)} if path and valid else None)
        if route['loop']:seg=(seg+seg)[:len(stops)*2-1]
        specs['shuttle-'+route['id']]={'source':'OSM 차량 통행 도로·학교 정류장 순서 · 현장 검증 전','segments':seg,'anchor_segments':parts}
        print('shuttle_geometry',route['id'],sum(bool(x) for x in seg),len(seg),flush=True)
    digest=hashlib.sha256(json.dumps(specs,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:12]
    out={'version':'road-v1-'+digest,'routes':specs,'missing_segments':errors,'generated_at':datetime.now(timezone.utc).isoformat()}
    (DATA/'road_geometry.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    if any(r['id']=='41843' for r in shuttle['routes']):
        # Retain the verified Seoul shared bus corridor at the main gate.
        from prepare_town_shuttle import build as town_geometry
        town_geometry()
        if any(r['id']=='41842' for r in shuttle['routes']):
            from prepare_all_shuttles import build as all_student_shuttles
            all_student_shuttles()

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--fetch-official',action='store_true');args=p.parse_args()
    if args.fetch_official:fetch_official()
    download_osm();build()
