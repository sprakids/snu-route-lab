"""Cross-candidate report, including failed comparisons, from completed ledgers only."""
from pathlib import Path
from datetime import datetime, timezone
import csv, hashlib, json, math

ROOT=Path(__file__).resolve().parent
ANALYSIS=ROOT.parent
IDS=['261116102200','261116103210','261116105704','261116112731','261116120358','261116122336']
BASE='261116010854'
C='261116105704'
E='261116122336'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
def save(p,x):
    assert not p.exists(),p
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def write(p,t):
    assert not p.exists(),p
    p.write_text(t,encoding='utf8')
def wait(r):return r['extended_diagnostics']['all_recorded_time_over20_episode_weight']
def maximum(r):return r['extended_diagnostics']['all_recorded_time_max_continuous_wait_min']
def quantiles(r):return r['extended_diagnostics']['finished_trip_quantiles']['total_min']
def match(rs,r):
    result=[x for x in rs if (x['case']['day'],x['case']['scenario'])==(r['case']['day'],r['case']['scenario'])]
    assert len(result)==1
    return result[0]

def main():
    ede=read(ANALYSIS/E/'pilot-decision.json')
    if ede['status']=='PILOT_QUALIFIED':
        assert (ANALYSIS/E/'grid-validation.json').exists(),'Accepted pilot still needs full grid'
        assert (ANALYSIS/E/'export-reconciliation.json').exists(),'Wait for full table reconciliation'
        assert (ANALYSIS/E/'artifact-verification.json').exists(),'Wait for final verification'
    chosen=E if ede['status']=='PILOT_QUALIFIED' else C
    w=ANALYSIS/chosen
    current=read(w/'grid-validation.json')['results']
    old=read(ANALYSIS/BASE/'grid-validation.json')['results']
    assert len(current)==len(old)==10
    oldf=rows(ANALYSIS/C/'grid-field-comparison.csv')
    newf=rows(w/'grid-field-comparison.csv')
    oldf=[x for x in oldf if x['model']==BASE]
    newf=[x for x in newf if x['model']==chosen]
    assert len(oldf)==len(newf)==8
    key='expected_absolute_distance_to_count_or_interval'
    law=rows(w/'grid-stop-queue-exposure.csv')
    lawmax=max(float(x['maximum_queue']) for x in law if x['node'] in ('47','60'))
    numerical={'comparison_parent':BASE,'fully_evaluated_comparison_candidate':chosen,
        'latest_literal_behavior_candidate':E,'latest_pilot_status':ede['status'],
        'max_wait_before':max(map(maximum,old)),'max_wait_after':max(map(maximum,current)),
        'over20_before':math.fsum(map(wait,old)),'over20_after':math.fsum(map(wait,current)),
        'field_error_before':math.fsum(float(x[key]) for x in oldf),'field_error_after':math.fsum(float(x[key]) for x in newf),
        'law_all_recorded_max_after':lawmax,'unserved_weight':math.fsum(x['unserved_trip_weight'] for x in current),
        'new_date_accuracy':'NOT_EVALUATED','production_writes':False,'operating_adoption_recommended':False}
    experiments=[]
    for model in IDS:
        folder=ANALYSIS/model
        decision=read(folder/'pilot-decision.json')
        started=list((folder/'runs').glob('*/attempt_01/started.json'))
        receipts=list((folder/'runs').glob('*/attempt_01/repair_analysis.json'))
        assert len(started)==len(receipts)
        experiments.append({'model':model,'executed_cases':len(started),'pilot':decision,
            'completed_main_grid':(folder/'grid-validation.json').exists(),
            'started_sha256':{str(p.relative_to(ANALYSIS)):sha(p) for p in started}})
    numerical['completed_executions_this_task']=sum(x['executed_cases'] for x in experiments)
    save(ROOT/'experiment-review.json',{'created_at':datetime.now(timezone.utc).isoformat(),
        'summary':numerical,'experiments':experiments,'input_provenance':str(w/'input_manifest.json')})
    status=('최신 환승 대기 미예견 행동을 초기·이후 모두 적용한 후보의 전요일 결과입니다.' if chosen==E else
            '전요일에서 비교한 부분 개선안은105704입니다. 이 안은 초기 선택만 환승 대기를 미예견하므로 최신 행동 설명을 완전히 반영한 최종 모형으로 채택하지 않았습니다. 초기·이후 모두 미예견한112731·120358과 현재 줄의 변경 사유를 분리한122336은 아래에 실패 결과까지 공개합니다.')
    text=['# 남은 긴 대기·정문 과소예측·법대 집중 검토','',status,'',
        '공개 사이트·경로API·운영V11은 바꾸지 않았습니다. 강제20분 이탈,40명 줄 절단,수요 삭제,숨은 외부 승객 추가나 정원 확대는 사용하지 않았습니다.','',
        '## 원인과 수정','',
        '1. **같은 자리의 다른 노선이 보이지 않는 문제:** 초기 경로 잠금 때문에 개인의 선호가 풀려도 합법적인 같은 정류장 노선을 비교하지 못했습니다. 현재 FIFO 순번과 대기·준비·만차 경험은 유지하면서 기존 정책과 합법 확장 정책을 비교하도록 수정했습니다.',
        '2. **원래 귀가 수단이 몰래 바뀌는 문제:** 첫 접근편이 시내버스이면 후속 주노선이 통학셔틀이어도 같은 수단으로 간주했습니다. 이후 새로운 셔틀 충성을 얻어 오래 기다리는 경로가 생겼습니다. 서울대입구·대학동은 원래 주수단 허용 집합도 보존합니다. 접근용 교내셔틀은 귀가 주수단과 구분합니다.',
        '3. **법대 환승 집중:** 기존 최대 줄의 낙성대 수요45.61명 상당 중42.99명 상당이 다른 버스에서 내려 환승했습니다. 그 자리의 대상 노선02-2는 당시 모의 여석이8.60명분뿐이었습니다. 접근편 승차지마다 별도 선택 기회를 주던 초기 선택도 주노선 물리 승차지별로 묶었습니다. 실제 환승 목적지 비율·차종·외부 재차를 새로 알아낸 결과는 아닙니다.',
        '4. **정문 과소예측:** 정문 보행 연결은 빠지지 않았습니다. 중간 수정으로16:30~17:04 유입이39.35→75.84명 상당, 승차 유출도25.82→52.63명 상당으로 함께 늘었습니다. 따라서 유입 증가분이 전부17:03 줄에 남는 것은 아닙니다. 최종 정문 대안으로 옮긴 학생도 생겼으나 한 시점 관측만으로 귀가 수요·서비스·외부 승객을 각각 식별할 수 없습니다.',
        '5. **20분 넘는 잔류:** 개인 기준은 반드시 떠나는 시각이 아니라 대안을 검토하는 기준입니다. 중간 후보의31.67분 사례는 개인P18.15분, 만차3회·재검토56회였고 재검토가 멈춘 오류는 아니었습니다. 후속 환승 대기 인지, 과거 여석에 근거한 낙관적 승차 전망, 실측 미추정 대기 효용이 대안 순위에 함께 영향을 줍니다. 이차·삼차 대기 부담을 중복 버그라고 단정하지 않고 별도 민감도로 비교했습니다.',
        '6. **수단 자유와 반복 변경 사유의 혼동:** 기존에는 한번 자유를 얻으면 새 줄이 짧아도 계속 변경할 자격이 생겼습니다.122336은 수단 자유는 유지하면서 현재 줄의 예상 대기·실제 만차와 추가 통과·운행부재 등 기존 변경 사유가 있을 때만 물리 경로를 재검토합니다. 변경 횟수 상한이나 쿨다운을 추가하지 않았습니다. 이 영구 재검토는 기존 단위시험에도 의도적으로 고정된 가정이었으므로 단순 오탈자 수정이 아니라 사용자 설명에 맞춘 행동 가정의 분리입니다.','',
        '## 전요일 비교: 요청 직전과 '+chosen,'',
        '|지표|요청 직전 → 비교 후보|','|---|---:|',
        f"|20분 초과 가중 대기 구간|{numerical['over20_before']:.3f}→{numerical['over20_after']:.3f}|",
        f"|최대 연속 대기|{numerical['max_wait_before']:.3f}→{numerical['max_wait_after']:.3f}분|",
        f"|재사용 관측4건×운행2시나리오의 기대 절대오차 합|{numerical['field_error_before']:.3f}→{numerical['field_error_after']:.3f}|",
        f"|법대 양방향 전체 기록 최대 줄|76.394→{lawmax:.3f}명 상당|",
        f"|미완료 가중치|{numerical['unserved_weight']:.3f}|",'',
        '가중 구간은 고유 학생 수가 아닙니다. 관측4건을 이미 여러 후보에 사용했으며 운행 대안2개를 독립 관측8건으로 세지 않습니다. 아래 표의 총시간은 실제 모의 경로 완료 시간입니다. 인지 ETA로 대신 계산하지 않았습니다.','',
        '|요일·배차|평균 총시간 전→후(분)|최대 대기 전→후(분)|20분 초과 가중 구간 전→후|p99 전→후(분)|',
        '|---|---:|---:|---:|---:|']
    for r in current:
        o=match(old,r);c=r['case']
        text.append(f"|{c['day']} {c['scenario']}|{quantiles(o)['mean']:.2f}→{quantiles(r)['mean']:.2f}|{maximum(o):.2f}→{maximum(r):.2f}|{wait(o):.2f}→{wait(r):.2f}|{quantiles(o)['p99']:.2f}→{quantiles(r)['p99']:.2f}|")
    text+=['','## 불리한 결과도 포함한 파일럿','',
        '각 파일럿의 전→후는 해당 사전 계획의 대조군 기준입니다. 112731·120358은105704의 월·화 기본배차와 비교하며,122336은 요청 직전010854와 비교합니다.','',
        '|후보|이번 실제 실행수|월·화20분 초과 합 전→후|월·화 재사용 기대오차합 전→후|사전 판정|',
        '|---|---:|---:|---:|---|']
    for e in experiments:
        d=e['pilot'];model=e['model']
        text.append(f"|[{model}](../{model}/pilot-decision.json)|{e['executed_cases']}|{d['over20_before']:.3f}→{d['over20_after']:.3f}|{d['field_error_sum_before']:.3f}→{d['field_error_sum_after']:.3f}|{d['status']}|")
    text+=['',
        '112731은 초기·이후의 인지를 통일했지만 평균 귀가시간이 월3.645분·화3.490분 늘고 재사용 관측 오차와20분초과도 악화되어 추가8조건을 실행하지 않았습니다. 같은 요일의 수정 비활성2조건은105704 결과를 재현했습니다.',
        '120358은 같은 미예견 행동을 유지하고 이차·삼차 추가 부담만 제외했으나 월·화 평균 귀가시간이6.344/5.028분 늘어 실패했습니다.122336은112731의 비용식을 유지한 채 수단 자유와 현재 줄의 변경 사유를 분리했습니다. 한번 자유를 얻었다는 사실만으로 새 줄의 문제를 자동 부여하지 않습니다. 현재 예상 대기·만차/추가 통과·운행부재 조건은 그대로입니다.',
        f"122336의 요청 직전 대비 월·화 평균 총시간 변화는 각각{ede['mean_journey_delta_minutes'][0]:+.3f}/{ede['mean_journey_delta_minutes'][1]:+.3f}분, 최대 대기는{ede['max_wait_before']:.3f}→{ede['max_wait_after']:.3f}분입니다.",
        f"모든 후보의 실제 완료 실행은{numerical['completed_executions_this_task']}조건입니다. 독립적인 그 수의 실측 날짜가 아닙니다. 실패한 조건은 보존했고 각 조건은attempt01 한 번만 실행했습니다.",'',
        '## 남은 문제와 자료','',
        '20분과40명 기준을 모두 충족했다고 판단하지 않습니다. 특정 한쪽 줄만 줄거나 전체 평균만 좋아진 결과를 모든 병목 해결로 표시하지 않습니다. 일반버스50·마을24의 정원 가정, 외부 배경 승객 미포함, 당일 실제 귀가 여부와 초기 수단 대리값은 여전히 식별 한계입니다. 수치 맞추기를 피하려면 실제 노선별 재차·승하차·대기자 목적지·환승 경로와 새 날짜 대기 관측이 필요합니다.','',
        f'- [전요일·99노드 대기](../{chosen}/grid-all-recorded-stops.csv)',
        f'- [요일·정류장·30분 진입집단 대기](../{chosen}/grid-all-recorded-half-hour-waits.csv)',
        f'- [초기·마감 포함 줄 최대와40명 초과 지속](../{chosen}/grid-stop-queue-exposure.csv)',
        f'- [수업 종료부터 귀가](../{chosen}/class-end-journey-comparison.csv)',
        f'- [대기 원인 원장](../{chosen}/grid-wait-cause-ledger.json)',
        f'- [고정 입력·초기 선호·공개8GET 보존 검사](../{chosen}/artifact-verification.json)',
        '- [가정·자료·출처](SOURCES_AND_ASSUMPTIONS.md)',
        '- [원문 문헌 확인 범위와 해석](../v12_remaining_queues_20261116/THEORY_AND_SCOPE_20261116.md)',
        '- [최신122336 파일럿의 모든 정류장 대기](../261116122336/pilot-all-recorded-stops.csv)',
        '- [최신122336 파일럿의 정류장·30분 진입집단 대기](../261116122336/pilot-all-recorded-half-hour-waits.csv)',
        '- [모든 후보의 실행 영수증](experiment-review.json)','']
    write(ROOT/'FINAL_REVIEW.md','\n'.join(text))
    print('FINAL_REVIEW_COMPLETE',chosen,numerical['completed_executions_this_task'])

if __name__=='__main__':main()
