"""Independent reader parity check, not an out-of-sample accuracy claim."""
import json
import sys
import hashlib
from pathlib import Path

WORK=Path(__file__).resolve().parent
APP=WORK/'app_candidate'
SOURCE=WORK.parent/'simulation_viewer_2026-11-07/weekday_operations_2026-11-10'
sys.path.insert(0,str(APP))
from city_operations import CityOperations,validate_operations

def main():
    raw=(SOURCE/'city_operations.json').read_bytes()
    data=json.loads(raw);network_raw=(APP/'data/network.json').read_bytes()
    validate_operations(data,json.loads(network_raw),hashlib.sha256(network_raw).hexdigest())
    source=json.loads((SOURCE/'vehicle_stop_clocks.json').read_bytes())
    assert source['revision']==data['revision']
    operations=CityOperations(data,'candidate_not_published')
    checks=[];count=0;maximum=0.
    for rid,spec in data['routes'].items():
        for day in range(5):
            supplied=source['routes'][rid][str(day)]
            expected=[sorted(row[k] for row in supplied) for k in range(len(spec['stops']))]
            actual=operations.timeline(rid,day)
            assert [len(v) for v in expected]==[len(v) for v in actual],(rid,day,'count')
            error=max((abs(a-b) for arow,brow in zip(expected,actual) for a,b in zip(arow,brow)),default=0.)
            assert error<1e-6,(rid,day,error)
            n=sum(map(len,actual));count+=n;maximum=max(maximum,error)
            checks.append({'route_id':rid,'weekday':day,'clock_values':n,'maximum_absolute_seconds':error})
    report={'status':'PASS','kind':'reader_parity_not_predictive_accuracy','revision':data['revision'],
        'operations_sha256':hashlib.sha256(raw).hexdigest(),'network_sha256':hashlib.sha256(network_raw).hexdigest(),
        'route_days':len(checks),'clock_values':count,'maximum_absolute_seconds':maximum,'checks':checks,
        'production_changed':False,'latest_pointer_changed':False}
    (WORK/'operation-clock-verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='checks'}))

if __name__=='__main__':main()
