"""Demand is a scheduling proxy, never a vehicle crowding grade."""
import json,csv
from pathlib import Path
from collections import defaultdict

ROOT=Path(__file__).parent;APP=ROOT.parent/'app';routes=['100100250','100100251','100100253','120900011','120900012']
def main():
    h=json.loads((APP/'data/weekday_history.json').read_text(encoding='utf-8'))
    history=defaultdict(list);classes=defaultdict(float)
    for row in h['profiles']:
        segment,hour,pooled,means,n=row;rid=h['segments'][segment][0]
        for day in range(5):history[(day,hour,rid)].append(means[day])
    names=['월','화','수','목','금']
    source=ROOT.parent/'course_demand_2026-11-06/outputs/stop_inflow_5min_scenarios.csv'
    with source.open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            if r['scenario']=='reference_dorm19p49_depart50' and r['weekday'] in names and r['route_id'] in routes and r['boarding_stage']=='1':
                classes[(names.index(r['weekday']),int(r['bin_minute']),r['route_id'])]+=float(r['expected_trip_events'])
    hist={k:sum(v)/len(v) for k,v in history.items()};hm=max(hist.values(),default=1) or 1;cm=max(classes.values(),default=1) or 1
    out={}
    for day in range(7):
        out[day]={}
        for minute in range(680,1390,5):
            out[day][minute]={rid:{'history':hist.get((day,minute//60,rid),0)/hm,'classes':classes.get((day,minute,rid),0)/cm} for rid in routes}
    (ROOT/'demand.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    (APP/'data/demand_features.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    (ROOT/'demand_provenance.json').write_text(json.dumps({'history_model':h['model_id'],'history_unit':h['unit'],'class_source':str(source.relative_to(ROOT.parent)),
        'class_unit':'expected_trip_events','class_scenario':'reference_dorm19p49_depart50','observed_passengers':False,
        'unavailable_weekend_history':True,'normalization':'maximum across known days, times and five routes'},ensure_ascii=False,indent=2),encoding='utf-8')
    print('demand prepared',len(hist),'route-hour-weekday profiles;',len(classes),'modeled route-bins')
if __name__=='__main__':main()
