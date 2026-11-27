"""Write the final reviewed candidate report only after all predefined cells exist."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import argparse,csv,hashlib,json,math
ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
def num(x,d=2):return '—' if x is None else f'{x:.{d}f}'
def clock(t):return '—' if t is None else f'{int(t//3600):02}:{int(t//60)%60:02}'
def metric(r,key,side='prototype',scope='all'):
    m=r['scope'][scope]['metrics'];p=m.get(key+'_min',m.get(key+'_seconds',m.get(key)))
    return p[side]
def csvout(p,rows):
    assert rows
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)
def main(candidate,validation):
    candidate=Path(candidate).resolve();validation=Path(validation).resolve();target=ROOT/'RESULTS.md'
    assert not target.exists(),'Preserve a completed report; create a new version for later evidence'
    v=read(validation/'validation.json');lock=read(validation/'experiment_lock.json')
    assert Path(lock['parent_candidate']).resolve()==candidate and v['cases']==12 and v['main_grid']==10
    assert v['new_algorithm_promoted'] is False and v['empirical_status']=='NOT_EVALUABLE'
    for name,digest in v['runtime_code_sha256'].items():assert sha(candidate/name)==digest==sha(validation/name)
    mainnames={c['case'] for c in lock['all_weekday_main_cases']};primary=[r for r in v['results'] if r['case']['case'] in mainnames]
    order={c['case']:i for i,c in enumerate(lock['all_weekday_main_cases'])}
    primary.sort(key=lambda r:order[r['case']['case']])
    assert len(primary)==10
    basecsv=ANALYSIS/'simulation_viewer_2026-11-07/peak_pair_correction_2026-11-10/all_stops_waits.csv'
    with basecsv.open(encoding='utf-8-sig',newline='') as f:oldstops=list(csv.DictReader(f))
    summary=[]
    for r in primary:
        c=r['case'];day={'월':'mon','화':'tue','수':'wed','목':'thu','금':'fri'}[c['day']]
        ref=[p for p in oldstops if p['scenario']==c['scenario'] and p['weekday']==day];assert len(ref)==99
        summary.append({'weekday':c['day'],'scenario':c['scenario'],'case':c['case'],'input_trip_weight':r['scope']['all']['weight'],
            'baseline_total_min':metric(r,'total','baseline'),'candidate_total_min':metric(r,'total'),
            'baseline_wait_min':metric(r,'wait','baseline'),'candidate_wait_min':metric(r,'wait'),
            'baseline_walk_min':metric(r,'walk','baseline'),'candidate_walk_min':metric(r,'walk'),
            'baseline_max_stop_wait_min':max(float(p['max_continuous_wait_min']) for p in ref),
            'candidate_max_stop_wait_min':r['maximum_continuous_wait_min'],'over20_episode_weight':r['over20_weight'],
            'unserved_trip_weight':r['unserved_trip_weight'],'late_finished_weight':r['late_finished_weight'],'mean_changes':metric(r,'changes')})
    peaks=read(ROOT/'queue_peaks_by_window.json');assert len(peaks['rows'])==990
    named=[p for p in peaks['rows'] if p['stop'] in ('서울대정문','법대.사회대입구')];assert len(named)==40
    above=[p for p in named if p['window_max_queue']>40]
    # Same-physics old-behavior controls were already executed; never rerun them
    # merely to rebuild a table. CurrentMonday V8 is a new validation cell.
    factor=[];old=ANALYSIS/'prototype_followup_261110165541'
    for c in read(old/'experiment_lock.json')['pilot_cases']:
        if c['mode']!='physics':continue
        folder=old/'runs'/c['case']/'attempt_01';r=read(folder/'independent_analysis.json')
        factor.append({'behavior':'previous','operations':c['operations'],'wait_min':metric(r,'wait'),'walk_min':metric(r,'walk'),
                       'total_min':metric(r,'total'),'max_wait_min':r['maximum_continuous_wait_min'],'over20_weight':r['over20_weight'],'source':str(folder)})
    newer=[r for r in primary if r['case']['day']=='월' and r['case']['scenario']=='regular']
    for c in read(candidate/'experiment_lock.json')['pilot_cases']:
        if c['operations']=='distribution_v8':continue
        folder=candidate/'runs'/c['case']/'attempt_01';r=read(folder/'independent_analysis.json')
        assert r['status']=='PASS_INTERNAL_INVARIANTS';newer.append(r)
    assert len(newer)==3
    for r in newer:
        c=r['case'];factor.append({'behavior':'candidate','operations':c['operations'],'wait_min':metric(r,'wait'),'walk_min':metric(r,'walk'),
            'total_min':metric(r,'total'),'max_wait_min':r['maximum_continuous_wait_min'],'over20_weight':r['over20_weight'],'source':r.get('source_directory',str(candidate/'runs'/c['case']/'attempt_01'))})
    assert len(factor)==6
    q=read(ROOT/'known_queue_diagnostic.json');assert len(q['rows'])==22
    extra_clock=read(ROOT/'additional_clock_diagnostic.json')
    qrows=[]
    for event in q['observations']:
        selected={r['model']:r for r in q['rows'] if r['observation_id']==event['id'] and r['scenario']=='regular' and r['model'] in ('V11','prototype_V8')}
        assert len(selected)==2;qrows.append({'event':event,**selected})
    tails=read(ROOT/'journey_tail_comparison.json');assert len(tails['rows'])==40
    engineering_bins=read(ROOT/'engineering_snu_departure_half_hour_comparison.json')
    engineering=[]
    for r in primary:
        c=r['case'];engineering.append({'weekday':c['day'],'scenario':c['scenario'],'input_trip_weight':r['scope']['engineering_snu']['weight'],
            **{'baseline_'+k:metric(r,k,'baseline','engineering_snu') for k in ('wait','walk','total')},
            **{'candidate_'+k:metric(r,k,'prototype','engineering_snu') for k in ('wait','walk','total')}})
    with (validation/'half_hour_waits.csv').open(encoding='utf-8-sig',newline='') as f:half=list(csv.DictReader(f))
    peak_by={(r['case'],r['node']):r for r in peaks['rows']}
    for r in half:
        r['ars']=peak_by[r['case'],int(r['node'])]['ars']
        r['total_wait_exposure_person_minutes']=float(r['arrival_episode_weight'])*float(r['mean_continuous_wait_min'])
    largest_exposure=sorted(half,key=lambda r:-r['total_wait_exposure_person_minutes'])[:10]
    mon=next(r for r in primary if r['case']['day']=='월' and r['case']['scenario']=='regular')
    changes=mon['change_distribution'];mass=math.fsum(changes.values());distribution={k:100*w/mass for k,w in changes.items()}
    allrawmax=max(r['extended_diagnostics']['all_recorded_time_max_continuous_wait_min'] for r in v['results'])
    allrawover=math.fsum(r['extended_diagnostics']['all_recorded_time_over20_episode_weight'] for r in v['results'])
    meta={'internal_status':v['status'],'empirical_status':'NOT_EVALUABLE','candidate':str(candidate),'validation':str(validation),
          'new_algorithm_promoted':False,'production_candidate_ready':False,'requires_new_explicit_user_approval_before_production':True,
          'independent_heldout_dates':[],
          'maximum_continuous_wait_min':v['maximum_continuous_wait_min'],'over20_episode_weight':v['over20_episode_weight'],
          'unserved_trip_weight':v['unserved_trip_weight'],'all_recorded_max_stop_wait_min':allrawmax,'all_recorded_over20_episode_weight':allrawover,
          'validation_sha256':sha(validation/'validation.json'),'runtime_code_sha256':v['runtime_code_sha256'],
          'source_demand_frozen_prepared_sha256':sha(candidate/'frozen/prepared_capacity44_pair.json.gz'),
          'weekday_comparison':summary,'factor_comparison':factor,'mon_regular_change_distribution_percent':distribution,
          'named_stop_reference40_cells_exceeded_in_primary_window':len(above),
          'engineering_snu_comparison':engineering,'engineering_half_hour_rows':len(engineering_bins['rows']),
          'additional_clock_status':extra_clock['status'],'additional_clock_maximum_wait_min':extra_clock['maximum_continuous_wait_min'],
          'additional_clock_over20_weight':extra_clock['over20_weight'],
          'all_experiments_including_additional_clock_pass20':v['over20_episode_weight']<1e-7 and extra_clock['over20_weight']<1e-7,
          'diagnostic_sources':{name:sha(ROOT/name) for name in ('known_queue_diagnostic.json','journey_tail_comparison.json','queue_peaks_by_window.json')}}
    csvout(ROOT/'weekday_comparison.csv',summary);csvout(ROOT/'behavior_operations_comparison.csv',factor);csvout(ROOT/'named_stop_queue_review.csv',named)
    csvout(ROOT/'half_hour_wait_exposure.csv',half)
    csvout(ROOT/'engineering_snu_weekday_comparison.csv',engineering)
    save(ROOT/'review.json',meta)
    lines=['# 무제한 경로 변경 프로토타입 · 검증 결과',
      f'\n작성 {datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")}. **주12조건 내부 판정 {v["status"]} / 추가 도킹참조 판정 {extra_clock["status"]} / 실측 정확도 NOT_EVALUABLE / 운영 V11 유지.**',
      '\n## 무엇을 반영했나',
      '\n변경 횟수의 상한·예산·소진은 없다. 평상시 재검토 성향은0.3^현재 변경횟수로 감소하고, 경과 대기·개인 만차 경험의 스트레스는 별도로 재판단 가능성을 높인다. 평균1회는 할당값이 아니다.0~500m의 기본 도보 상대 고려도는 같고1km 이후 급감한다. 실제 보행 선택률은 소요시간·경사·대안·줄에 따라 달라진다. 같은 노선의 뒤 정류장과 재방문은 낮은 고려도0.08/0.05로 남긴다.',
      '\n보행4.8km/h·해당 계단 구간의3배 시간 시나리오·분 상당 선호비용·실제 차량별 정원/FIFO·지속적 개인차·사건별 확률 선택을 분리한 프로토타입이다. 도보 선호계수2를 실제 도보시간2배로 쓰지 않는다. 실제 이동시간과 일반화비용을 구분하며 이미 기다린 시간을 잔여 ETA에 다시 더하지 않는다.',
      '\n기존 수강 기반 출발자료·목적지 참고비중·보행망을 동결했다. 같은 출발지·시각·목적지의 가중 통행을 재배분하며 실제 학생 명부나 개인별 목적지를 관측한 자료가 아니다. 표시 점·고유 학생·가중 통행·승차·재차·대기 방문은 서로 다르다.',
      '\n총시간의 종점은 모형의 설입·낙성대·대학동·기숙사 거점이다. 개인 집까지의 연결 시간은 별도 미확보다. 윗공대 표는301·302동 출발에서 서울대입구역 도착까지로 종점을 일치시켰다.',
      '\n행정관→설입 주간44명/차와 가정한15~19시 피크 창의 두 대 묶음 공급을 양쪽에 똑같이 사용했다. 두 차량을88명 단일 버스로 바꾸지 않았다. 다른 차량의 참고 정원과 야간60명 미확인 가정은 유지했다. 실제 공급을 늘려20분을 맞추지 않았다.',
      '\n## 검증 범위와 판정',
      f'\n월~금×regular/peak10조건과 월요일regular seed1/2를 포함한 **12조건**을 검산했다. 이미 통과한 부모 월요일regular seed1은 코드·설정·입력·감사 해시를 확인해 재사용했고11조건은 새로 계산했다. 최대 연속 정류장 대기는 **{num(v["maximum_continuous_wait_min"],5)}분**,20분 초과 가중 대기 사건량은 **{num(v["over20_episode_weight"],6)}**, 미완료 통행량은 **{num(v["unserved_trip_weight"],6)}**이다.',
      f'\n주 기준은11:20~23:10에 겹치는 모든 연속 대기 방문이다. 줄을 떠나 걷거나 다른 정류장으로 간 방문도 포함한다. 같은 줄에서 호환노선을 바꾸어도 시계를 초기화하지 않는다. 창 밖 초기화 기록까지 포함한 최대는{num(allrawmax,5)}분,20분 초과량은{num(allrawover,6)}이다.20분 강제 이탈·대기 자르기·수요 삭제는 하지 않았다.',
      '\n이는 유한 조건과 난수의 내부 검사다. 모든 난수·현실의 모든 날에20분 이하라는 보장이나 실측 정확도 향상 판정이 아니다. 실제 정답이 부족하므로 NOT_EVALUABLE을 유지한다. 새 사용자 명시 승인 전 V11·latest·사이트 기본 모형·경로 앱 입력을 교체하지 않는다.',
      f'\n별도 민감도인 정문 도킹 절대시계 참조의 판정은{extra_clock["status"]}이며 최대{num(extra_clock["maximum_continuous_wait_min"],5)}분,20분 초과{num(extra_clock["over20_weight"],6)}명 상당·회가 남았다. 주 운행시계는 이 결과를 보기 전에 사용자 요청에 따라 V8분포로 고정했다. 추가 실험 통과 여부도 해당 수치와 판정으로 확인한다. 어떤 운행변동에서도20분 미만이라는 견고성을 확보했다고 주장하지 않는다.',
      '\n## 요일·배차별 전체 비교',
      '\n분 단위 평균은 분석창 밖 출발도 포함한 같은 전체 입력 부모 통행을 양쪽에 사용한다. 대기 최대의 분석창 기준과 분모가 다르다. 아래는 보행 물리시간·행동/예측·시내버스 운행시계를 함께 바꾼 V11대비 전체 효과다.',
      '\n|요일·공급|총시간 평균 V11→후보|누적 대기 V11→후보|도보 V11→후보|최대 연속 대기 V11→후보|20분 초과|미완료|창 뒤 완료|',
      '|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in summary:lines.append(f'|{r["weekday"]} {r["scenario"]}|{num(r["baseline_total_min"])}→{num(r["candidate_total_min"])}|{num(r["baseline_wait_min"])}→{num(r["candidate_wait_min"])}|{num(r["baseline_walk_min"])}→{num(r["candidate_walk_min"])}|{num(r["baseline_max_stop_wait_min"],3)}→{num(r["candidate_max_stop_wait_min"],3)}|{num(r["over20_episode_weight"],5)}|{num(r["unserved_trip_weight"],5)}|{num(r["late_finished_weight"],5)}|')
    lines += ['\n![평일 최대 연속 대기와 전체 이동시간 변화](weekday_waits.png)',
      f'\n전 정류장990행과 도착시각 기준30분 집계{v["half_hour_rows"]}행을 만들었다.30분 표는 그 구간에 줄에 도착한 방문의 최종 연속 대기이며 순간 줄 길이와 다르다. 기존검증CSV의max_queue는 전체기록최대이므로 [시각범위 대조990행](queue_peaks_by_window.csv)에서 분석창/창밖을 구분한다.',
      f'\n[요일 비교 CSV](weekday_comparison.csv) · [전 정류장 CSV](../{validation.name}/all_stops_waits.csv) · [30분 CSV](../{validation.name}/half_hour_waits.csv) · [12조건 감사 JSON](../{validation.name}/validation.json).',
      '\n## 윗공대301·302동 → 서울대입구역',
      '\n같은301/302동 출발·설입 목적지의 부모 통행만 양쪽에서 골랐다. 줄에서 빠져나가 걷거나 다른노선으로 바꾼 통행을 포함한다. 가중치가 실제 고유 학생수라는 뜻은 아니다.',
      '\n|요일·공급|입력 가중통행|누적 대기 V11→후보|도보 V11→후보|총시간 V11→후보|',
      '|---|---:|---:|---:|---:|']
    for r in engineering:lines.append(f'|{r["weekday"]} {r["scenario"]}|{num(r["input_trip_weight"])}|{num(r["baseline_wait"])}→{num(r["candidate_wait"])}|{num(r["baseline_walk"])}→{num(r["candidate_walk"])}|{num(r["baseline_total"])}→{num(r["candidate_total"])}|')
    lines += ['\n[윗공대 요일별 CSV](engineering_snu_weekday_comparison.csv) · [윗공대30분별 CSV](engineering_snu_departure_half_hour_comparison.csv) · [분모·수지 검산](engineering_snu_departure_half_hour_comparison.json). 이30분은 수업 종료자료에 기초해 생성한 모형 통행출발시각(plan[4], 원래departure[particle]) 기준으로, 정류장 도착시각 기준인 전정류장30분 표와 다르다. 공식 수강편람 종료시각의 원표나 실제 학생 하교시각의 관측으로 해석하지 않는다. 같은시간구간의 부모 질량과 요일별 평균이 일치하는지 양쪽 감사에서 검산했다. 현재CSV의departure_bin_* 열로 모형출발시각을 명시했다.',
      '\n## 추가 난수와 변경 횟수',
      '\n|조건|최대 연속 대기|20분 초과량|변경 평균|총시간 평균|',
      '|---|---:|---:|---:|---:|']
    for r in v['results']:
        if r['case']['seed'] not in (1,2):continue
        lines.append(f'|월 regular seed{r["case"]["seed"]}|{num(r["maximum_continuous_wait_min"],4)}|{num(r["over20_weight"],6)}|{num(metric(r,"changes"),4)}|{num(metric(r,"total"),3)}|')
    lines += ['\n월요일regular seed0의 실제 변경 횟수 분포: '+', '.join(f'{k}회 {num(p)}%' for k,p in distribution.items())+'. 모든12조건의 분포는 감사JSON에 보존했다. 같은seed라도 서로 다른 알고리즘의 모든 난수 호출까지 같다는 뜻은 아니다.',
      '\n## 21분 사례를 어떻게 고쳤나',
      '\n앞선R7의12조건 중 목요일peak에서21.07310분/가중0.0548006 통행이 남았다.17:12시점 재구성에서는 앞줄이0이고, 과거 최소여석0.137명 상당을 다음차에 확실히 있는 것으로 취급해 작은 가중 통행은 탈 수 있다고 예측했다. 그 다음차의 실현된 모형 여석은0이었다. 실제 현장의 탑승 정답을 재현한 것은 아니다.',
      '\n앞사람이5513을 거절해도 예측에서는 줄이 청산되는 일반 구조의 불일치도 검토했지만, 이 시점의 앞줄0 재구성에서는 특정 실패의 원인으로 지지되지 않았다. 원래 가설과 반증·수정된 해석을 모두 보존했다.',
      '\n선택 예측에서 작은 가중 대표 통행도 개인 요청량 최소1로 조회하고, 여러 차량의0.x석을 누적해 탄 것으로 계산하지 않게 했다. 앞줄은 기존 가중 FIFO 예측으로 먼저 처리한다.2.1석−앞줄1.05=1.05석이면 한 사람의 요청이 가능해야 하므로 앞줄 처리 전 정수 내림은 하지 않는다. 실제 가중 질량·정원·부분 승차·FIFO·준비20초·대기시계·선호와 변경 위험률은 그대로다.',
      '\n정수 내림을 포함했던R8은 단일 조건의 보수 민감도 실험으로 보존하고 결과를 보기 전에 방법상의 이유로 주 후보에서 제외했다. R9는30개 경계 검산을 거쳤지만 추가난수에서21.744분이 남았다. 현재R10은 기존제곱age불편율의 미래성장을 적분하는 가설을 더하고32개 경계·3개 통합 검산과 독립 정적 검토를 거쳤다. 과거 여석만으로 다음차 여석을 보장할 수 없으므로 이는 보수적 개인 선택 시나리오이며 실측 탑승확률·정확한 ETA의 입증이 아니다.',
      '\n[앞선R7 전체 실패·수정 보고서](../prototype_review_2026-11-10/RESULTS.md) · [실패 시점 재구성](../prototype_validation_261110182218/thu_queue_forecast_replay.json) · [좌석단위 검토](../collaboration/r7_queue_clearance_review_261110182218/SEAT_UNIT_ADDENDUM.md) · [R9코드 독립정적검토](../collaboration/r9_static_review_261110185755/READ_ONLY_REVIEW.md).',
      '\n## R10의 미래 대기 불편 적분 가설',
      '\nR9는고정10조건을통과했으나월요일seed1에서21.744분/0.118735가중통행이남았다. 이전변경4회후에도재검토했으므로횟수소진은아니다. [R9전체판정](../prototype_review_261110185755/RESULTS.md)과 [실패원본](../prototype_validation_261110190402/seed1_long_wait_reconstruction.json)을보존했다.',
      '\n기존의age²×남은대기식은현재의불편율을고정해앞으로적용하는근사다. 산술오류라고단정하지않고, 미래대기중불편율도증가한다고내다보는별도행동가설을시험했다. 현재대기age=a, 앞으로W, 기존scaleS=600초이면 J(a,W)=W(a²+aW+W²/3)/S²이다. 새/후속정류장의age0항은각Wi³의합이고, 현재물리줄의교차항a²W1+aW1²만추가한다. 첫세제곱을중복가산하지않고, 같은줄의적격노선변경으로age를리셋하지않았다. 대기0이면지난대기를비용/ETA에다시더하지않는다.',
      '\nJ는초상당의선호항이며 beta_wait*J/60을분상당비용에넣는다. 물리적ETA에더하지않는다. 기존R3의W²길이선호항은유지했고두심리기전이독립이거나실측으로식별됐다는주장은하지않는다. beta_wait=1/full=0예시에서새줄20분의대기관련비용은60→86.667분상당, 이미10분기다린뒤앞으로10분은30→43.333분상당이다. 실제시간은각각20분과10분으로그대로다. scale유지가작은효과를의미하지않는다.',
      '\n한줄20분의J와두줄10분씩의J는달라새줄이동선호가커질수있으므로변경횟수·누적대기·도보·총시간의꼬리를함께검사한다. 점예측W를넣은J(W)이며불확실한W의기대불편E[J(W)]을계산한것이아니다. 비선형이어서J(E[W])와E[J(W)]는다르고분산·고차모멘트와현장정답이더필요하다.',
      '\n[수학독립검토](../collaboration/r10_integrated_wait_math_review_20261110/READ_ONLY_REVIEW.md) · [현재코드독립정적검토](../collaboration/r10_static_review_261110193823/READ_ONLY_REVIEW.md) · [통합검사3개로그](../'+candidate.name+'/prediction-integration-tests-retry1.log). 실제승하차엔진·정원·수요·운행시계·무제한변경/위험률코드는R9와같다. 추가수치튜닝은없고식의미래성장가정만바꿨다.',
      '\n## 행동/예측과 운행시간의 요인 비교',
      '\n같은4.8km/h 물리시간·수요·44명/두대 공급·seed0의 월요일regular 비교다. 이전행동 대조는R1의 검증 완료 결과를 재사용했다. V8분포가 주 운행보정이며gate_reference는 정문 도킹 절대시각의 별도 참조다. 월요일 자료를 다른요일에 전이한 것은 가정이다. 시내 구간 진입시각별 시간을 쓰고 정차시간을 다시 더하거나 셔틀 시계에 복사하지 않았다.',
      '\n|행동/예측|운행시계|누적 대기|도보|총시간|최대 연속 대기|20분 초과량|',
      '|---|---|---:|---:|---:|---:|---:|']
    for r in factor:lines.append(f'|{r["behavior"]}|{r["operations"]}|{num(r["wait_min"],3)}|{num(r["walk_min"],3)}|{num(r["total_min"],3)}|{num(r["max_wait_min"],4)}|{num(r["over20_weight"],5)}|')
    lines += ['\n![같은 물리시간과 공급의 행동 및 운행시간 비교](factor_times.png)',
      '\n[요인 비교6행 CSV](behavior_operations_comparison.csv). 같은 공급 시나리오끼리 행동/예측 효과를 비교해야 한다. 임의의 가장 잘 맞는 시계나 초를 선택하지 않았다.',
      '\n[추가 도킹참조 상세](additional_clock_diagnostic.json)에도 현재후보의 판정을 보존했다. 이전R9의 도킹참조 실패는[원본](../prototype_review_261110185755/additional_clock_diagnostic.json)에 대학원생활관21897의 두 가중 통행으로 남겼다.11:05도착→11:25탑승으로 분석창에 겹쳤고, 이전 변경2회·만차1회·자발적 승차거절0회였다. 이후에도 재검토했으므로 횟수 소진이 아니다. 첫 차량은 다른 승객으로 만차가 됐고 두번째 차량에 탔다. 버스가 가까워진 뒤 기다리는 비용이 도보보다 낮게 나왔으며 실제 현장 원인으로 확인된 것은 아니다.20분 경보를 남기고 늦은 도보 전환이나 임의 공급증가로 지우지 않았다.',
      '\n## 기존 줄 관측 네 건과의 진단',
      '\n모두 기존 선택 또는 공급 정정에 사용한 자료이며 독립 검증이 아니다. 초 미상은1분 안의 균등 임의시점으로 놓고 정확히 시간적분했다.17:03과11/10의 같은 처리는 비교 가정이다. 날짜는 대화일에서 추정했고 문화관입구21297의 방향 매핑은 미확정이다. 서울대학교21128설입방향은 사용자 확인값이다.',
      '\n|보고|줄|V11→후보 분내 평균|V11→후보 기대 절대오차|',
      '|---|---:|---:|---:|']
    errorfield='expected_absolute_distance_to_count_or_interval';worse=0
    for g in qrows:
        e=g['event'];a=g['V11'];b=g['prototype_V8'];worse+=b[errorfield]>a[errorfield]+1e-7
        observed=str(e['low']) if e['low']==e['high'] else f'{e["low"]}~{e["high"]}'
        lines.append(f'|{e["day"]} {e["minute"]} {b["stop"]}|{observed}|{num(a["uniform_minute_mean"])}→{num(b["uniform_minute_mean"])}|{num(a[errorfield])}→{num(b[errorfield])}|')
    lines += [f'\n네 보고 중{worse}건에서 후보의 기대 줄 오차가 더 컸다.33~39를 정확한36명으로 바꾸지 않고 보고구간까지의 거리를 썼다. 아래 비교로 새 정확도 향상을 주장하지 않으며 이 결과에 계수를 다시 맞추지 않았다.',
      '\n[regular/peak·다른시계 전체22행 CSV](known_queue_diagnostic.csv) · [정의·원본/감사 해시](known_queue_diagnostic.json). 개인189초·탑승후30초는 한 사건이다. 사진 두 장이나67명을 독립 대기 표본으로 늘리지 않았다. 전역 모형의 도착·승차·출발은 한 사건 근사이므로 개인189초를 도착대기/승차처리로 분리 재현했다고 하지 않는다.',
      '\n## 도보와 전체 이동의 꼬리',
      '\n한 정류장의20분 기준과 여정 누적 대기·거점 도착 총시간은 다르다. 줄에서 걸어 나간 통행을 포함하고, 같은 원래 부모 통행 전체의 가중 분위수를 비교했다. 미완료를 완료로 숨기지 않았으며 창 뒤 완료량은 앞 표에 분리했다.',
      '\n|요일·공급|도보 p99 V11→후보|누적 대기 p99 V11→후보|총시간 p99 V11→후보|총시간 최대 V11→후보|',
      '|---|---:|---:|---:|---:|']
    for r in summary:
        t={x['metric']:x for x in tails['rows'] if x['weekday']==r['weekday'] and x['scenario']==r['scenario']}
        def pair(k,q):return num(t[k]['baseline_'+q])+'→'+num(t[k]['candidate_'+q])
        lines.append(f'|{r["weekday"]} {r["scenario"]}|{pair("walk_min","p99")}|{pair("cumulative_wait_min","p99")}|{pair("total_min","p99")}|{pair("total_min","maximum")}|')
    lines += ['\n[모든 분위수·변경횟수40행 CSV](journey_tail_comparison.csv) · [감사 해시와 수지](journey_tail_comparison.json). 드문 장거리 보행·반복 변경·긴 총시간은 별도의 모형 품질 대상이다. 연속 대기만 통과했다고 자연스러운 행동이나 운영 준비 완료로 판정하지 않는다.',
      '\n## 줄 길이 참고와 시간대별 병목',
      f'\n서울대정문·법대/사회대입구 두방향×요일×배차40셀 중 분석창 최대줄이40명 상당을 넘는 셀은{len(above)}개다. 약40명은 사용자 기억의 참고값이며 측정된 상한이 아니다. 줄을40명으로 잘라 맞추지 않았다. 다음표는 각방향에서 가장 큰 분석창 줄이며 전체기록 최대는별도CSV에 보존했다.',
      '\n|정류장·ARS|조건|분석창 최대줄|최대시각|',
      '|---|---|---:|---:|']
    for ars in ('21269','21299','21270','21298'):
        values=[r for r in named if str(r['ars'])==ars];assert len(values)==10
        p=max(values,key=lambda x:x['window_max_queue'])
        lines.append(f'|{p["stop"]} {ars}|{p["weekday"]} {p["scenario"]}|{num(p["window_max_queue"])}|{clock(p["window_queue_peak_at"])}|')
    lines += ['\n[40셀 원표](named_stop_queue_review.csv) · [990셀 분석창/전체시각 대조](queue_peaks_by_window.csv).R7에서61.36명 상당은11:05로 분석창 전,50.37은21:00으로 분석창 안이었다. [R7개별 줄 수지](../prototype_review_2026-11-10/law_queue_service_detail.json)는 유입·승차·도보이탈과 차량통과·거절을 분리한 사후 모형 장부이며 실제 현장 원인 증거는 아니다.',
      '\n30분별 전체 원표에서 최대대기와 총대기노출(평균대기×도착가중치)을 나눠 봐야 한다. 작은 가중 통행의 긴 대기와 많은 통행의 짧은 대기는 다른 병목이다. [30분 CSV](../'+validation.name+'/half_hour_waits.csv)에는 승차자와 중도이탈 방문이 함께 들어 있다.',
      '\n총대기노출이 큰 상위10셀은 다음과 같다. 각 행은 별도 요일·공급 시나리오이고, 여러행의 가중 방문을 합쳐 고유 학생수로 부르면 안 된다. 시간대는 정류장 도착 기준이다.',
      '\n|요일·공급|정류장·ARS|도착 구간|방문 가중치|평균 대기|최대 대기|가중 대기 합계(명 상당×분)|',
      '|---|---|---|---:|---:|---:|---:|']
    for r in largest_exposure:lines.append(f'|{r["day"]} {r["scenario"]}|{r["stop"]} {r["ars"]}|{clock(float(r["bin_start_second"]))}~{clock(float(r["bin_end_second"]))}|{num(float(r["arrival_episode_weight"]))}|{num(float(r["mean_continuous_wait_min"]))}|{num(float(r["max_continuous_wait_min"]))}|{num(r["total_wait_exposure_person_minutes"])}|')
    lines += ['\n[모든30분셀·가중대기노출 CSV](half_hour_wait_exposure.csv). 이 순위는 실측 혼잡순위가 아니라 모형의 비교 지표다.',
      '\n후속 검증 대상은 수업종료 도착집중과 차량 도착위상, 같은 목적지의 다른 노선·교내 셔틀 연결, 하류에 도착하기 전 차내 재차, 실제 승하차 체류다. 공급을 바꿀 때는 차량 총량·정원을 맞춘 별도 실험으로 효과를 분리해야 한다. 혼잡등급을 임의 인원으로 바꾸거나 관측 승차를 정류장 도착수요로 덮어쓰지 않는다.',
      '\n## 검산·남은 한계·운영 경계',
      '\n부모별 질량·성향 지속·보행시간·시간 분해·실제 승하차와 재차 수지·정원·자발거절을 구분한 적격FIFO·준비전 취소·대기열 재구성·차량시각을 감사자료로 별도 검산했다.32개 경계·3개 통합 검사는 같은시각44명 두차량, 준비중 놓친차, 소수석 여러차량 누적불가, 앞줄처리후1석, 변경100회후 재검토 가능 등을 포함한다.',
      '\n실제사건과 여행자의 예측이 같은 고정 외생 공급시계를 공유한다. V8추정 시계는 공식 공개 시간표가 아니며 실시간 예측 검증이나 미래정보 완전차단을 통과했다고 표현하지 않는다. actual_schedule/perceived_schedule/available_at분리가 남는다. 승차/대기 뒤 거절·만차일 때 도보를 검토하는 두단계 선택이며 마지막버스보다 빠른 도보의 동시비교·내생적 조기하차는 미구현이다.',
      '\n일반적인 적격pool과 예측 승차의향의 차이, 경로 유사성, 교외 배경 승객, 경사 누락과 실제 투입 차종 정원이 불확실하다. 선호·위험률·보행 계수는 미보정 시나리오다. 별도44명 두차량 승하차 작은모형의1296민감도 실험은 전역 네트워크에 아직 결합하지 않았다.',
      '\n미사용 날짜의 정렬된 실제 줄·개인대기·승하차·총시간이 부족하다. 서울시 일별 승하차와 월별 시간대 합계를 날짜×시간의 대기 정답으로 만들지 않았다. 현재 자료로 실측 정확도와 교체 적합성을 판정할 수 없어 NOT_EVALUABLE이다.',
      '\n운영은 [V11지도](https://snu-shuttle-simulation.vercel.app/)와 [경로앱](https://snu-route-lab.vercel.app/)을 유지한다. 활성모델261110162302, payload SHA256 `f39be2fbe61185f198ac27da9b8b57565cccfb80824e0a4f8f65f68915cbd130`이다. 모바일 지도와44명/피크두대 공급 설명의 운영 변경은 이 행동 프로토타입과 별개다. **새 사용자 명시 승인 전 교체·예약배포·latest변경은 없다.**',
      '\n[운영 사이트 읽기 전용 재확인](production_unchanged_verification_v2.json)은 지도 latest·지도/데이터 호스트의 실제 배포 payload·경로 앱 동기화·모바일 자산 등 8개 응답을 확인했다. 최초 검사기의 데이터 호스트 latest 경로 가정으로 발생한 404는 [실패 기록](production_unchanged_verification.json)에 보존했다. 데이터 전용 호스트는 불변 release payload를 제공하며, 확인 과정에서 운영 변경은 없었다.',
      '\n출처와 원리: [이전9파일럿의 직접 확인한 출처](../prototype_model_2026-11-10/RESULTS.md#참고한-원리와-직접-확인한-출처), [R7의 모든 실패와 반례](../prototype_review_2026-11-10/RESULTS.md), [현재32경계검사 로그](../'+candidate.name+'/boundary-tests.log), [코드·입력·결과 요약JSON](review.json).',
      f'\n후보 `{candidate.name}` / 전체검증 `{validation.name}`. 모든 이전엔진·원본수요·V7~V11·실패후보·부분실행·실패로그를 보존했다.']
    target.write_text('\n'.join(lines)+'\n',encoding='utf8');print('FINAL_REVIEW_CREATED',v['status'],target)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--candidate',required=True);p.add_argument('--validation',required=True);a=p.parse_args();main(a.candidate,a.validation)
