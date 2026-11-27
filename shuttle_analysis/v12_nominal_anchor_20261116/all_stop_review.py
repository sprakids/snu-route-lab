"""Review every modeled boarding node/time using completed CSVs only."""
from pathlib import Path
from collections import defaultdict
import csv,hashlib,json,math,re,time
ROOT=Path(__file__).resolve().parent;w=Path(json.loads((ROOT/'candidate.json').read_bytes())['path'])
def read(p):return json.loads(p.read_bytes())
def rows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
deadline=time.monotonic()+10800
while not (w/'TEAM_PACKAGE_FINAL.json').exists():
    assert time.monotonic()<deadline
    time.sleep(10)
final=read(w/'TEAM_PACKAGE_FINAL.json');group='grid' if final['main_cases']==10 else 'pilot'
q=rows(w/f'{group}-stop-queue-exposure.csv');waits=rows(w/f'{group}-all-recorded-stops.csv');half=rows(w/f'{group}-all-recorded-half-hour-waits.csv')
if group=='pilot':
    q=[r for r in q if not r['case'].startswith('ablation')]
    waits=[r for r in waits if not r['case'].startswith('ablation')]
    half=[r for r in half if not r['case'].startswith('ablation')]
qkeys={(r['case'],r['node']) for r in q};wkeys={(r['case'],r['node']) for r in waits};assert qkeys==wkeys
assert len(q)==len(qkeys)==99*final['main_cases']
law=read(w/f'{group}-law-transfer-metrics.json')['cases'];lmap={(r['case']['case'],str(z['node'])):z for r in law for z in r['law_profiles']}
cases={r['case']:(r['weekday'],r['scenario']) for r in q};percase=defaultdict(list)
for r in waits:percase[r['case']].append(r)
all_over=math.fsum(float(r['over20_episode_weight']) for r in waits)
s=['# R'+w.name+' 전체 승차지·시간 점검','',
    f"모형의 승차지 99개 × 본실험 {final['main_cases']}조건, 총 {len(q)}행을 확인했습니다. 실제 정류장 전부의 새로운 현장 측정을 뜻하지 않습니다. 줄 크기와 연속 대기를 각각 계산했고, 비어 있는 승차지도 포함했습니다.",'',
    '## 법대: 오후 피크와 전체 기록 피크','',
    '앞선 15~20시 결과와 달리 전체 기록에는 오전·점심·늦은 시간도 들어갑니다. 40명은 사용자의 대략적 회상에 따른 점검값이며 계산에서 잘라낸 상한이 아닙니다.','',
    '|요일·운행·ARS|전체 최대 줄|그 시각|15~20시 최대 줄|전체 40명 초과 누적분|','|---|---:|---|---:|---:|']
lawq=[r for r in q if r['node'] in ['47','60']]
for r in lawq:
    a=lmap[(r['case'],r['node'])]
    clock=r['peak_kst'] if float(r['maximum_queue']) else '-'
    s.append(f"|{r['weekday']}·{r['scenario']}·{r['ars']}|{float(r['maximum_queue']):.2f}|{clock}|{a['maximum_queue']:.2f}|{float(r['minutes_above40_recollection_reference']):.2f}|")
s+=['','## 다른 정문 승차지','',
    '같은 이름의 승차지라도 방향과 ARS가 다르면 줄을 합치지 않았습니다. 21128은 정문 바깥 설입 방향이며, 교내의 서울대정문과 구분합니다.','',
    '|요일·운행·승차지|ARS|전체 최대 줄|그 시각|','|---|---|---:|---|']
for r in q:
    if r['ars'] not in ['21128','21269','21299']:continue
    s.append(f"|{r['weekday']}·{r['scenario']}·{r['stop']}|{r['ars']}|{float(r['maximum_queue']):.2f}|{r['peak_kst']}|")
s+=['','## 조건별 20분 초과 대기가 많은 승차지','',
    '대기 구간의 가중량을 기준으로 상위 3개씩 표시했습니다. 인접한 같은 승차지의 연속 대기는 합쳤으며, 경로를 바꿔 나간 학생도 포함했습니다. 고유 학생 수나 실제 관측 인원은 아닙니다.','',
    '|요일·운행|승차지(모형 번호)|20분 초과 가중 구간|평균 대기, 분|최대 대기, 분|','|---|---|---:|---:|---:|']
for case,rs in percase.items():
    day,sc=cases[case]
    ordered=sorted(rs,key=lambda r:float(r['over20_episode_weight']),reverse=True)
    for r in ordered[:3]:
        if not float(r['over20_episode_weight']):continue
        s.append(f"|{day}·{sc}|{r['stop']}({r['node']})|{float(r['over20_episode_weight']):.2f}|{float(r['mean_wait_min']):.2f}|{float(r['max_wait_min']):.2f}|")
s+=['','## 30분별로 가장 큰 긴 대기 집단','',
    '아래 20개는 줄에 합류한 시각으로 묶은 집단입니다. 그 순간 줄 길이를 의미하지 않습니다. 누적 도착·순간 대기 인원·실제 승차 대기시간을 구분해 해석합니다.','',
    '|요일·운행|승차지|합류 구간 시작|20분 초과 가중 구간|평균 대기, 분|','|---|---|---|---:|---:|']
for r in sorted(half,key=lambda r:float(r['over20_episode_weight']),reverse=True)[:20]:
    s.append(f"|{r['day']}·{r['scenario']}|{r['stop']}({r['node']})|{r['queue_entry_time_kst']}|{float(r['over20_episode_weight']):.2f}|{float(r['mean_wait_min']):.2f}|")
s+=['','## 해석과 다음 확인 대상','',
    '남은 병목은 수요가 몰리는 시각, 목적지행 호환 노선의 간격, 정원과 줄 앞의 승객, 학생의 개인별 인내가 함께 만든 모의 결과입니다. 큰 줄 하나만으로 수요나 외부 승객을 각각 역산할 수는 없습니다. 해당 시각의 유입·승차·잔여 좌석 관측이 있어야 원인을 더 나눌 수 있습니다.',
    '인내 분포는 이번에 새로 측정한 값이 아닙니다. 그 값을 줄여 20분 초과를 없애거나 줄 인원을 40명으로 제한하지 않았습니다. 관측이 없는 승차지의 예측이 실제로 정확하다고 주장하지 않습니다.',
    '기본/피크 운행은 시나리오이며 실제 차량 운영을 변경한 것은 아닙니다. 교외 배경 승객과 실제 등록 정원 등 남은 공급 가정은 [자료·가정 문서](SOURCES_AND_ASSUMPTIONS.md)에 명시했습니다. [최종 비교](FINAL_REVIEW.md)와 함께 보십시오.','']
out=w/'ALL_STOP_REVIEW.md';assert not out.exists();out.write_text('\n'.join(s),encoding='utf8')
for href in re.findall(r'\]\(([^)]+)\)',out.read_text(encoding='utf8')):assert (w/href).exists(),href
summary={'display_name':'R'+w.name,'main_cases':final['main_cases'],'modeled_boarding_nodes':99,'all_stop_rows':len(q),
    'all_recorded_over20_episode_weight':all_over,'law_all_recorded_maximum':max(float(r['maximum_queue']) for r in lawq),
    'law_afternoon_maximum':max(z['maximum_queue'] for r in law if not r['case']['case'].startswith('ablation') for z in r['law_profiles']),
    'public_model_preserved':final['public_model_preserved'],'operating_adoption_recommended':False,
    'documents_sha256':{n:sha(w/n) for n in ['ALL_STOP_REVIEW.md','TEAM_PACKAGE_FINAL.json']},'production_writes':False}
p=w/'TEAM_PACKAGE_ALL_STOPS.json';assert not p.exists();p.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('ALL_STOPS_REVIEW_COMPLETE',summary,flush=True)
