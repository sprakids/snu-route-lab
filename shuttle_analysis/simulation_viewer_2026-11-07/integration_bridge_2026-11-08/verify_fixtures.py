"""Run portable fixtures with Python's standard library alone."""
from pathlib import Path
import copy,json,hashlib
from bridge import kinematic_profile,first_boardable,ride_seconds

HERE=Path(__file__).resolve().parent


def main():
    inputs=json.loads((HERE/'route_time_inputs.json').read_text(encoding='utf-8'))
    fixtures=json.loads((HERE/'fixtures.json').read_text(encoding='utf-8'))
    for case in fixtures['profile_cases']:
        p=kinematic_profile(case['points'],case['cuts'],inputs['campus_polygon'],case['force_campus'])
        assert abs(p['duration']-case['expected_kinematic_seconds'])<1e-5,case['name']
        assert p['dwell_seconds']==15*len(case['cuts'])
        for k,cap in enumerate(p['cap']):assert max(p['v'][k],p['v'][k+1])*3.6<=cap+1e-4
    for case in fixtures['queue_cases']:
        args=[case[k] for k in ('rows','vehicles')]+[0.,0.,case['stage'],case['weight'],case['waiting']]
        before=copy.deepcopy(args);out=first_boardable(*args)
        assert out[0]==case['expected'] and args==before,case['name']
    hops=0
    for rid,r in inputs['routes'].items():
        for s in r['segments']:
            assert abs(ride_seconds(inputs,rid,s['from_index'],s['to_index'])-s['model_seconds'])<1e-7
            hops+=1
    result={'status':'PASS','profile_fixtures':len(fixtures['profile_cases']),
        'queue_fixtures':len(fixtures['queue_cases']),'route_hops':hops,'third_party_imports':False,
        'bridge_sha256':hashlib.sha256((HERE/'bridge.py').read_bytes()).hexdigest(),
        'inputs_sha256':hashlib.sha256((HERE/'route_time_inputs.json').read_bytes()).hexdigest()}
    (HERE/'portable_verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':main()
