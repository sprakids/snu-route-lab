"""Expose the latest behavior candidate even when its pilot is rejected."""
from pathlib import Path
import csv,json,math,subprocess,sys,time
ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent;w=ANALYSIS/'261116122336'
def read(p):return json.loads(p.read_bytes())
def rows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
deadline=time.monotonic()+2400
while not (w/'pilot-decision.json').exists():
    assert time.monotonic()<deadline
    time.sleep(10)
# The parent script is read-only. Make a pilot-specific analysis copy with its
# own output names, rather than relabelling pilot records as a ten-case grid.
p=ROOT/'pilot_stop_queue_exposure.py';assert not p.exists()
t=(ROOT/'stop_queue_exposure.py').read_text(encoding='utf8')
t=t.replace('grid-stop-queue-exposure.csv','pilot-stop-queue-exposure.csv').replace('grid-validation.json','pilot-validation.json')
t=t.replace('assert len(rows)==990','assert len(rows)==297')
t=t.replace("w/'prediction-information-audit.json'","w/'pilot-prediction-information-audit.json'")
p.write_text(t,encoding='utf8')
log=ROOT/'pilot-full-profile-analysis.log';assert not log.exists()
with log.open('x',encoding='utf8') as f:
    result=subprocess.run([sys.executable,'-X','utf8',str(p),str(w)],stdout=f,stderr=subprocess.STDOUT)
assert result.returncode==0
v=read(w/'pilot-validation.json')['results'];main=[r for r in v if not r['case']['case'].startswith('ablation')]
base=read(ANALYSIS/'261116010854/grid-validation.json')['results']
direct=read(ANALYSIS/'261116112731/pilot-validation.json')['results']
fields=[x for x in rows(w/'pilot-field-comparison.csv') if x['model']==w.name and not x['case'].startswith('ablation')]
assert len(fields)==4
exposure=rows(w/'pilot-stop-queue-exposure.csv');assert len(exposure)==297
d=read(w/'pilot-decision.json');b=read(w/'pilot-behavior-validation.json')
text=['# 최신 하교 행동 후보122336: 월·화 결과','',
      '영구적인 수단 선택의 자유와 현재 정류장에서 다시 경로를 바꿀 사유를 분리했습니다. 초기·이후 모두 접근편 뒤 환승 대기를 미예견하며,개인 인내·만차와 추가 통과·운행부재·수단 자유·무제한 변경·반복 도보·정문 최종 대안은 유지했습니다. 비용식과 숫자 계수·물리 입력은112731과 같습니다.','',
      f"사전 판정은 **{d['status']}**입니다. 이는 실행 오류 여부와 다른 판정입니다. 물리검사와 행동검사는통과했지만 성과 조건을 만족하지 못한 경우 운영 후보로 확대·채택하지 않았습니다. 본 월·화2조건과 같은 월요일 수정 비활성1조건을 각한번 실행했습니다.",'',
      '## 요청 직전010854 → 최신122336','',
      '|요일|평균 총시간(분)|최대 연속 대기(분)|20분 초과 가중 구간|p99 총시간(분)|미완료|',
      '|---|---:|---:|---:|---:|---:|']
comparisons=[]
for r in main:
    c=r['case'];old=next(a for a in base if (a['case']['day'],a['case']['scenario'])==(c['day'],c['scenario']))
    par=next(a for a in direct if not a['case']['case'].startswith('ablation') and a['case']['day']==c['day'])
    diag=lambda a:a['extended_diagnostics'];q=lambda a:diag(a)['finished_trip_quantiles']['total_min']
    text.append(f"|{c['day']}|{q(old)['mean']:.3f}→{q(r)['mean']:.3f}|{diag(old)['all_recorded_time_max_continuous_wait_min']:.3f}→{diag(r)['all_recorded_time_max_continuous_wait_min']:.3f}|{diag(old)['all_recorded_time_over20_episode_weight']:.3f}→{diag(r)['all_recorded_time_over20_episode_weight']:.3f}|{q(old)['p99']:.3f}→{q(r)['p99']:.3f}|{r['unserved_trip_weight']:.3f}|")
    comparisons.append({'day':c['day'],'original_mean':q(old)['mean'],'direct_parent_mean':q(par)['mean'],'latest_mean':q(r)['mean'],
         'current_pressure_violation_weight':next(x for x in b['cases'] if x['case']['case']==c['case'])['physical_changes_without_current_queue_pressure_weight']})
text+=['','## 이미 사용한 관측과 비교','',
       '분 안의 관측 초는 모릅니다. 각 분을 균등 적분한 평균이며,이미 여러 후보에 사용한 네 관측입니다. 독립 정확도 검증이 아닙니다.','',
       '|관측|관측 인원|요청 직전 분평균 → 최신 분평균|기대 절대오차 전→후|','|---|---:|---:|---:|']
for x in fields:
    old=next(a for a in rows(ANALYSIS/'261116105704/grid-field-comparison.csv') if a['model']=='261116010854' and a['scenario']==x['scenario'] and a['observation_id']==x['observation_id'])
    k='expected_absolute_distance_to_count_or_interval'
    text.append(f"|{x['reported_minute']}|{x['observed_low']}~{x['observed_high']}|{float(old['uniform_minute_mean']):.3f}→{float(x['uniform_minute_mean']):.3f}|{float(old[k]):.3f}→{float(x[k]):.3f}|")
text+=['','## 법대·사회대입구 양방향: 전체 기록','',
       '40명은 사용자 회상에 따른 점검 기준입니다. 사람을 잘라내거나 수용량 상한으로 적용하지 않았습니다. 표시 화면 밖의 초기·마감도 포함합니다.','',
       '|요일|ARS|최대 줄(명 상당)|최대 시각|40명 초과 누적(분)|최장 연속 초과(분)|','|---|---|---:|---|---:|---:|']
for x in exposure:
    if x['case'].startswith('ablation') or x['node'] not in ('47','60'):continue
    text.append(f"|{x['weekday']}|{x['ars']}|{float(x['maximum_queue']):.3f}|{x['peak_kst']}|{float(x['minutes_above40_recollection_reference']):.3f}|{float(x['longest_spell_above40_minutes']):.3f}|")
text+=['',
       '가중 대기 구간·변경 사건은 고유 학생 수가 아닙니다. 현재 줄에 변경 사유 없이 물리 경로를 바꾼 가중치는 본조건에서각0인지별도검사했습니다. 행동 규칙이 일관되게 작동하는 것과 실제 귀가시간·줄을 정확히 예측하는 것은 다른 검사입니다.',
       '최신 후보의 월·화 평균 총시간은 직접 부모112731보다도 각각'+('/'.join(f"{r['latest_mean']-r['direct_parent_mean']:+.3f}" for r in comparisons))+'분 변화했습니다. 상태 분리만으로 모든 수치가 개선됐다고 해석하지 않습니다.','',
       '- [모든99노드의 전체 기록 대기:본2+진단1](../261116122336/pilot-all-recorded-stops.csv)',
       '- [정류장·30분 진입집단 대기:본2+진단1](../261116122336/pilot-all-recorded-half-hour-waits.csv)',
       '- [전 정류장의 최대 줄·40명 초과 지속](../261116122336/pilot-stop-queue-exposure.csv)',
       '- [인지 전망·운영 ETA·실제 누적 대기 분리 검산](../261116122336/pilot-prediction-information-audit.json)',
       '- [현재 변경 사유를 포함한 행동 검사](../261116122336/pilot-behavior-validation.json)',
       '- [사전 판정](../261116122336/pilot-decision.json)',
       '- [전요일 중간안과 실패한 비교 전체](FINAL_REVIEW.md)',
       '- [가정·자료·출처](SOURCES_AND_ASSUMPTIONS.md)','']
out=ROOT/'LATEST_PILOT_RESULTS.md';assert not out.exists();out.write_text('\n'.join(text),encoding='utf8')
print('LATEST_PILOT_REPORT_COMPLETE',json.dumps(comparisons,ensure_ascii=False),flush=True)
