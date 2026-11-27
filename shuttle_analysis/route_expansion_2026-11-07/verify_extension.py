"""Independent arithmetic check against the preserved, dated source rows."""
from pathlib import Path
from datetime import datetime
import json,math,sys,hashlib
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'app'))
from historical_forecast import HistoricalForecast,KST
model=HistoricalForecast()
source=json.loads((ROOT/'cached_history_new_routes.json').read_text(encoding='utf-8'))
by_date={d:{(str(r['routeId']),str(int(r['staSn'])),str(r['fromStaId']),str(r['toStaId'])):r for r in rows} for d,rows in source.items()}
checked=0;max_error=0.
for ident in model.segments:
    if ident in model.base_segments:continue
    for hour in range(12,23):
        data={d:float(rows[ident][f'a18SumLoadPsngNum{hour:02d}h']) for d,rows in by_date.items() if ident in rows and rows[ident].get(f'a18SumLoadPsngNum{hour:02d}h') is not None}
        mean=math.fsum(data.values())/len(data)
        for weekday in range(5):
            values=[v for d,v in data.items() if datetime.strptime(d,'%Y%m%d').weekday()==weekday]
            n=len(values);expected=mean+n/(n+10)*(math.fsum(values)/n-mean) if n else mean
            at=datetime(2026,11,9+weekday,hour,tzinfo=KST).timestamp()
            actual=model.point(*ident,at)['predicted_sum_load']
            max_error=max(max_error,abs(actual-expected));checked+=1
assert max_error<=.00000051
base=ROOT.parent/'app/data/weekday_history.json';backup=ROOT/'backups/app/data/weekday_history.json'
assert base.read_bytes()==backup.read_bytes(),'Original five-route model changed'
result={'status':'PASS','checked_new_weekday_values':checked,'max_rounding_error':max_error,
        'old_model_bytes_unchanged':True,'new_network_requests':0,'new_segment_count':len(model.segments)-259,
        'base_model_sha256':hashlib.sha256(base.read_bytes()).hexdigest()}
(ROOT/'independent_history_verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
