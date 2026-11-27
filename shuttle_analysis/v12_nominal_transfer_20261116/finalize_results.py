"""Verify owned one-shot results, then prepare a reviewable private team package."""
from pathlib import Path
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor
import csv,gzip,hashlib,importlib.util,json,math,re,subprocess,sys,time
ROOT=Path(__file__).resolve().parent;A=ROOT.parent
w=Path(json.loads((ROOT/'candidate.json').read_bytes())['path']);P=A/'261116153200'
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def csvrows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
def write(p,t):
    assert not p.exists(),p
    p.write_text(t,encoding='utf8')
def save(p,d):write(p,json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def run(name,*args):
    log=w/(name.removesuffix('.py')+'-finalization.log');assert not log.exists()
    with log.open('x',encoding='utf8') as f:r=subprocess.run([sys.executable,'-X','utf8',str(ROOT/name),str(w),*args],stdout=f,stderr=subprocess.STDOUT)
    assert r.returncode==0,(name,r.returncode)
    print('ANALYZED',name,flush=True)
deadline=time.monotonic()+7200
while True:
    state=(w/'workflow.log').read_text(encoding='utf8') if (w/'workflow.log').exists() else ''
    if 'STOP_PRESERVE_PILOT_RESULTS' in state or 'GRID_ANALYSIS_TABLES_COMPLETE' in state:break
    assert not list((w/'runs').glob('*/attempt_01/failure.json')),'Preserve consumed failure; inspect it'
    assert time.monotonic()<deadline
    time.sleep(10)
decision=read(w/'pilot-decision.json');group='grid' if decision['status']=='PILOT_QUALIFIED' else 'pilot'
run('diagnose_waits.py','--group','pilot')
src=(ROOT/'stop_queue_exposure.py').read_text(encoding='utf8')
src=src.replace('grid-stop-queue-exposure.csv','pilot-stop-queue-exposure.csv').replace('grid-validation.json','pilot-validation.json')
src=src.replace('assert len(rows)==990','assert len(rows)==297').replace("w/'prediction-information-audit.json'","w/'pilot-prediction-information-audit.json'")
write(ROOT/'pilot_stop_queue_exposure.py',src);run('pilot_stop_queue_exposure.py')
v=read(w/f'{group}-validation.json');pilot=read(w/'pilot-validation.json')['results']
main=[r for r in v['results'] if not r['case']['case'].startswith('ablation')]
assert len(main)==(10 if group=='grid' else 2)
original=read(A/'261116010854/grid-validation.json')['results']
parent=[r for r in read(P/'pilot-validation.json')['results'] if not r['case']['case'].startswith('ablation')]
over=lambda r:r['extended_diagnostics']['all_recorded_time_over20_episode_weight']
maximum=lambda r:r['extended_diagnostics']['all_recorded_time_max_continuous_wait_min']
quant=lambda r:r['extended_diagnostics']['finished_trip_quantiles']['total_min']
manifest=read(w/'repair_manifest.json');future=read(w/'future_evaluation_plan.json');cfg=read(w/'config.json');count=0
for path,h in manifest['protected'].items():assert sha(Path(path))==h,path;count+=1
for n,h in manifest['frozen_payloads'].items():assert sha(w/n)==sha(P/n)==h,n;count+=1
for n,h in future['frozen_sha256'].items():assert sha(w/n)==h,n;count+=1
protocol=read(w/'protocol-reference.json');assert sha(Path(protocol['path']))==protocol['sha256']
priorcfg=read(P/'config.json');numeric={k:v for k,v in priorcfg.items() if type(v) in (int,float)}
assert all(cfg[k]==v for k,v in numeric.items())
units={}
for name,expected in [('enabled-final.log',159),('legacy-final.log',89)]:
    t=(w/name).read_text(encoding='utf8');ns=re.findall(r'Ran (\d+) tests?',t)
    assert len(ns)==1 and int(ns[0])==expected and re.search(r'^OK\s*$',t,re.M);units[name]=expected
assert read(w/'loyalty-invariant-check.json')['status']=='PASS'
assert read(w/'preparation-catalog-audit.json')['status']=='PASS_PREPARATION_ONLY'
assert read(w/'static-scope-proof.json')['status']=='PASS_STATIC_SCOPE'
assert read(w/f'{group}-behavior-validation.json')['status']=='PASS_STUDENT_BEHAVIOR_GATES'
folders=list((w/'runs').glob('*/attempt_01'));assert len(folders)==len(main)+1
profiles=[];information=[]
for folder in folders:
    start=read(folder/'started.json');result=read(folder/'result.json');case=start['case']
    assert result['status']=='COMPUTED_NOT_EMPIRICALLY_VALIDATED'
    assert start['experiment_lock_sha256']==sha(w/'experiment_lock.json')
    assert start['input_manifest_sha256']==sha(w/'input_manifest.json') and len(start['code_sha256'])==19
    for n,h in start['code_sha256'].items():assert sha(w/n)==sha(folder/'source_snapshot'/n)==h;count+=2
    effective={**cfg,'seed':case['seed'],'operations':case['operations'],**case.get('config_overrides',{}),
        'physics':'path_local_4p8','behavior':'sequential','origin_choice':True,'boarding_choice':True}
    assert start['config']==effective
    old=next(x for x in original if (x['case']['day'],x['case']['scenario'])==(case['day'],case['scenario']))
    a=read(Path(old['source_directory'])/'result.json')['policy_report']['student_strategy']
    b=result['policy_report']['student_strategy']
    assert set(a['initial_mode_weights'])==set(b['initial_mode_weights'])
    assert all(abs(v-b['initial_mode_weights'][k])<1e-6 for k,v in a['initial_mode_weights'].items())
    assert a['patience_draw_sample']==b['patience_draw_sample']
    assert b['initial_trunk_checks'].get('violation_weight',0)==0
    assert result['policy_report']['catalog_repair']['restored_count']==5
    profiles.append({'case':case['case'],'initial_mode_mass_unchanged':True,'patience_draws_unchanged':True})
    information.append({'case':case['case'],'enabled':effective['anticipated_transfer_headways'],
        'initial':result['policy_report']['nominal_transfer_initial'],'review':result['policy_report']['nominal_transfer_review']})
diag=next(r for r in pilot if r['case']['case'].startswith('ablation'))
ref=next(r for r in parent if r['case']['day']=='화')
values=lambda r:[over(r),maximum(r),*quant(r).values()]
errors=[abs(a-b) for a,b in zip(values(diag),values(ref))];assert max(errors)<1e-6
save(w/'transfer-information-audit.json',{'status':'PASS','cases':information,
    'scope':'New headway references never read queue/capacity; inherited known/historical crowd context retained. Physical availability and ETA are audited separately.',
    'normal_wait_phase_removed':True,'source_calendars_are_scenarios_not_future_observations':True})

# Fixed old law-peak sample: a synthetic trace, not newly observed students.
on=next(r for r in pilot if r['case']['day']=='화' and not r['case']['case'].startswith('ablation'))
report=lambda model,case:read(model/'runs'/case/'attempt_01/result.json')['policy_report']['initial_policy_diagnostics']
oldrows={r['uid']:r for r in report(P,ref['case']['case'])};newrows={r['uid']:r for r in report(w,on['case']['case'])}
focus=read(A/'v12_law_snu_followup_20261116/law-snu-cohort-trace.json')['latest_focus_uid_weights'];traces=[]
for uid,weight in focus.items():
    a=oldrows.get(int(uid));b=newrows.get(int(uid))
    if a is None or b is None:continue
    traces.append({'uid':int(uid),'weight':weight,'old_primary_node':a['selected_primary_node'],'new_primary_node':b['selected_primary_node'],
        'old_first_node':a['selected_first_node'],'new_first_node':b['selected_first_node']})
focus_change=math.fsum(r['weight'] for r in traces if r['old_primary_node']==60 and r['new_primary_node']!=60)
save(w/'initial-choice-comparison.json',{'matched':len(traces),'total_focus_weight':math.fsum(x['weight'] for x in traces),
    'old_law_primary_new_elsewhere_weight':focus_change,'rows':traces,'scope':'Fixed prior F peak sample, G vs clarified child; not a population estimate or field evidence.'})

# Public GETs only. No publish command, active pointer write or UI mutation.
spec=importlib.util.spec_from_file_location('readback',A/'261112111627/verify_production_unchanged_v2.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
lab='https://snu-shuttle-simulation.vercel.app/';rel=f'routing-model/releases/{mod.MODEL}.json'
jobs=[('lab_latest',lab+'routing-model/latest.json'),('lab_payload',lab+rel),('data_payload','https://snu-shuttle-v9-data.vercel.app/'+rel),
    ('route_api','https://snu-route-lab.vercel.app/api/queue-model')]+[(n,lab+n) for n in ['index.html','viewer-v5.js','mobile-lab.js','mobile-lab.css']]
with ThreadPoolExecutor(max_workers=4) as pool:public=list(pool.map(mod.fetch,jobs))
save(w/'artifact-verification.json',{'status':'PASS_RESULT_INTEGRITY','hash_checks':count,'runtime_modules':19,'fixed_payloads':len(manifest['frozen_payloads']),
    'future_source_hashes':len(future['frozen_sha256']),'actual_single_attempt_cases':len(folders),'main_cases':len(main),'diagnostic_cases':1,
    'unit_tests':units,'loyalty_guards':5,'initial_profile_checks':profiles,'disabled_parent_metric_errors':errors,
    'existing_numeric_parameters_unchanged':numeric,'public_readback':public,'public_readback_all_passed':all(x['check']=='PASS' for x in public),
    'expected_public_model':mod.MODEL,'checked_at':datetime.now(timezone.utc).isoformat(),'new_date_accuracy':'NOT_EVALUATED','production_writes':False})

law=read(w/'pilot-law-transfer-metrics.json')['cases'];oldlaw=read(w/'parent-law-reference.json')['cases']
s=[f'# 법대 환승 집중과 긴 대기: 배차 인지 수정 {w.name}','',
    f"사전 월·화 판정: **{decision['status']}**. 공개 V11은 유지했고 별도 후보에서 비교했습니다. 숫자계수 46개, 수요·목적지·운행·물리모형은 부모 G와 같습니다.",'',
    '## 왜 법대로 몰렸는가','',
    '첫째, 기존 경로 확장에서 같은 노선·승차지의 직통과 셔틀 환승 꼬리를 하나로 줄여 일부 5511 직통이 빠졌습니다. 부모 G는 기존 자료 안의 직통 5개를 복원했습니다. 그러나 직통 복원만으로 월·화 20분 초과 대기 합이 582.003→583.948로 조금 늘어 채택하지 않았습니다.',
    '둘째, 환승 뒤 대기를 모두 0으로 빼면 직통은 주노선에 **타는 시각**, 접근편 경로는 주노선 정류장에 **도착하는 시각**으로 비교됩니다. 법대에 빨리 데려다주는 5516→5511이 법대에서의 정상적인 배차 대기조차 부담하지 않아 유리해졌습니다. 사용자 확인은 평소 배차간격은 감안하고, 환승지의 줄·만차는 미리 예상하지 않는다는 뜻이었습니다.',
    '이번 후보는 정상 배차 기대 대기와 기존 준비시간을 반영하여 주노선 승차까지 비교합니다. 초기와 이후 재검토의 인지 범위를 맞추되 실제 승하차·정원·FIFO·전체 도착시간은 원래 사건 모형으로 계산합니다. 별도의 동일 주노선 0.08 가중치 확장 초안은 실행하지 않았습니다.','',
    '## 같은 월·화 기본 운행: 부모 G와의 직접 비교','',
    '|지표|수정 전 → 후|','|---|---:|',
    f"|20분 초과 가중 대기 구간 합|{decision['over20_before']:.3f} → {decision['over20_after']:.3f}|",
    f"|최대 연속 대기, 분|{decision['max_wait_before']:.3f} → {decision['max_wait_after']:.3f}|",
    f"|15~20시 법대 양방향 최대 줄, 명 상당|{decision['afternoon_law_max_before']:.3f} → {decision['afternoon_law_max_after']:.3f}|",
    f"|15~20시 설입행, 이전 버스 탑승 후 법대 누적 도착|{decision['afternoon_snu_transfer_arrivals_before']:.3f} → {decision['afternoon_snu_transfer_arrivals_after']:.3f}|",
    f"|재사용 4관측 기대 절대오차 합|{decision['field_error_sum_before']:.3f} → {decision['field_error_sum_after']:.3f}|",
    f"|월·화 평균 총시간 변화, 분|{decision['mean_journey_delta_minutes'][0]:+.3f} / {decision['mean_journey_delta_minutes'][1]:+.3f}|",'',
    '누적 도착량·대기 구간은 가중 방문량으로 고유 학생 수가 아닙니다. 40명은 회상에 따른 점검 기준이며 줄을 잘라내는 상한으로 사용하지 않았습니다.','',
    '|요일·법대 ARS|오후 최대 줄 전 → 후|40명 초과 누적분 전 → 후|','|---|---:|---:|']
for b in law:
    if b['case']['case'].startswith('ablation'):continue
    a=next(r for r in oldlaw if r['case']['day']==b['case']['day'])
    for z in b['law_profiles']:
        before=next(r for r in a['law_profiles'] if r['node']==z['node']);ars=21270 if z['node']==47 else 21298
        s.append(f"|{b['case']['day']}·{ars}|{before['maximum_queue']:.3f} → {z['maximum_queue']:.3f}|{before['minutes_above40']:.3f} → {z['minutes_above40']:.3f}|")
s+=['','## 정문과 기존 관측','',
    '분 안의 정확한 측정 초는 모르는 것으로 두고 분 전체의 예측을 적분했습니다. 다음 4건은 이미 여러 후보에 사용한 자료이며 독립적인 정확도 검증은 아닙니다.','',
    '|시각|관측 장소|분 평균 예측 전 → 후|기대 절대오차 전 → 후|','|---|---|---:|---:|']
names={'16:53':'행정관, 관측 53','16:55':'문화관, 관측 5','17:03':'정문 21128, 관측 33~39','15:23':'행정관, 관측 67'}
for r in decision['observations']:s.append(f"|{r['minute']}|{names.get(r['minute'],'')}|{r['old_mean']:.3f} → {r['new_mean']:.3f}|{r['old_error']:.3f} → {r['new_error']:.3f}|")
s+=['','## 완료한 요일·운행 조건','',
    '아래의 넓은 비교 기준 261116010854는 모든 요일이 있습니다. 부모 G의 직접 비교가 있는 조건은 월·화 기본 운행뿐이므로 다른 요일 차이를 이번 수정 하나의 효과로 해석하지 않습니다.','',
    '|요일·운행|평균 총시간 전 → 후, 분|20분 초과 가중 구간 전 → 후|최대 대기 전 → 후, 분|','|---|---:|---:|---:|']
for r in main:
    a=next(x for x in original if (x['case']['day'],x['case']['scenario'])==(r['case']['day'],r['case']['scenario']))
    s.append(f"|{r['case']['day']}·{r['case']['scenario']}|{quant(a)['mean']:.3f} → {quant(r)['mean']:.3f}|{over(a):.3f} → {over(r):.3f}|{maximum(a):.3f} → {maximum(r):.3f}|")
s+=['','## 남은 대기와 한계','',
    '20분은 이상 징후를 살피는 기준입니다. 개인별 인내 기준을 넘으면 재검토하지만, 대안이 더 나쁘면 계속 기다릴 수 있습니다. 인내의 중앙값 20분과 기존 분산을 유지했으므로 20분 초과가 전부 사라진다고 가정하지 않습니다. 전체 정류장·전체 시각의 연속 대기와 30분 진입 집단을 별도 표로 남겼습니다.',
    '정문 과소예측은 도착 수요와 버스 공급·잔여 좌석의 공동 결과입니다. 경로 인지만으로 남은 오차 전체를 설명할 수는 없습니다. 교외에서 들어오는 승객은 물리 수요에 추가하지 않았고, 혼잡등급을 임의 인원으로 바꾸지도 않았습니다. 일반 50명·마을 24명 정원과 수업 종료 후 실제 귀가 비율도 남은 가정입니다.',
    f'기존 법대 피크 표본 {len(traces)}개 합 {math.fsum(r["weight"] for r in traces):.3f}명 상당 중, 초기 주노선 승차지를 법대 밖으로 바꾼 가중량은 {focus_change:.3f}입니다. 이는 고정 합성 표본 추적이며 실측 학생 비율이 아닙니다.',
    f'실행은 본실험 {len(main)}조건과 OFF 진단 1조건입니다. 미통과 항목은 [사전 판정](pilot-decision.json)에 모두 남겼습니다. 새 날짜 실측 결과는 열지 않았으며 공개 모델 교체나 배포는 하지 않았습니다.','',
    '## 검산과 원자료 연결','',
    f'[정류장 전체 대기]({group}-all-recorded-stops.csv), [30분별 대기]({group}-all-recorded-half-hour-waits.csv), [오후 법대]({group}-law-transfer-metrics.json), [긴 대기 원인](pilot-wait-cause-ledger.json), [고정 표본 초기 선택](initial-choice-comparison.json), [입력·출처·가정](SOURCES_AND_ASSUMPTIONS.md), [보존·대조 재현 검산](artifact-verification.json).','']
write(w/'RESULTS.md','\n'.join(s))
source='''# 자료·가정·출처

사용한 자료는 기존에 동결한 수업 종료·가중 학생 계획, 물리 경로, 버스 운행 자료와 이미 재사용한 4건의 줄 관측입니다. 이번에 개별 학생의 실제 거주지·당일 마지막 수업·실제 하교 경로를 새로 확보한 것은 아닙니다.

- [수업 종료 추출](frozen/class_endings_source_20261106.json), [가중 학생·경로](frozen/prepared_capacity44_pair.json.gz), [기존 실측 운행 맥락](frozen/operations_v12_empirical.json), [실측 근거 목록](frozen/empirical_evidence.json).
- [셔틀 44명 수정 근거](capacity44_amendment.json), [피크 편성 가정](pair_amendment.json)을 계승했습니다. 일반 50명·마을 24명은 노선별 실등록 정원 확인이 남아 있습니다. 실제 혼잡등급을 인원으로 환산하지 않았고 교외 배경 승객을 물리 수요로 더하지 않았습니다.
- 관측: 월요일 대응 16:53 행정관 53명, 16:55 문화관 5명(방향 미상), 17:03 정문 설입 방향 21128의 33~39명, 화요일 15:23 줄 합류 67명(본인 포함). 분 안의 초는 균등 적분했습니다. 날짜·방향의 기존 불확실성은 유지합니다. 화요일 승차 189초·44명 두 대 중 두 번째라는 기존 정정도 계승했습니다.

이번 사용자의 확인은 ‘평소 배차간격은 감안하지만, 그곳의 줄·만차는 미리 예상하지 않음’입니다. 수정은 이 정보 범위를 적용한 것입니다. 법대에 도착한 뒤 정상 대기를 0으로 처리하지 않고, 접근 중간과 주노선 승차에 필요한 정상 배차 기대를 넣습니다. 주노선 승차 후 총 도착시간을 최소화하는 초기 선택으로 바꾸지는 않았습니다.

기대 대기는 같은 외생 운행 달력의 호환 서비스 도착을 모아 시간별 간격 h에 대해 sum(h²)/(2sum(h))로 계산합니다. 구간 h 안에 균등하게 도착한다고 가정하면 대기시간의 면적이 h²/2이므로, 전체 시간으로 나눈 값입니다. 이는 무작위 도착·배차 인지라는 모형 가정이며 서울대 학생의 실제 기대 대기를 새로 측정한 값이 아닙니다. 해당 시간 간격이 없으면 하루 전체 간격으로 대체하며 단 하나의 출발만 있으면 배차를 지어내지 않습니다. 기존 20초 준비는 유지합니다.

새 배차 참조는 미래 줄·만차·정확한 다음 출발 위상을 사용하지 않습니다. 기존의 경로 실행 가능성·탑승 노선과 물리 운행 시각, 현재 알려진 혼잡/과거 혼잡 맥락은 그대로입니다. 경로 선택을 위한 인지 예측과 실제 운영 예측·실행 결과를 구분합니다.

셔틀 충성·개인차, 실제 만차 경험, 현재 정류장의 압력에서 변경 재검토, 이미 간 정류장 복귀 금지, 정문 최종 대안, 기숙사 도보, 도보 중 합법적 승차, 무제한 경로 변경과 반복 변경 후 도보 성향을 유지합니다. 수요·목적지·개인 선호·운행·속도·정원·인내의 수치계수 46개는 부모 G와 같습니다. 20분 강제 이탈이나 40명 상한은 없습니다.

기존 직통 5개 복원은 부모 G에서 계승했습니다. 동일 주노선 하류 접근의 0.08 가중치 확장 초안 261116160157은 실행하지 않았고 이번 후보에 포함하지 않았습니다. 과거 시험에서 수치가 불리했던 자료와 조건은 모두 보존했습니다.

새 날짜 자료는 가용성 확인과 결과 검증을 구분합니다. 다른 채팅이 확인한 최근 기록의 존재 자체는 독립 정확도 검증이 아닙니다. 이번 비교에서 그 새 날짜 원본 정답은 열지 않았습니다. 추후 검증은 동결한 모형으로 관측 범위·방향·시각을 맞춰야 합니다. 운영 채택이나 배포 검증은 별개입니다.
'''
write(w/'SOURCES_AND_ASSUMPTIONS.md',source)
intro=f'''# 배차 인지를 바로잡은 비공개 비교 {w.name}

기존 공개 V11은 유지했습니다. 이번 후보는 환승 뒤의 대기를 통째로 빼던 부분에 평소 배차간격을 반영합니다. 미래 환승지의 줄·만차는 미리 알지 못합니다. 수요·배차·정원·개인차를 맞춰서 결과를 만들지 않았습니다.

월·화 사전 판정은 **{decision['status']}**입니다. 20분 초과 가중 대기 구간은 {decision['over20_before']:.3f}→{decision['over20_after']:.3f}, 오후 법대 최대 줄은 {decision['afternoon_law_max_before']:.3f}→{decision['afternoon_law_max_after']:.3f}명 상당입니다. 본실험 {len(main)}조건과 OFF 진단 1조건을 완료했습니다.

- [원인·법대·정문·요일별 결과와 남은 문제](RESULTS.md)
- [자료·가정·출처](SOURCES_AND_ASSUMPTIONS.md)
- [사전 판정과 악화 항목](pilot-decision.json)
- [실행·고정 입력·모드/개인차·대조 재현·공개 상태 검산](artifact-verification.json)
- [전체 정류장 대기]({group}-all-recorded-stops.csv)
- [정류장·30분별 대기]({group}-all-recorded-half-hour-waits.csv)

재사용 관측에 대한 모의 비교이며 독립 날짜 정확도는 미평가입니다. 가중 대기 구간·누적 도착·한 시점의 줄은 서로 다른 지표입니다. 공개 모델 교체나 사이트 배포는 하지 않았습니다.
'''
write(w/'START_HERE.md',intro)
links=0
for n in ['START_HERE.md','RESULTS.md','SOURCES_AND_ASSUMPTIONS.md']:
    for href in re.findall(r'\]\(([^)]+)\)',(w/n).read_text(encoding='utf8')):
        if href.startswith(('http://','https://','#')):continue
        assert (w/href).resolve().exists(),(n,href);links+=1
names=['START_HERE.md','RESULTS.md','SOURCES_AND_ASSUMPTIONS.md','artifact-verification.json','pilot-decision.json','initial-choice-comparison.json','transfer-information-audit.json']
save(w/'TEAM_PACKAGE.json',{'release_id':w.name,'entry_point':'START_HERE.md','created_at':datetime.now(timezone.utc).isoformat(),
    'document_sha256':{n:sha(w/n) for n in names},'links_checked':links,'main_cases':len(main),'diagnostic_cases':1,
    'pilot_status':decision['status'],'new_date_accuracy':'NOT_EVALUATED','operating_adoption_recommended':False,'production_writes':False})
print('FINAL_REPORT_AND_VERIFICATION_COMPLETE',w.name,flush=True)
