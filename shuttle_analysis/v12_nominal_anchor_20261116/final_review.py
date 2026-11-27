"""Readable final receipt with R label, residual issues and all-week stop checks."""
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
import csv,gzip,hashlib,json,math,re,time
ROOT=Path(__file__).resolve().parent;A=ROOT.parent;w=Path(json.loads((ROOT/'candidate.json').read_bytes())['path'])
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
def save(p,v):
    assert not p.exists(),p
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
deadline=time.monotonic()+10800
while not all((w/n).exists() for n in ['TEAM_PACKAGE.json','MECHANISM_DIAGNOSIS_v2.md','mechanism-diagnosis.json']):
    assert not list((w/'runs').glob('*/attempt_01/failure.json'))
    assert time.monotonic()<deadline
    time.sleep(10)
package=read(w/'TEAM_PACKAGE.json');decision=read(w/'pilot-decision.json');proof=read(w/'artifact-verification.json')
for n,h in package['document_sha256'].items():assert sha(w/n)==h,n
group='grid' if package['main_cases']==10 else 'pilot'
validation=read(w/f'{group}-validation.json')['results'];main=[r for r in validation if not r['case']['case'].startswith('ablation')]
law=[r for r in read(w/f'{group}-law-transfer-metrics.json')['cases'] if not r['case']['case'].startswith('ablation')]
mechanism=read(w/'mechanism-diagnosis.json');f=read(w/'frozen/prepared_capacity44_pair.json.gz');nodes=f['prepared']['common']['nodes']
over=lambda r:r['extended_diagnostics']['all_recorded_time_over20_episode_weight']
maximum=lambda r:r['extended_diagnostics']['all_recorded_time_max_continuous_wait_min']
quant=lambda r:r['extended_diagnostics']['finished_trip_quantiles']['total_min']
percent=lambda before,after:100*(after/before-1) if before else None
original=read(A/'261116010854/grid-validation.json')['results']
matched=[(next(o for o in original if (o['case']['day'],o['case']['scenario'])==(r['case']['day'],r['case']['scenario'])),r) for r in main]
all_stop=rows(w/f'{group}-all-recorded-stops.csv')
half=rows(w/f'{group}-all-recorded-half-hour-waits.csv')
assert len(all_stop)==len(validation)*len(nodes)
for r in validation:
    z=[x for x in all_stop if x['case']==r['case']['case']]
    assert abs(math.fsum(float(x['over20_episode_weight']) for x in z)-over(r))<1e-5
summary={'display_name':'R'+w.name,'release_id':w.name,'public_model':'V11 261110162302',
    'main_cases':len(main),'diagnostic_cases':1,'all_recorded_stops_rows':len(all_stop),'half_hour_rows':len(half),
    'pilot_over20_reduction_percent':-percent(decision['over20_before'],decision['over20_after']),
    'pilot_law_transfer_arrivals_reduction_percent':-percent(decision['afternoon_snu_transfer_arrivals_before'],decision['afternoon_snu_transfer_arrivals_after']),
    'broader_reference':'261116010854','broader_over20_before':math.fsum(over(a) for a,b in matched),
    'broader_over20_after':math.fsum(over(b) for a,b in matched),'broader_max_wait_before':max(maximum(a) for a,b in matched),
    'broader_max_wait_after':max(maximum(b) for a,b in matched),
    'new_date_accuracy':'NOT_EVALUATED_FOR_THIS_CANDIDATE','operating_adoption_recommended':False,'production_writes':False}
save(w/'final-review-metrics.json',summary)
s=[f'# R{w.name}: 법대 환승 집중 개선 검토','',
    '**공개 V11은 유지했습니다.** 이 문서의 결과는 별도 개발·검증 후보 R'+w.name+'의 결과이며 배포나 운영 승격 결과가 아닙니다. 내부 시각 식별자·기존 V12 계열 이름은 과거 비교를 위해 바꾸지 않았습니다.','',
    '법대로 설입행 환승 수요가 몰린 원인은 두 가지였습니다. 일부 5511 직통이 경로 확장에서 빠졌고, 접근편을 타는 경로는 법대에 도착한 뒤의 정상 배차 대기조차 0으로 평가했습니다. 직통 경로만 복원한 G는 성과 기준을 넘지 못했습니다. 이번에는 사용자 확인대로 **평소 배차는 예상하되 미래 환승지의 줄·만차는 모르는 선택**을 구현했습니다.',
    '초기 점수의 끝을 주노선 정류장 도착에서 주노선 승차까지 맞췄습니다. 첫 버스 평균 대기와 후속 배차 시간대의 시각 기준도 맞췄으며, 정류장에서 실제로 기다리는 중의 재검토 시각은 유지했습니다. 수요·행선지·운행·정원·보행·인내·선호 수치 46개는 바꾸지 않았습니다.','',
    '## 월·화 기본 운행의 직접 비교','',
    '수정 전은 직전 비공개 후보 G261116153200입니다. 공개 V11 대비 수치로 혼동하지 마십시오.','',
    '|지표|G → R|','|---|---:|',
    f"|15~20시 설입행 이전 버스 이용 후 법대 누적 도착, 가중량|{decision['afternoon_snu_transfer_arrivals_before']:.2f} → {decision['afternoon_snu_transfer_arrivals_after']:.2f} ({summary['pilot_law_transfer_arrivals_reduction_percent']:.1f}% 감소)|",
    f"|월·화 오후 법대 양방향 최대 줄, 명 상당|{decision['afternoon_law_max_before']:.2f} → {decision['afternoon_law_max_after']:.2f}|",
    f"|전체 기록의 20분 초과 가중 대기 구간 합|{decision['over20_before']:.2f} → {decision['over20_after']:.2f} ({summary['pilot_over20_reduction_percent']:.1f}% 감소)|",
    f"|최대 연속 대기, 분|{decision['max_wait_before']:.2f} → {decision['max_wait_after']:.2f}|",
    f"|재사용 4관측 기대 절대오차 합|{decision['field_error_sum_before']:.2f} → {decision['field_error_sum_after']:.2f}|",'',
    '법대 누적 도착·대기 구간은 고유 학생 수가 아닙니다. 20분 초과는 모든 정류장·모든 기록 시간이며, 오후 법대 최대는 15~20시입니다.','',
    '|관측 시각·장소|관측|분 평균 예측 G → R|기대 오차 G → R|','|---|---:|---:|---:|']
obs={'16:53':('행정관','53'),'16:55':('문화관','5'),'17:03':('정문 21128','33~39'),'15:23':('행정관','67')}
for r in decision['observations']:
    name,actual=obs[r['minute']]
    s.append(f"|{r['minute']} {name}|{actual}|{r['old_mean']:.2f} → {r['new_mean']:.2f}|{r['old_error']:.2f} → {r['new_error']:.2f}|")
s+=['','측정 초가 알려지지 않은 분을 균등 적분한 비교입니다. 같은 4건을 재사용했으므로 독립적인 정확도 검증으로 부르지 않습니다.','',
    '## 왜 정문 예측이 달라졌는가','',
    '정문 16:30~17:04의 유입−승차 질량 보존을 확인했습니다. 버스 시각·차량·노선·정원은 같았고, 경로 선택이 바뀌면서 정문 유입이 달라졌습니다.','',
    '|모형|누적 정문 유입|그중 처음 선택한 경로|경로 변경 후 유입|누적 승차|','|---|---:|---:|---:|---:|']
for r in mechanism['gate_mass_balances']:
    z=r['flow'];s.append(f"|{r['model']}|{z.get('arrivals',0):.2f}|{z.get('arrivals_initial_plan',0):.2f}|{z.get('arrivals_after_route_change',0):.2f}|{z.get('exit_boarded',0):.2f}|")
s+=['','정문 줄 관측 한 건으로 실제 정문 유입과 외부 승객이 차지한 좌석을 따로 식별할 수는 없습니다. 외부 승객을 임의로 넣거나 버스 공급을 줄여 오차를 맞추지 않았습니다.','',
    '## 완료한 모든 요일·운행의 오후 법대','',
    'regular/peak는 동결된 기본/피크 운행 시나리오입니다. 각 행의 최대는 해당 날짜의 실측값이 아니라 합성 수요의 모의 결과입니다. 40명은 회상 점검값이며 상한이 아닙니다.','',
    '|요일·운행|설입 방향 21298 최대 줄|그 시각|40명 초과 누적분|반대쪽 21270 최대 줄|','|---|---:|---|---:|---:|']
for r in law:
    a=next(z for z in r['law_profiles'] if z['node']==60);b=next(z for z in r['law_profiles'] if z['node']==47);t=a['peak_seconds']
    clock=f'{int(t//3600):02}:{int(t%3600//60):02}' if a['maximum_queue'] else '-'
    s.append(f"|{r['case']['day']}·{r['case']['scenario']}|{a['maximum_queue']:.2f}|{clock}|{a['minutes_above40']:.2f}|{b['maximum_queue']:.2f}|")
s+=['','## 남은 20분 초과와 악화 지점','',
    '20분을 넘는 대기는 남아 있습니다. 개인차를 유지한 인내 기준은 중앙값 20분이며, 그 기준을 넘으면 경로를 다시 검토하되 더 나은 대안이 없으면 계속 기다릴 수 있습니다. 모형의 오차 신호와 개인 기준 초과를 구분해 분석했습니다.','',
    '|모형·요일|원시 20분 초과 방문|개인 기준 이내|개인 기준도 초과|','|---|---:|---:|---:|']
for r in mechanism['models']:
    if r['model']!=w.name:continue
    z=r['raw_visit_wait_categories'];s.append(f"|R{w.name}·{r['day']}|{z.get('over20',0):.2f}|{z.get('within_personal',0):.2f}|{z.get('beyond_personal',0):.2f}|")
s+=['','원시 방문은 연속 대기 구간과 달라질 수 있으며 고유 학생 수가 아닙니다. 최대 대기·개인 기준·최초 예상·실제 만차 이력은 [원인 원장](mechanism-diagnosis.json)에 남겼습니다.',
    '전체 개선이 모든 정류장의 개선을 뜻하지는 않습니다. 악화와 개선이 큰 정류장을 [상세 진단](MECHANISM_DIAGNOSIS_v2.md)에 함께 표시했습니다. 문화관과 화요일 행정관의 관측 오차, 일부 법대의 40명 초과, 아직 검증하지 않은 외부 승객·실등록 정원·실제 귀가 수요 문제도 남았습니다. 40명 절단이나 20분 강제 이탈로 숨기지 않았습니다.','',
    '## 전체 기록 검산과 범위','',
    f"본실험 {len(main)}조건, 시간 기준 OFF 진단 1조건을 각 한 번 완료했습니다. 활성163검사·기존89검사·충성5점검, 수요·FIFO·정원·경로 행동 검사와 대조 재현을 통과했습니다. 정류장 {len(nodes)}곳의 모든 기록 대기를 확인했고, {len(all_stop)}행의 정류장 요약과 {len(half)}행의 30분별 진입 집단 표를 만들었습니다. 30분 표는 줄에 들어온 시각으로 묶은 대기시간이며, 순간 줄 크기 표와 다릅니다.",
    f"전요일이 있는 기존 기준261116010854와 같은 조건 묶음의 20분 초과 합은 {summary['broader_over20_before']:.2f} → {summary['broader_over20_after']:.2f}, 최대 연속 대기는 {summary['broader_max_wait_before']:.2f} → {summary['broader_max_wait_after']:.2f}분입니다. 이 넓은 비교에는 이전 변경도 포함되므로 이번 수정 하나의 인과 효과는 월·화의 G 대조로 판단합니다.",
    '이전 후보 G와 I의 실행·실패·결과를 보존했습니다. I261116160639은 성과 자체는 통과했지만 초기 시간 기준 문제로 확대 제외했고, R에서만 바로잡았습니다. 처음 검토한 동일 주노선 하류 접근의 0.08 가중치 확장 초안은 실행하거나 결합하지 않았습니다.',
    '새 날짜 결과를 이 후보 선택에 사용하지 않았습니다. 다른 채팅의 별도 실측 운행 보강 후보도 아직 결합하지 않았습니다. 독립 날짜 검증과 운영 연결·화면 성능 검증은 남았으며, 공개 모델을 교체하지 않았습니다.','',
    '## 검토 파일','',
    '[결과 본문](RESULTS.md), [가정·자료·출처](SOURCES_AND_ASSUMPTIONS.md), [전 정류장 대기]('+group+'-all-recorded-stops.csv), [30분별 대기]('+group+'-all-recorded-half-hour-waits.csv), [모든 요일 법대]('+group+'-law-transfer-metrics.json), [불리한 지점 포함 원인 분석](MECHANISM_DIAGNOSIS_v2.md), [고정 입력·행동·대조·공개 상태 검산](artifact-verification.json).','']
target=w/'FINAL_REVIEW.md';assert not target.exists();target.write_text('\n'.join(s),encoding='utf8')
links=0
for href in re.findall(r'\]\(([^)]+)\)',target.read_text(encoding='utf8')):
    assert (w/href).resolve().exists(),href;links+=1
save(w/'TEAM_PACKAGE_FINAL.json',{'display_name':'R'+w.name,'release_id':w.name,'entry_point':'FINAL_REVIEW.md','created_at':datetime.now(timezone.utc).isoformat(),
    'main_cases':len(main),'diagnostic_cases':1,'original_package_sha256':sha(w/'TEAM_PACKAGE.json'),
    'documents_sha256':{n:sha(w/n) for n in ['FINAL_REVIEW.md','final-review-metrics.json','MECHANISM_DIAGNOSIS_v2.md','mechanism-diagnosis.json']},
    'links_checked':links,'public_model_preserved':'V11 261110162302','public_readback_all_passed':proof['public_readback_all_passed'],
    'new_date_accuracy':'NOT_EVALUATED_FOR_THIS_CANDIDATE','operating_adoption_recommended':False,'production_writes':False})
print('FINAL_REVIEW_COMPLETE','R'+w.name,summary,flush=True)
