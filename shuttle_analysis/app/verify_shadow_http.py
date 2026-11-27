"""Exercise V11 -> signed ticket -> R -> Durable Object comparison archive."""
import gzip,json,time,urllib.request
from pathlib import Path
def call(path,value=None,worker=False):
    url=('http://127.0.0.1:8857' if worker else 'http://127.0.0.1:8861')+path
    headers={'Content-Type':'application/json'}
    if worker:headers['Authorization']='Bearer shadow-local-fixture-only'
    request=urllib.request.Request(url,data=json.dumps(value).encode() if value is not None else None,headers=headers)
    with urllib.request.urlopen(request,timeout=55) as response:raw=response.read()
    return raw if path.endswith('/export') else json.loads(raw)
def main():
    start=time.perf_counter();plan=call('/api/plan',{'origin_id':'snu-410','destination_id':'snu-station','mode':'live',
        'departure_at':time.time(),'preset':'fast','include_shuttle':True})
    plan_seconds=time.perf_counter()-start;assert plan['prediction_model']['queue_model']=='261110162302'
    ticket=plan['shadow']['ticket'];result=call('/api/shadow-run',{'ticket':ticket})
    assert result.get('saved') and result.get('status')=='complete',result
    status=call('/shadow/status',worker=True);assert status['latest']['operating_model']=='V11'
    duplicate=call('/api/shadow-run',{'ticket':ticket});assert not duplicate['saved']
    archived=gzip.decompress(call('/shadow/export',worker=True));records=[json.loads(line) for line in archived.splitlines()]
    assert records[-1]['comparison']['comparison_id']==status['latest']['comparison_id']
    for record in records:
        text=json.dumps(record)
        for forbidden in ['"lat"','"lon"','"point"','"geometry"','"ticket"','"token"']:assert forbidden not in text
    recording=call('/shuttle/status',worker=True)
    output={'passed':True,'environment':'local workerd + local Python; not production deployment',
        'V11_model':'261110162302','candidate_model':result['candidate_model'],'V11_seconds':round(plan_seconds,3),
        'comparison_saved':True,'duplicate_blocked':True,'archived_comparisons':len(records),'exact_location_persisted':False,
        'shuttle_recording':recording,'comparison_accuracy_validated':False}
    target=Path(__file__).resolve().parent.parent/'shadow_operation_261116/local_http_check.json'
    target.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(output,ensure_ascii=True)[:2100])
if __name__=='__main__':main()
