"""A single team entry point with explicit scope, tradeoffs and source links."""
from pathlib import Path
from datetime import datetime,timezone
import csv,hashlib,json,re
ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent;w=ANALYSIS/'261116122336'
def read(p):return json.loads(p.read_bytes())
def rows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
d=read(w/'pilot-decision.json');review=read(ROOT/'experiment-review.json')['summary']
assert d['status']=='PILOT_NOT_ACCEPTED' and d['physical'] and d['behavior']
assert read(w/'pilot-final-verification.json')['status']=='PASS_RESULT_INTEGRITY_NOT_ACCEPTANCE'
assert read(w/'disabled-pressure-reproduction.json')['maximum_absolute_error']<1e-6
assert read(w/'pilot-prediction-information-audit.json')['status']=='PASS'
public=read(ROOT/'final-public-readback.json');assert public['all_checks_passed'] and public['expected_model']=='261110162302'
fields=read(w/'pilot-decision.json')['observations']
gate=next(x for x in fields if x['minute']=='17:03')
exposure=rows(ROOT/'afternoon-law-before-after.csv')
afternoon=[]
for day in ['월','화']:
    a=next(r for r in exposure if r['model']=='261116010854' and r['weekday']==day and r['node']=='60')
    b=next(r for r in exposure if r['model']==w.name and r['weekday']==day and r['node']=='60')
    afternoon.append(f"|{day} 15~20시·21298 최대 줄|{float(a['maximum_queue']):.2f}→{float(b['maximum_queue']):.2f}명 상당|")
text=f'''# 하교 모형 추가 개선 검토:팀 전달본

**이번 비교에서는 세 문제를 모두 해결한 운영 후보를 확보하지 못했습니다.** 구조 문제를 수정한 코드와27조건의 완료 결과를 보존했습니다. 최신122336은 행동·물리 검사는 통과했지만 성과 판정에 실패해 나머지8조건으로 확대하지 않았습니다. 공개V11은261110162302로 유지했으며 사이트·경로API·공개 자산8개를 마지막에 다시 확인했습니다.

## 무엇이 문제였고 무엇을 수정했나

1. 같은 정류장의 다른 합법 노선을 초기 경로 잠금 때문에 보지 못하는 경우가 있었습니다. 선호가 풀리면 FIFO 순번·대기·만차 경험을 유지한 채 그 자리의 다른 정책도 비교하게 했습니다.
2. 첫 접근편만 시내버스이면 후속 주노선이 통학셔틀로 바뀌어도 원래 수단을 지킨 것으로 처리했습니다. 서울대입구·대학동의 원래 귀가 주수단 허용 집합을 보존하고,주노선 승차지별로 초기 선택을 묶었습니다.
3. 한번 수단 자유를 얻으면 새 줄이 짧아도 계속 변경 기회가 생겼습니다.122336은 수단 자유와 현재 줄에서 다시 변경할 사유를 분리했습니다. 개인별 인내·만차/추가 통과·운행부재 기준,무제한 변경,반복 도보,재방문 금지와 정문 최종 대안은 유지했습니다.

법대 최대 혼잡 장면의 낙성대 수요45.61명 상당 중42.99명 상당은 다른 버스에서 내려온 환승 수요였습니다. 당시 다음02-2의 모의 여석은8.60명분이었습니다. 이는 모형 내부 진단이며 실제 학생의 목적지별 환승이나 실제 차량 정원을 새로 측정한 결과가 아닙니다.

20분을 넘겨도 재검토가 멈춘 것은 아니었습니다. 중간 후보의31.67분 사례는 만차3회·재검토56회 후에도 계속 기다리는 쪽을 택했습니다. 현재 대기 예상·후속 환승의 인지·미추정 대기 효용·여석 대리값을 분리해 비교했고,유리한 숫자만 골라 채택하지 않았습니다.

## 최신122336의 월·화 기본배차:요청 직전과 비교

|지표|요청 직전 → 최신|
|---|---:|
|20분 초과 가중 대기 구간 합|{d['over20_before']:.3f}→{d['over20_after']:.3f}|
|최대 연속 대기|{d['max_wait_before']:.3f}→{d['max_wait_after']:.3f}분|
|재사용4관측의 기대 절대오차 합|{d['field_error_sum_before']:.3f}→{d['field_error_sum_after']:.3f}|
|월요일 평균 귀가 총시간|28.251→31.612분|
|화요일 평균 귀가 총시간|28.029→31.239분|
|17:03 정문21128 분평균·관측33~39명|{gate['old_mean']:.3f}→{gate['new_mean']:.3f}명 상당|
{chr(10).join(afternoon)}

정문은 가까워졌지만 여전히 과소예측합니다. 문화관은3.776→12.105명 상당으로 관측5명에서 더 멀어졌습니다.20분 초과와 평균 총시간도 악화해 최신안을 채택하지 않았습니다. 미완료·정원 위반이나 현재 줄의 변경 사유 없는 물리적 이탈이 없다는 검사는 통과했습니다. 그 사실이 실측 정확도를 보장하지는 않습니다.

## 시간 범위를 구분해야 하는 이유

전체 기록의76명 안팎 최대는 오전11시 부근에 잡히는 경우가 있습니다. 이를 하교 피크의 최대라고 부르면 잘못된 해석입니다. 위 표는15~20시만 따로 계산했습니다. 최신안에서 법대21298의 화요일 오후 최대는53.36→66.80명 상당으로 악화했고,맞은편21270은 월·화 오후 모두40명 아래였습니다. 양방향·요일·초과 지속시간은[오후 병목 표](AFTERNOON_BOTTLENECKS.md)를 보십시오.

## 전요일에서 일부 좋아진 중간안도 구분

105704는 평일5일×기본/피크10조건에서20분초과 가중 구간19.9% 감소,재사용 관측 기대오차합7.0% 감소,평균 총시간19~44초 단축을 보였습니다. 그러나 최대 대기는31.67분으로 악화했고,환승 대기 미예견을 초기 선택에만 적용한 안입니다. 이후 재검토까지 같은 해석으로 넓힌112731·120358·122336은 성과 검사를 통과하지 못했습니다. 따라서105704도 최신 행동을 완전히 반영한 최종 모형이나 독립 실측 검증을 마친 모형으로 표시하지 않습니다.

‘환승 대기를 고려하지 않는다’가 이후 줄·만차만 예측하지 않는다는 뜻인지,평소 배차 대기도 전부 제외한다는 뜻인지는 추가 확인 대상으로 남았습니다. 이번 확장 비교는 후속 대기 전체를 미예견하는 해석입니다. 이 범위를 결과가 유리하도록 바꿔 채택하지 않았습니다.

## 숫자를 더 맞추기 전에 필요한 자료

- 같은 날짜·같은 버스 도착 전후의 대기 줄,승하차,교외에서 들어온 재차와 실제 차량 정원.
- 법대 양방향에서 내린 뒤 낙성대·기숙사·서울대입구로 갈 사람의 분리 계수와 실제 이용 노선.
- 정문21128의 줄 합류·승차 흐름과 당시 운행시각. 한 시점의 줄만으로 유입 수요와 수송력을 각각 식별할 수는 없습니다.

수업 종료 수강인원은 실제 학생의 마지막 수업·당일 귀가 여부·개인 주소와 같지 않습니다. 일반버스50·마을24명 정원,초기 수단 대리값,외부 배경 승객 미포함도 남은 가정입니다. 관측4건은 이미 여러 번 사용했으며 기본/피크 시나리오를 독립 날짜로 세지 않았습니다.

## 함께 볼 파일

- [최신 월·화의 대기·관측·법대 결과](LATEST_PILOT_RESULTS.md)
- [하교15~20시 법대 양방향 병목](AFTERNOON_BOTTLENECKS.md)
- [전요일 중간안과 모든 실패 비교](FINAL_REVIEW.md)
- [가정·자료·출처](SOURCES_AND_ASSUMPTIONS.md)
- [문헌 원문과 확인 범위](../v12_remaining_queues_20261116/THEORY_AND_SCOPE_20261116.md)
- [전요일99노드·30분 진입집단 대기:중간105704](../261116105704/grid-all-recorded-half-hour-waits.csv)
- [최신122336의99노드 대기:본2+진단1](../261116122336/pilot-all-recorded-stops.csv)
- [최신122336의정류장·30분 진입집단 대기](../261116122336/pilot-all-recorded-half-hour-waits.csv)
- [최신 입력·초기 성향·대조군 재현 검사](../261116122336/pilot-final-verification.json)
- [공개 모델 마지막 확인](final-public-readback.json)

최신 코드의 고유 활성시험129개·계승 모듈시험89개·선호 보조검사5개가 통과했습니다. 수정 비활성 대조군은 직접 부모112731의 수치를 오차0으로 재현했습니다. 실행·내부 정합성과 새 날짜의 실측 정확도는 구분하며,새 날짜 정확도는평가하지않았습니다.
'''
out=ROOT/'START_HERE.md';assert not out.exists();out.write_text(text,encoding='utf8')
names=['START_HERE.md','LATEST_PILOT_RESULTS.md','AFTERNOON_BOTTLENECKS.md','FINAL_REVIEW.md',
       'SOURCES_AND_ASSUMPTIONS.md','experiment-review.json','afternoon-law-before-after.csv','final-public-readback.json',
       'unpressured-switch-diagnosis.json']
links=0
for n in [x for x in names if x.endswith('.md')]:
    for href in re.findall(r'\]\(([^)]+)\)',(ROOT/n).read_text(encoding='utf8')):
        if href.startswith(('http://','https://','#')):continue
        assert (ROOT/href).resolve().exists(),(n,href)
        links+=1
out=ROOT/'TEAM_PACKAGE.json';assert not out.exists()
out.write_text(json.dumps({'created_at':datetime.now(timezone.utc).isoformat(),'entry_point':'START_HERE.md',
    'latest_candidate':w.name,'latest_status':d['status'],'completed_executions':review['completed_executions_this_task'],
    'document_sha256':{n:sha(ROOT/n) for n in names},'local_links_checked':links,'source_and_input_integrity':str(w/'pilot-final-verification.json'),
    'new_date_accuracy':'NOT_EVALUATED','operating_adoption_recommended':False,'production_writes':False},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('TEAM_HANDOFF_READY',review['completed_executions_this_task'],links,sha(ROOT/'START_HERE.md'),flush=True)
