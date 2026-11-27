"""Apply the confirmed position quota without resetting counters or changing code."""
import argparse,datetime,json,sys,urllib.request
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'collector'))
from export_history import credentials
c=credentials()
assert urlsplit(c['url']).hostname=='snu-route-collector.touchline-atlas-june.workers.dev'
def request(path,body=None):
    req=urllib.request.Request(c['url']+path,data=json.dumps(body).encode() if body is not None else None,
        headers={'Authorization':'Bearer '+c['token'],'Content-Type':'application/json','User-Agent':'SNU-Route-Lab/0.4'})
    with urllib.request.urlopen(req,timeout=25) as response:return json.load(response)
def save(name,value):
    path=ROOT/name
    if path.exists():raise RuntimeError('Preserve existing evidence: '+name)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def summary(s):
    return {k:s.get(k) for k in ['enabled','configured','position_calls_today','position_calls_remaining',
        'position_app_daily_limit','collection_policy','next_scheduled_at','usage','errors','server_time']}
parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
before=request('/snapshot')
if not args.apply:
    print(json.dumps(summary(before),ensure_ascii=True,indent=2));sys.exit()
assert before['enabled'] and before['configured'],'Collector must already be healthy and enabled'
assert not before['usage']['throttled'] and before['usage']['writes']<70000
assert before['collection_policy']['approved_limit']==10000,'Expected unchanged pre-approval policy'
evidence=json.loads((ROOT/'approval-evidence.json').read_text(encoding='utf-8'))
assert evidence['requested_daily_limit']==15000
save('before.json',before)
after=request('/control',{'enabled':True,'provider_approved_limit':15000})
save('after.json',after)
assert after['collection_policy']['approved_limit']==15000
assert after['collection_policy']['cap']==(3200 if after['collection_policy']['weekend'] else 10400)
assert after['position_calls_today']>=before['position_calls_today'],'Never reset the spent ledger'
assert after['position_calls_today']<=after['position_app_daily_limit']
assert after['enabled']
receipt={'applied_at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(),
    'provider_approved_limit':15000,'before':summary(before),'after':summary(after),
    'confirmation_basis':evidence['confirmation_basis'],'code_deployment_required':False,
    'daily_counter_reset':False,'platform_limits_raised':False,'regular_weekday_requests':9568,
    'retry_reserve':832,'seoul_daily_margin':4600}
save('receipt.json',receipt)
print(json.dumps(receipt,ensure_ascii=True,indent=2))
