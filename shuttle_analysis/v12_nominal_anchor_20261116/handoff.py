"""Final integrity receipt and concise handoff; no simulation or publication."""
from pathlib import Path
from datetime import datetime,timezone
import csv,hashlib,json,math,re
ROOT=Path(__file__).resolve().parent;w=Path(json.loads((ROOT/'candidate.json').read_bytes())['path'])
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,d):
    assert not p.exists(),p
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
for pkg in ['TEAM_PACKAGE_FINAL.json','TEAM_PACKAGE_ALL_STOPS.json']:
    d=read(w/pkg)
    for n,h in d['documents_sha256'].items():assert sha(w/n)==h,n
proof=read(w/'artifact-verification.json');assert proof['public_readback_all_passed']
manifest=read(w/'repair_manifest.json');future=read(w/'future_evaluation_plan.json');checks=0
for p,h in manifest['protected'].items():assert sha(Path(p))==h,p;checks+=1
for n,h in manifest['frozen_payloads'].items():assert sha(w/n)==h,n;checks+=1
for n,h in future['frozen_sha256'].items():assert sha(w/n)==h,n;checks+=1
folders=list((w/'runs').glob('*/attempt_01'));assert len(folders)==11
for folder in folders:
    start=read(folder/'started.json');assert start['experiment_lock_sha256']==sha(w/'experiment_lock.json')
    for n,h in start['code_sha256'].items():assert sha(w/n)==sha(folder/'source_snapshot'/n)==h,n;checks+=2
assert not list((w/'runs').glob('*/attempt_02')) and not list((w/'runs').glob('*/attempt_01/failure.json'))
v=read(w/'grid-validation.json')['results'];assert len(v)==10
assert all(r['status']=='PASS_INTERNAL_INVARIANTS' and r['unserved_trip_weight']==0 for r in v)
assert read(w/'grid-behavior-validation.json')['status']=='PASS_STUDENT_BEHAVIOR_GATES'
dec=read(w/'pilot-decision.json');summary=read(w/'final-review-metrics.json');allstops=read(w/'TEAM_PACKAGE_ALL_STOPS.json')
assert all(dec['checks'].values()) and max(dec['disabled_reproduction_absolute_errors'])<1e-6
waits=read(w/'grid-wait-cause-ledger.json')['cases'];raw=math.fsum(r['counts'].get('over20_episode_weight',0) for r in waits)
within=math.fsum(r['counts'].get('over20_within_personal_weight',0) for r in waits)
law=read(w/'grid-law-transfer-metrics.json')['cases'];q=list(csv.DictReader((w/'grid-stop-queue-exposure.csv').open(encoding='utf-8-sig')))
assert len(q)==990
interior=max(float(r['maximum_queue']) for r in q if r['ars'] in ['21269','21299'])
full_over=summary['broader_over20_after'];full_before=summary['broader_over20_before'];full_reduction=100*(1-full_over/full_before)
s=[f'# R{w.name} 최종 전달','',
    '**공개 V11을 유지한 비공개 개선 후보입니다.** 수요·행선지·운행·정원·보행·인내·선호 수치 46개를 바꾸지 않았습니다.','',
    '## 원인과 변경','',
    '법대 쏠림을 만드는 모형의 두 문제를 확인했습니다. 같은5511 승차에서 직통과 셔틀 접근을 하나로 축약해 직통 선택지가 빠졌고, 접근편 뒤 정상 배차 대기를0으로 빼서 법대에 도착하는 경로가 법대에서 주노선에 타는 경로보다 부당하게 유리했습니다.',
    '이미 있는 직통5개를 복원하고, 사용자 확인대로 평소 배차는 예상하되 미래 환승지의 줄·만차는 모르는 선택을 구현했습니다. 초기 첫 승차의 평균 시각과 후속 배차 시간대도 맞췄습니다. 실제 승하차·FIFO·정원·소요시간은 원래 물리 모형으로 계산합니다.',
    '셔틀 선호와 개인차, 반복 만차 뒤 재검토, 이미 떠난 승차지로 복귀 금지, 정문 최종 대안, 기숙사 도보·도보 중 승차, 무제한 경로 변경과 반복 후 도보 성향은 유지했습니다.20분 강제 이탈·40명 상한·새로운 같은 노선 가중치 규칙을 넣지 않았습니다.','',
    '## 월·화 기본 운행의 직접 효과','',
    '직전 비공개 후보G261116153200과 같은 두 조건 비교입니다. 공개V11 대비 효과나 실제 인원 변화로 해석하지 않습니다.','',
    '|지표|G → R|','|---|---:|',
    f"|15~20시 설입행 이전 버스 이용 후 법대 누적 도착, 가중량|{dec['afternoon_snu_transfer_arrivals_before']:.2f} → {dec['afternoon_snu_transfer_arrivals_after']:.2f} ({summary['pilot_law_transfer_arrivals_reduction_percent']:.1f}% 감소)|",
    f"|두 요일·양방향 중 오후 법대 최대 줄, 명 상당|{dec['afternoon_law_max_before']:.2f} → {dec['afternoon_law_max_after']:.2f}|",
    f"|모든 기록20분 초과 가중 대기 구간|{dec['over20_before']:.2f} → {dec['over20_after']:.2f} ({summary['pilot_over20_reduction_percent']:.1f}% 감소)|",
    f"|정문17:03 분 평균 예측, 관측33~39|17.53 → 33.86|",'',
    '정문은 버스 운행과 정원을 바꾸지 않은 채 유입 경로가 달라져 예측이 개선됐습니다. 누적 유입과 승차로 줄의 질량 보존을 확인했습니다.','',
    '## 전요일·전체 승차지','',
    f"평일5일×기본/피크 운행10조건과 시간 기준OFF 진단1조건을 각 한 번 완료했습니다. 모형 승차지99개·조건별990행과30분별 합류 집단11894행을 확인했습니다. 줄을 떠나 경로를 바꾼 학생의 대기도 포함했습니다. 미완료 이동과 정원 위반은0입니다.",
    f"전요일이 있는 초기 비교모형261116010854 대비20분 초과 가중 구간 합은 {full_before:.2f} → {full_over:.2f} ({full_reduction:.1f}% 감소), 최대 연속 대기는 {summary['broader_max_wait_before']:.2f} → {summary['broader_max_wait_after']:.2f}분입니다. 화·목 일부 조건은 그 초기 기준보다20분 초과가 늘었습니다. 이 넓은 비교에는 이전 변경도 포함되므로 이번 수정 하나의 인과 효과는 위의G월·화 대조로 구분합니다.",
    f"서울대정문 교내 양방향(21269/21299)의 전체 기록 최대는 {interior:.2f}명 상당입니다. 정문 바깥21128의 줄과 합치지 않았습니다. 법대는 오후 전요일 최대 {allstops['law_afternoon_maximum']:.2f}명으로40명 초과가 남습니다.",
    '전체 기록에는 표준 표시·집계 시작11:20 이전도 포함합니다. 월11:03의62.51명은 그 이전 내부 기록입니다. 반면 수18:04의50.15명은 오후 표준 시간창 안의 잔여 피크입니다. [시간 범위 구분](TIME_WINDOW_NOTE.md)을 함께 보십시오.','',
    '## 남은 문제와 이유','',
    '수요일18:04 법대50.15명은 설입행36.21·낙성대행13.34·기숙사행0.60명이 겹친 경우였습니다. 그중 설입행은 접근편 환승으로 유입한 사람이 아니었고, 모두 초기 경로 집단이었습니다. 피크 때 이미 기다린 시간은 평균5.66분·최대10.22분이었고, 뒤이어 온5511과관악02-2는 모형에서 만차였습니다. 도착 전에 만차를 모르는 행동을 유지하면 이런 일시적 줄이 남을 수 있습니다. [목적지 구성·버스 사건 원장](WEDNESDAY_RESIDUAL.md)에 확인 근거를 남겼습니다.',
    f"전요일 원시20분 초과 방문 {raw:.2f} 중 {within:.2f}는 모형의 개인별 인내 범위 안입니다. 이 범위를 실제 학생이 견딘다는 실측 증거는 아닙니다. 인내 분포는 기존 미측정 가정이며 기준을 넘으면 재검토하되 대안이 더 나쁘면 남을 수 있습니다. 개인 기준 초과 방문도 [원인 원장](grid-wait-cause-ledger.json)에 보존했습니다.",
    '문화관의 분 평균 예측1.16명(관측5), 화요일 행정관93.28명(관측67)의 오차도 남습니다. 외부 승객이 차지하는 자리, 실제 등록 정원, 수업 종료와 실제 마지막 수업 후 귀가의 차이도 검증이 더 필요합니다. 이 값을 임의로 조정해 숫자를 맞추지 않았습니다.','',
    '## 검증 상태와 후속 사용','',
    '활성163검사·기존89검사·충성5점검 및 전요일의 수요·FIFO·정원·학생 행동 검사를 통과했습니다. 초기 시각 수정OFF는 바로 전 후보I의 화요일을 정확히 재현했습니다. I는 성과 통과에도 시간 기준 문제 때문에 확대 제외하고 보존했고, 수정 자식R에서만 전요일을 비교했습니다. 알려진 입력·소스·이전 결과와 새 스냅샷 해시를 다시 확인했습니다.',
    '기존4관측을 재사용했으므로 독립 정확도 검증은 아닙니다. 별도 운행 보강R261116162001과 결합하지 않았고 그 후보의 신규 날짜 수치 결과를 이 후보 선택에 사용하지 않았습니다. 프로젝트 다른 채팅에서11월12일 기록을 개봉한 사실과 남은 날짜 범위는 [검증 범위 설명](VALIDATION_SCOPE_NOTE.md)에 기록했습니다.',
    '공개V11의 latest·모형데이터·경로API·화면파일은8개 읽기 검사에서 유지됐습니다. 운영 연결·새 날짜 독립 검증·화면 성능 확인은 남았으며, 이 전달은 배포나 운영 승격 요청이 아닙니다.','',
    '## 검토 파일','',
    '''- [요일·조건별 상세 비교](FINAL_REVIEW.md)
- [모든 승차지·시간대 점검](ALL_STOP_REVIEW.md)
- [수요일 오후 잔여 원인](WEDNESDAY_RESIDUAL.md)
- [표준 시간창 전 오전 구성](MORNING_RESIDUAL.md)
- [시간 범위 구분](TIME_WINDOW_NOTE.md)
- [새 날짜 검증 범위](VALIDATION_SCOPE_NOTE.md)
- [새 가정·자료·출처](SOURCES_AND_ASSUMPTIONS.md)
- [정류장별 전체 기록 대기](grid-all-recorded-stops.csv)
- [30분 합류 집단별 대기](grid-all-recorded-half-hour-waits.csv)
- [보존·대조 재현·공개 상태 검산](artifact-verification.json)
- [사전 성과 판정](pilot-decision.json)
''',
    '주요 구현은 [초기/재검토 행동](behavioral_policy.py), [평소 배차 대기 인지](nominal_transfer.py), [선택/물리 예측 분리](policy.py), [기존 직통 복원](direct_restoration.py)에 있습니다.','']
out=w/'FINAL_HANDOFF.md';assert not out.exists();out.write_text('\n'.join(s),encoding='utf8')
for href in re.findall(r'\]\(([^)]+)\)',out.read_text(encoding='utf8')):assert (w/href).resolve().exists(),href
names=['FINAL_HANDOFF.md','FINAL_REVIEW.md','ALL_STOP_REVIEW.md','WEDNESDAY_RESIDUAL.md','MORNING_RESIDUAL.md','TIME_WINDOW_NOTE.md',
    'VALIDATION_SCOPE_NOTE.md','SOURCES_AND_ASSUMPTIONS.md','wednesday-residual-diagnosis.json','morning-residual-diagnosis.json',
    'grid-all-recorded-stops.csv','grid-all-recorded-half-hour-waits.csv','artifact-verification.json','TEAM_PACKAGE_FINAL.json','TEAM_PACKAGE_ALL_STOPS.json']
save(w/'TEAM_PACKAGE_HANDOFF.json',{'display_name':'R'+w.name,'release_id':w.name,'entry_point':'FINAL_HANDOFF.md',
    'created_at':datetime.now(timezone.utc).isoformat(),'document_sha256':{n:sha(w/n) for n in names},'final_additional_hash_checks':checks,
    'main_cases':10,'diagnostic_cases':1,'all_cases_single_attempt':True,'all_main_unserved_weight':0,
    'public_model_preserved':'V11 261110162302','public_readback_checks':8,'public_readback_all_passed':True,
    'new_date_accuracy':'NOT_EVALUATED_FOR_THIS_CANDIDATE','operating_adoption_recommended':False,'production_writes':False})
print('HANDOFF_READY','R'+w.name,'hashes',checks,'files',len(names),'full_over20',full_before,full_over,flush=True)
