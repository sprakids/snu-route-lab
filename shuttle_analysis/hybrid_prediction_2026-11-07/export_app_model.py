"""Export only the chosen weekday historical model, without keys or test targets."""
from pathlib import Path
import json,hashlib,math

ROOT=Path(__file__).resolve().parent
APP=ROOT.parent/'app'
KEY=('route_id','sta_sn','from_stop_id','to_stop_id','hour')
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def key(r):return tuple(str(r[k]) for k in KEY)

def main():
    frozen=load(ROOT/'selection_frozen.json');path=ROOT/'frozen_models.json'
    assert sha(path)==frozen['frozen_model_sha256']
    model=load(path);k=model['models']['weekday_history']['k']
    weekday={(int(r['weekday']),)+key(r):r for r in model['tables']['weekday']}
    segments=sorted({key(r)[:-1] for r in model['tables']['base']},key=lambda a:(a[0],int(a[1]),a[2:]))
    ids={s:i for i,s in enumerate(segments)};profiles=[];max_rounding=0.
    for r in model['tables']['base']:
        ident=key(r);H=float(r['H']);values=[];counts=[]
        for day in range(5):
            w=weekday.get((day,)+ident);n=int(w['weekday_n']) if w else 0
            estimate=H+(n/(n+k) if n else 0)*(float(w['weekday_mean'])-H if w else 0)
            value=round(estimate,6);max_rounding=max(max_rounding,abs(estimate-value))
            values.append(value);counts.append(n)
        profiles.append([ids[ident[:-1]],int(r['hour']),round(H,6),values,counts])
    assert len(segments)==259 and len(profiles)==2849 and max_rounding<=.00000051
    payload={'schema':'snu_weekday_history_v1','model_id':'weekday-history-20261107','model':'weekday_history',
             'label':'요일별 과거 평균','timezone':'Asia/Seoul','hours_inclusive':[12,22],
             'weekdays':[0,1,2,3,4],'history_dates':model['fit_dates'],'shrinkage_k':k,
             'source':'서울특별시 서울교통 빅데이터 플랫폼 · 교통정책지원시스템(TAIMS)',
             'source_url':'https://t-data.seoul.go.kr/dataprovide/trafficdataviewopenapi.do?data_id=1025',
             'unit':'hourly_segment_sum_load','unit_label':'시간당 구간 재차합',
             'interpretation':'한 시간에 해당 구간을 지난 차량들의 재차인원 합계 예측. 차량 한 대의 탑승 인원이나 정류장 대기 인원이 아닙니다.',
             'source_model_sha256':sha(path),'max_rounding_difference':max_rounding,
             'segments':[list(s) for s in segments],'profiles':profiles}
    target=APP/'data/weekday_history.json'
    assert not target.exists(),'Preserve an existing production model and version its replacement'
    target.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(json.dumps({'model':payload['model_id'],'segments':len(segments),'profiles':len(profiles),
                      'bytes':target.stat().st_size,'sha256':sha(target),'max_rounding_difference':max_rounding}))

if __name__=='__main__':main()
