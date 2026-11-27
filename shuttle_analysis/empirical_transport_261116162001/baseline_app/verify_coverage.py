"""Connectivity check only: 13 representative origins x two destinations; no external calls."""
import json
from datetime import datetime
from unittest.mock import patch
from server import Application, KST, ROOT, RUNTIME
from routing import PRESETS

app=Application()
departure=datetime(2026,11,6,17,0,tzinfo=KST).timestamp()
cases=[]
with patch('urllib.request.urlopen',side_effect=AssertionError('Coverage must not call external services')) as requests:
    for origin in app.origins:
        for destination in app.destinations:
            result=app.planner.plan((origin['lat'],origin['lon']),(destination['lat'],destination['lon']),
                                    departure,'estimate',PRESETS['fast'],False)
            cases.append({'origin':origin['label'],'destination':destination['label'],
                          'candidates':result['candidate_count'],
                          'has_bus':any(c['route_names'] for c in result['candidates'])})
    external_calls=requests.call_count
report={'checked_at':datetime.now(KST).isoformat(),'scope':'representative origin connectivity, not actual journey accuracy',
        'departure':datetime.fromtimestamp(departure,KST).isoformat(),'external_calls':external_calls,
        'cases':cases,'connected_cases':sum(c['candidates']>0 for c in cases),'total_cases':len(cases),
        'shuttle_included':False,'note':'Future/estimate mode never generates shuttle positions or departures.'}
RUNTIME.mkdir(exist_ok=True)
(RUNTIME/'coverage_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({key:report[key] for key in ('connected_cases','total_cases','external_calls')},ensure_ascii=False))
if report['connected_cases']!=report['total_cases']:raise SystemExit('Some representative endpoints are disconnected.')
