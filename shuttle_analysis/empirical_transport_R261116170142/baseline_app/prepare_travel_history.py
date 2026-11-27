"""Build a dated speed prior from preserved Seoul responses, not crowding counts."""
import json,statistics,hashlib
from pathlib import Path
from datetime import datetime
from collections import defaultdict
ROOT=Path(__file__).parent

def main():
    network=json.loads((ROOT/'data/network.json').read_text(encoding='utf-8'));profiles=defaultdict(list);sources=[]
    for route in network['routes']:
        p=ROOT/'data/raw'/('route_'+route['id']+'.json')
        rows=json.loads(p.read_text(encoding='utf-8')).get('resultList',[])
        when=datetime.fromisoformat(route['captured_at']);date=when.date().isoformat()
        for r in rows:
            try:kmh=float(r['sectSpd']);seq=int(r['seq'])
            except (ValueError,KeyError,TypeError):continue
            if .5<=kmh<=100:profiles[f"{route['id']}:{seq}"].append({'date':date,'weekday':when.weekday(),'hour':when.hour,'speed_kmh':kmh})
        sources.append({'path':'data/raw/'+p.name,'captured_at':route['captured_at'],'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    out={'schema':'seoul_section_speed_history_v1','unit':'km/h','kind':'dated_provider_speed_snapshots_not_completed_trip_times',
        'weekday_hour_model_validated':False,'source':'서울시 공식 모바일 버스정보 보존 응답','sources':sources,'speed_profiles':dict(profiles)}
    (ROOT/'data/travel_history.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print('historical speed links',len(profiles),'dates',sorted({x['date'] for v in profiles.values() for x in v}))
if __name__=='__main__':main()
