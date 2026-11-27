from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,csv,sys
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,s):
    assert not p.exists(),p
    p.write_text(s,encoding='utf8')
def sources(w):
    text='''# 가정·자료·출처와 변경 범위

기준은261116010854이며 수요/목적지/운행/정원/보행/출발 지연과 수치 선호를 그대로 계승했습니다. 이번 선택 규칙은 사용자가 추가로 설명한 행동을 구현한 시나리오입니다. 개인별 주소·실제 선호·새 통학 표본을 확보한 결과가 아닙니다.

|항목|사용 자료|한계|
|---|---|---|
|수업·분반 수강인원·건물|[11월6일 추출 수업표](frozen/class_endings_source_20261106.json), [고정 가중 수요](frozen/prepared_capacity44_pair.json.gz)|고유 학생의 실제 당일 귀가/주소를 추적한 자료가 아님|
|기숙사·목적지·도서관 경유|계승한prepared의목적지/출발시각과[기존 사용장부](../261112220847/OBSERVATION_USAGE.md)|비율·잔류·귀가시각은계승한시나리오|
|시내버스 운행/구간시간|[고정 운행 입력](frozen/operations_v12_empirical.json), [관측 맥락](frozen/empirical_evidence.json)|11월10일 탐지 기반 계획/시간 정보. 미래실현운행초나개인실측대기와같지않음|
|셔틀 정원·편성|[정원 수정 근거](capacity44_amendment.json), [편성 가정](pair_amendment.json)|행정관-설입낮44명/대·15~19시두대편성등기존시나리오유지. 모든실제편성의확인아님|
|시내버스 정원·외부 승객|계승한일반50/마을24가정과[독립 진단](../collaboration/v12_remaining_queues_20261116/DIAGNOSIS.md)|실제노선별등록정원미확인. 외부배경승객은물리수요에미포함. 혼잡등급을인원으로환산하지않음|
|과거 줄 관측|월요일추정16:53행정관53명,16:55문화관5명(방향불확실),17:03정문밖21128의33~39명;화15:23행정관67명(줄합류·본인포함)|분안의초를균등적분. 이미사용한4관측으로독립검증아님. 화요일189초+승차후30초·44명두대중두번째라는기존수정계승|
|개인기다림·도보·반복변경|기존중앙값20분·sigma0.1,0~500m평탄·1km뒤급감,무제한변경·반복회피/기하급수도보증가|이번에값을줄여맞추지않음. 실측추정분포가아님|
|초기첫수단·주수단집합|source계획의첫수단과각pool멤버own continuation의귀가주수단|설문으로측정한선호가아님. 혼합source는원래허용집합유지,교내접근셔틀구분|
|주노선선택과환승대기|사용자직접답변과[사전계획](../v12_remaining_queues_20261116/PRIMARY_PROTOCOL.md)|주노선승차지당바깥선택1개. 첫대기와물리접근은인지하지만뒤환승대기/준비는초기점수에서제외. 직접/feeder정보비대칭을포함한명시휴리스틱|
|후속반응·도보중승차|기존개인P·실제만차2회+추가대기·재방문금지·정문최종대안·기존플랫폼접합|실제도착후FIFO/정원/대기는유지. 현재합법플랫폼의기존30초/80m/30m창이며모든보행승차기회의실측모형이아님|

초기인지점수는실제예상탑승/도착시각과구분합니다. 직접1단계는기존접근+첫대기이며,feeder뒤에는처음탑승이후주노선까지의차내/보행만더합니다. 후속줄·정원·접근중인원으로초기후보를미리제거하지않고공개계획운행의연결가능성만확인합니다. 이미존재하는미래시나리오운행시각을쓰지만미래실현승객결과는읽지않습니다. 첫빈줄기대잔여대기Σh²/(2Σh)는계승하고,모든미래위상을제거했다고주장하지않습니다. 보행prior는기존첫접근도보길이의범위를유지합니다.

이론배경으로[Spiess·Florian(1989), Optimal strategies](https://www.sciencedirect.com/science/article/pii/0191261589900349)의출판사초록은목적지까지기대비용을고려하는모형을설명합니다. 이번사용자의근시안적규칙은그최적전략알고리즘을구현하거나서울대행동을논문으로검증한것이아닙니다. 초록만확인했으며본문은403/시간초과로확보하지못했습니다. 기존빈줄대기참고는[van Oort(2016)](https://link.springer.com/article/10.1007/s12469-016-0121-3)에서계승한고빈도/무작위도착의참고이며개인대기실측이아닙니다.

새날짜실측정답/독립검증자료는열지않았습니다. 외부재차·실제노선정원·유일학생의당일귀가비중·개인모드선호는추가실측없이지금자료로분리식별하지못합니다. 숫자를맞추려고20분강제이탈/40명절단/목적지배율/숨은승객을추가하지않았습니다. 공개V11과사이트는유지합니다.
'''
    write(w/'SOURCES_AND_ASSUMPTIONS.md',text)
def handoff(w):
    r=read(w/'recommendation.json');verify=read(w/'artifact-verification.json')
    assert verify['status']=='PASS'
    rows=[]
    for model in ['261116102200','261116103210',w.name]:
        p=w.parent/model;d=read(p/'pilot-decision.json')
        rows.append(f"|{model}|{d['main_cases']}+{d['diagnostic_cases']}|{d['over20_before']:.3f}→{d['over20_after']:.3f}|{d['field_error_sum_before']:.3f}→{d['field_error_sum_after']:.3f}|{d['status']}|")
    ledger='\n'.join(['# 후보별 실행·선택 기록','',
        '모든조건은고정수요/공급의모의비교이며각실행디렉터리는attempt01한개입니다. 완료본을재사용하고이전/불리한결과를보존했습니다. 중간후보2개각3조건, 최종후보본10조건+진단2조건으로총18조건입니다.','',
        '|후보|파일럿 본+진단|20분 초과 가중 구간|재사용 관측 기대오차합|사전판정|','|---|---:|---:|---:|---|',*rows,'',
        '102200은같은자리선택으로긴대기가줄었지만관측분예측이그대로여서,새로확인된주수단/선택의미문제를분리검토했습니다.103210은관측오차악화로주간확대를중단했습니다.105704는그뒤사용자의명시답변으로주노선승차지단위와환승대기미예견을정의한별도규칙입니다. 모수를다시맞춘후보가아닙니다.','',
        '실험사전계획과소스해시는각후보protocol-reference.json/future_evaluation_plan.json과STARTED에고정했습니다. 준비중시험fixture수정/실패로그도보존했으며,모형조건재실행으로성공값만고르지않았습니다.'])
    write(w/'EXPERIMENT_LEDGER.md',ledger+'\n')
    intro=f'''# 남은 대기·정문·법대 개선 후보 {w.name}

사용자가설명한하교행동과추가답변을반영했습니다. 수치가정·수요·목적지·운행·정원은그대로두고같은자리노선검토,귀가주수단보존,주노선승차지별초기선택을수정했습니다. 환승대기는초기인지점수에서미리보지않지만실제대기계산에는포함합니다.

- 전체기록20분초과가중대기구간: **{r['over20_weight_before']:.3f}→{r['over20_weight_after']:.3f}**, 감소율{100*r['over20_reduction']:.1f}%.
- 전체최대연속대기: **{r['max_wait_before']:.3f}→{r['max_wait_after']:.3f}분**.
- 재사용4관측×2배차기대절대오차합: **{r['reused_field_error_sum_before']:.3f}→{r['reused_field_error_sum_after']:.3f}**, 감소율{100*r['reused_field_error_reduction']:.1f}%.
- 법대양방향표시구간최대줄: **{r['law_display_max_before']:.3f}→{r['law_display_max_after']:.3f}명상당**.
- 평균총시간변화범위: {r['mean_journey_delta_range'][0]:+.3f}~{r['mean_journey_delta_range'][1]:+.3f}분. 미완료가중치{r['unserved_weight']:.3f}.

가중방문은고유학생수가아닙니다. 재사용관측의적합도비교이며독립실측검증이아닙니다.20분/40명엄격기준과운영교체권고는recommendation.json의별도판정을확인하세요. 공개V11은{verify['production_model']}로유지했습니다.

- [원인·요일별비교·실측오차·남은문제](RESULTS.md)
- [가정·자료·출처](SOURCES_AND_ASSUMPTIONS.md)
- [모든99노드의전체기록대기](grid-all-recorded-stops.csv)
- [모든정류장30분진입집단대기](grid-all-recorded-half-hour-waits.csv)
- [초기·마감구간까지줄최대/지속](grid-stop-queue-exposure.csv)
- [수업종료부터귀가까지](class-end-journey-comparison.csv)
- [대기원인원장](grid-wait-cause-ledger.json)
- [정문유입·유출분리](gate-flow-before-after.json)
- [같은운행의모형재차비교](gate-service-diagnosis.json)
- [불리한후보도포함한실행기록](EXPERIMENT_LEDGER.md)
- [파일·동작·난수·초기선호·공개모델보존검산](artifact-verification.json)
- [표수치검산](export-reconciliation.json)

운영채택권고는보류합니다. 실제차종정원·외부재차·목적지별줄합류/승차·환승관측,새날짜독립검증과사이트연결/성능평가는별도로남습니다.
'''
    write(w/'START_HERE.md',intro)
    names=['START_HERE.md','RESULTS.md','SOURCES_AND_ASSUMPTIONS.md','EXPERIMENT_LEDGER.md','recommendation.json','artifact-verification.json','export-reconciliation.json']
    manifest={'release_id':w.name,'created_at':datetime.now(timezone.utc).isoformat(),'document_sha256':{n:sha(w/n) for n in names},
              'analysis_script_sha256':{p.name:sha(p) for p in ROOT.glob('*.py')},'production_writes':False,'new_date_accuracy':'NOT_EVALUATED'}
    write(w/'handoff-manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');print('HANDOFF_COMPLETE',w.name,flush=True)
if __name__=='__main__':
    w=Path(sys.argv[1]).resolve()
    if sys.argv[2]=='sources':sources(w)
    elif sys.argv[2]=='handoff':handoff(w)
