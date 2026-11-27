"""Read pre-existing weekday curves; no simulation, calibration or publication."""
from pathlib import Path
from bisect import bisect_right
from datetime import datetime,timezone
import gzip,hashlib,json,math,urllib.request
HERE=Path(__file__).resolve().parent;A=HERE.parent;PUBLIC=A/'simulation_viewer_2026-11-07/public'
START,END=44400.,44460.;EPS=1e-7
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,d):
    assert not p.exists(),p
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def clock(t):return f'{int(t//3600):02}:{int(t%3600//60):02}:{t%60:06.3f}'
def curve(label,p,node):
    data=read(p);raw=data['queue_timeline'][node]
    assert [r[0] for r in raw]==sorted(r[0] for r in raw)
    # The last value at a shared timestamp is the right-continuous map state;
    # zero-duration intermediate updates must not inflate extrema.
    points={float(r[0]):float(r[1]) for r in raw};times=sorted(points)
    def at(t):
        index=bisect_right(times,t)-1
        return points[times[index]] if index>=0 else 0.
    cuts=sorted({START,END,*[t for t in times if START<t<END]})
    spans=[{'start_seconds':a,'end_seconds_exclusive':b,'start_kst':clock(a),'end_kst_exclusive':clock(b),'queue_raw':at(a)} for a,b in zip(cuts,cuts[1:]) if b>a]
    assert abs(math.fsum(s['end_seconds_exclusive']-s['start_seconds'] for s in spans)-60)<1e-8
    assert all(s['queue_raw']>=-EPS for s in spans)
    values=[s['queue_raw'] for s in spans]
    nearby=[]
    for e in data.get('events',[]):
        if e[1]==node and START-300<=e[0]<END+300:
            nearby.append({**dict(zip(data['event_columns'],e)),'clock_kst':clock(e[0])})
    return {'model':label,'source_path':str(p),'source_sha256':sha(p),'node':node,'window_seconds':[START,END],
        'range_raw':[min(values),max(values)],'range_display':[0. if abs(min(values))<EPS else min(values),max(values)],
        'time_weighted_mean':math.fsum((s['end_seconds_exclusive']-s['start_seconds'])*s['queue_raw'] for s in spans)/60,
        'segments':spans,'nearby_vehicle_events':nearby,'simultaneous_updates_coalesced':True,
        'float_roundoff_zero_tolerance':EPS,'unit':'weighted modeled waiting people, not a field count',
        'range_is_statistical_prediction_interval':False}
common=read(PUBLIC/'data/capacity_v11/common.json');node=common['hot_nodes']['admin_snu']
assert common['nodes'][node]['stop_id']=='snu-410' and node==1
jobs=[('V11-map-regular',PUBLIC/'data/capacity_v11/regular-mon.json'),('V11-map-peak',PUBLIC/'data/capacity_v11/peak-mon.json'),
      ('R261116161819-regular',A/'261116161819/runs/anchor-combined-regular-mon/attempt_01/regular-mon.json.gz'),
      ('R261116161819-peak',A/'261116161819/runs/anchor-combined-peak-mon/attempt_01/peak-mon.json.gz')]
results=[curve(label,p,node) for label,p in jobs]
assert results[0]['range_raw']==results[1]['range_raw'] and results[2]['range_raw']==results[3]['range_raw']
network=[]
def fetch(name,url,expected=None):
    row={'name':name,'url':url}
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'Accept-Encoding':'identity'}),timeout=25) as response:body=response.read();row['http_status']=response.status
        row['sha256']=hashlib.sha256(body).hexdigest()
        if expected is not None:row['local_sha256_match']=row['sha256']==expected;assert row['local_sha256_match']
        if name=='latest':
            d=json.loads(body);row.update(model_id=d['model_id'],source_simulation=d['source_simulation']);assert d['model_id']=='261110162302'
        row['status']='VERIFIED'
    except Exception as exc:row.update(status='UNVERIFIED',error=str(exc))
    network.append(row)
fetch('latest','https://snu-shuttle-simulation.vercel.app/routing-model/latest.json',sha(PUBLIC/'routing-model/latest.json'))
fetch('map_regular_payload','https://snu-shuttle-simulation.vercel.app/data/capacity_v11/regular-mon.json.gz',sha(PUBLIC/'data/capacity_v11/regular-mon.json.gz'))
report={'observation_id':'20261123-1220-admin-snu-immediate-boarding-01','computed_at_utc':datetime.now(timezone.utc).isoformat(),
    'request':'Monday12:20 full-minute queue envelope before incorporating the new observation',
    'interval':'12:20:00 <= t <12:21:00 Asia/Seoul','results':results,'public_data_verification':network,
    'date_scope':'Stored Monday templates, not a reconstruction from actual2026-11-23 bus positions',
    'operational_route_api_numeric_forecast_used':False,
    'interpretation':'Queue range alone does not establish individual immediate boarding; actual unknown seconds, bus presence and boarding opportunity are separate.',
    'new_observation_numeric_queue_target':None,'model_conditions_rerun':0,'model_changed':False,'production_writes':False}
save(HERE/'queue_range_1220_comparison.json',report)
save(HERE/'observation_use_1220_comparison.json',{'observation_id':report['observation_id'],
    'use':'user_requested_read_only_description_of_preexisting_model_outputs','comparison_file':'queue_range_1220_comparison.json',
    'numeric_queue_fit_performed':False,'wait_seconds_fit_performed':False,'formal_accuracy_score_computed':False,
    'new_numeric_count_created_from_immediate_boarding':False,'model_conditions_rerun':0,'model_changed':False})
s=['# 월요일12:20 행정관 설입행:기존 예측 비교','',
    '월요일 상황을 새로 계산하지 않고 이전에 저장된 모형 곡선만 읽었습니다. 아래 범위는 실제11월23일 인원이나 통계적 신뢰구간이 아니라12:20의1분 동안 변하는 모형 값입니다.','',
    '|모형|12:20 전체 최소~최대, 명 상당|시간 가중 평균|','|---|---:|---:|']
for r in [results[2],results[0]]:s.append(f"|{r['model']}|{r['range_display'][0]:.2f}~{r['range_display'][1]:.2f}|{r['time_weighted_mean']:.2f}|")
s+=['','기본·피크 운행은 이 시각에 각각 같은 범위였습니다. R에서는12:20:18.543까지 수치상0명, 이후 양의 줄로 바뀌어12:20:58.405부터약12.04명입니다. V11은12:20:22.606까지0명이고 후반 최대약5.76명입니다.',
    '초가 미상이므로12:20:00 값 하나로 비교하지 않았습니다. 같은 시각의 중간 갱신을 합치고 양의 시간 길이를 가진 구간만 집계했습니다. R의약8e-14명은 부동소수점 오차로0명 표시했으며 원래 값도 JSON에 보존했습니다.',
    '해당 분에 줄이0인 구간이 있다는 사실을 관측자의 실제 도착 당시 줄이0이었다는 뜻으로 쓰지 않습니다. 줄이 한 대 수용량 이내인지와 그 순간 버스에 바로 탈 수 있는지는 버스의 정차·도착·승차 처리까지 별도로 확인할 항목입니다.',
    '관측 원문의 숫자 미측정 상태는 유지했습니다. 이번 사용 상태는 [별도 사용 원장](observation_use_1220_comparison.json)에 추가했고 모형 보정이나 사건 실험은 수행하지 않았습니다.','',
    '[시각 구간·차량 사건·입력 해시·공개 파일 검산](queue_range_1220_comparison.json).','']
p=HERE/'12시20분_기존엔진_범위.md';assert not p.exists();p.write_text('\n'.join(s),encoding='utf8')
print(json.dumps({'range_R':results[2]['range_display'],'range_V11_map':results[0]['range_display'],
    'same_regular_and_peak':True,'public_verification':network,'model_changed':False},ensure_ascii=False),flush=True)
