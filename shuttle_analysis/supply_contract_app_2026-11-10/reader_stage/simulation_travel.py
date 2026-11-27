"""Adapt frozen v5 inputs only to identical directed stops and road segments."""
import hashlib,json
from pathlib import Path
from simulation_kernel import find_stop_indices,ride_seconds,city_segment_seconds,first_boardable

ROOT=Path(__file__).parent

class SimulationTravel:
    def __init__(self,geometry,path=None):
        raw=(Path(path) if path else ROOT/'data/simulation_time_inputs.json').read_bytes()
        self.data=json.loads(raw);self.sha256=hashlib.sha256(raw).hexdigest()
        self.geometry=geometry;self.cache={}
        self.model_id='v5-'+self.data['scenario_revision']

    def mapping(self,route):
        key=(route['id'],tuple((str(s['id']),str(s.get('seq'))) for s in route['stops']))
        if key in self.cache:return self.cache[key]
        source=self.data['routes'].get(route['id']);parts=self.geometry.routes.get(route['id'],{}).get('segments',[]);out={}
        if source:
            for k,(a,b) in enumerate(zip(route['stops'],route['stops'][1:])):
                if k>=len(parts) or not parts[k]:continue
                matches=find_stop_indices(source,a['id'],a.get('seq'))
                for index in matches:
                    if index+1>=len(source['stops']):continue
                    target=source['stops'][index+1]
                    if str(target['id'])!=str(b['id']) or str(target['source_seq'])!=str(b.get('seq')):continue
                    segment=source['segments'][index]
                    if abs(segment['meters']-parts[k]['meters'])>max(3.,segment['meters']*.01):continue
                    out[k]=(index,segment);break
        self.cache[key]=out;return out

    def segment(self,route,index):return self.mapping(route).get(index,(None,None))[1]

    def leg_seconds(self,route,i,j):
        mapping=self.mapping(route)
        if not 0<=i<j<len(route['stops']) or any(k not in mapping for k in range(i,j)):return None
        indexes=[mapping[k][0] for k in range(i,j)]
        if indexes!=list(range(indexes[0],indexes[0]+j-i)):return None
        return ride_seconds(self.data,route['id'],indexes[0],indexes[-1]+1)

    def offsets(self,route):
        mapping=self.mapping(route)
        if len(mapping)!=len(route['stops'])-1:return None
        return [0.]+[self.leg_seconds(route,0,k) for k in range(1,len(route['stops']))]

    def info(self,routes=()):
        coverage={r['id']:{'mapped_segments':len(self.mapping(r)),'road_segments':len(self.geometry.routes.get(r['id'],{}).get('segments',[]))} for r in routes}
        return {'model_id':self.model_id,'input_sha256':self.sha256,'observed_operations':False,
                'source':'시뮬레이션 에이전트의 고정 v5 모형','coverage':coverage,
                'dwell_convention':'모형의 구간 끝 정차 15초 포함 · 중복 가산 없음',
                'assumptions':'교내40·외부65km/h 상한, 가감속1m/s², 정차15초의 시나리오 · 법정 제한속도나 실측 운행값 아님',
                'priority':'완료시간 관측·동일 차량 도착예정 차이·최신 구간속도 우선',
                'algorithm':'OSM 보행망 Dijkstra + 최대1회 환승 후보의 시간순 평가 + FIFO 승차기회 선택',
                'scope':'승하차·방향·보행거리 제한 안의 후보 비교 · 전역 최적 보장 아님'}

def modeled_speed_seconds(segment,speed):
    # Reuse the exact v5 max rule, with no extra dwell on a snapshot-speed total.
    return city_segment_seconds({'duration':segment['kinematic_seconds'],'d':[segment['meters']]},speed)

def fifo_opportunity(rows,ready,ahead,weight=1.):
    """Use the shared FIFO kernel on explicit free-capacity opportunities.

    Rows may be observations or labeled scenarios; this adapter never supplies
    capacities itself and never exports its synthetic internal vehicle indexes.
    """
    active=sorted((r for r in rows if r['departure_at']>=ready),key=lambda r:r['departure_at'])
    stage={'rid':'available-supply','board':0,'alight':1};vehicles=[];events=[]
    for k,row in enumerate(active):
        free=0. if row.get('full') else max(0.,row['seats_available'])
        vehicles.append({'rid':stage['rid'],'cap':free,'last_stop':-1,'onboard':[]})
        events.append((row['departure_at'],k,0))
    result=first_boardable(events,vehicles,ready,ready,stage,weight,[{'w':ahead,'stage':0,'stages':[stage]}])
    passed=result[1] if result else len(active)
    full=sum(vehicles[k]['cap']<=0 for k in range(min(passed+1,len(active))))
    return (active[passed] if result else None),passed,full
