"""Team-facing source notes, failed trials and the final artifact index."""
from pathlib import Path
from datetime import datetime,timezone
import sys,json,hashlib
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,s):
    assert not p.exists(),p
    p.write_text(s,encoding='utf8')
def sources(w):
    text='''# 가정·자료·출처

이번 작업은 요청 직전 후보261116010854에서 이어졌습니다. 직접 대조군은 중간 후보261116105704입니다. 출발 수요·목적지·정원·운행·속도·개인 성향의 수치는 그대로 두었습니다. 학생별 실제 주소나 새로운 선호 설문을 확보한 결과가 아닙니다.

|항목|자료|사용 범위와 한계|
|---|---|---|
|수업·분반 수강인원·건물|[11월6일 추출 수업표](frozen/class_endings_source_20261106.json), [고정 가중 수요](frozen/prepared_capacity44_pair.json.gz)|고유 학생의 실제 당일 귀가나 주소를 추적한 자료가 아닙니다.|
|기숙사·목적지·도서관 경유|계승한prepared의 목적지·출발시각과 [기존 사용 장부](../261112220847/OBSERVATION_USAGE.md)|비율·잔류·귀가 시각은 기존 시나리오입니다. 이번에 관측값에 맞춰 바꾸지 않았습니다.|
|시내버스 운행·구간시간|[고정 운행 입력](frozen/operations_v12_empirical.json), [관측 맥락](frozen/empirical_evidence.json)|11월10일 탐지 기반 계획·시간 정보입니다. 미래 실제 운행이나 개인 대기 실측과 같지 않습니다.|
|셔틀 정원·편성|[정원 수정 근거](capacity44_amendment.json), [편성 가정](pair_amendment.json)|행정관-설입 낮44명/대·15~19시 두 대 편성 등 기존 설정을 계승했습니다. 모든 실제 편성을 확인했다는 뜻은 아닙니다.|
|시내버스 정원·외부 승객|계승한 일반50·마을24명 가정과 [독립 진단](../collaboration/v12_remaining_queues_20261116/DIAGNOSIS.md)|실제 노선별 등록 정원은 미확인입니다. 외부 배경 승객은 물리 수요에 포함되지 않았습니다. 혼잡 등급을 인원으로 환산하지 않았습니다.|
|과거 대기 줄|월요일 추정16:53 행정관53명,16:55 문화관5명(방향 불확실),17:03 정문 밖21128의33~39명; 화요일15:23 행정관67명(줄 합류·본인 포함)|분 안의 초를 균등하게 적분했습니다. 이미 사용한 네 관측이며 독립 검증이 아닙니다. 화요일189초+승차 후30초·44명 두 대 중 두 번째라는 기존 수정값도 계승했습니다.|
|개인 기다림·도보·반복 변경|기존 중앙값20분·로그표준편차0.1,0~500m 평탄·1km 이후 감소,무제한 변경·반복 회피와 도보 증가|이번에 분포를 더 좁혀 맞추지 않았습니다. 실제 학생에게서 추정한 분포가 아닙니다.|
|첫 수단·귀가 주수단|source 계획의 첫 수단과 각pool 멤버 자신의 후속 경로|실제 선호 설문이 아닌 대리값입니다. 원래 혼합 정책이 허용한 집합은 유지하며 새 비율을 정하지 않았습니다.|
|주노선 선택과 환승 대기 인지|사용자 답변: “목적지행 주노선에 빨리 타기인데, 접근용 버스를 탄 뒤 환승 대기까지 고려하진 않아”|초기 선택에서는 주노선 승차지별로 접근 방법을 묶습니다. 이후 경로 변경에서도 현재 첫 줄은 보되 접근편 뒤 환승 대기·준비는 미리 인지하지 않습니다. 이는 사용자 설명에 따른 휴리스틱입니다.|
|실제 반응·도보 중 승차|기존 개인P·만차2회와 추가 지연·재방문 금지·정문 최종 대안·플랫폼 접합|실제 도착 뒤 FIFO·정원·대기는 유지합니다. 기존30초/80m/30m 창은 모든 보행 승차 기회를 실측한 모형이 아닙니다.|

## 선택할 때 느끼는 시간과 실제 시간

초기 선택의 직접1단계는 기존 접근·첫 대기 점수를 유지합니다. 접근편을 타는 경로는 첫 대기와 주노선까지의 차내·보행을 보되, 이후 환승 줄·정원 때문에 후보를 미리 버리지 않습니다. 주노선 물리 노드당 판단 오차를 한 번 줍니다. 거리prior는 기존 첫 접근 도보 범위를 유지했습니다. 직접/접근편 경로의 인지 정보가 비대칭이라는 가정도 포함합니다.

경로 변경에서는 `perceived_prediction`과 정상 운영 전망을 분리합니다. 인지 비용에서는 현재/첫 남은 줄의 대기·준비와 이미 기다린 시간은 유지하고, 접근편 뒤의 대기·준비만 제외합니다. 실제 버스 시각·승하차·정원·보행·줄은 원래 물리 모형으로 계산합니다. `physical_prediction`이 없으면 운영 ETA는None이며 인지 ETA로 대신 채우지 않습니다. 총 귀가시간과 대기 통계는 실제 완료 경로를 사용합니다.

이는 미래를 모두 아는 최적 경로 선택이 아닙니다. 초기의 빈줄 기대 잔여대기Σh²/(2Σh)는 계승했지만 모든 미래 운행 위상을 제거한 것도 아닙니다. 계획 운행의 연결 가능성·구간시간은 사용하며, 미래 실제 승객 결과는 새 예측 입력으로 읽지 않습니다.

## 원인 확인과 이론의 범위

[독립 원인 분석](../collaboration/v12_remaining_queues_20261116/DIAGNOSIS.md), [주수단 경계 검토](../collaboration/v12_remaining_queues_20261116/TRUNK_STATIC_REVIEW_261116103210.md), [주노선 선택 검토](../collaboration/v12_remaining_queues_20261116/PRIMARY_STATIC_REVIEW_261116105704.md), [이번 사전 계획](../v12_consistent_perception_20261116/PROTOCOL.md)을 함께 보십시오. 수치 결과의 실행·검산과 정적 검토는 다른 증거입니다.

이론 배경인[Spiess·Florian(1989)의 출판사 초록](https://www.sciencedirect.com/science/article/pii/0191261589900349)은 목적지까지 기대비용을 고려하는 모형을 설명합니다. 이번의 사용자 휴리스틱을 그 최적전략 알고리즘이나 검증된 서울대 행동으로 부르지 않습니다. 초록만 확인했으며 본문은403/시간초과로 확보하지 못했습니다. 기존 빈줄 대기 참고는[van Oort(2016)](https://link.springer.com/article/10.1007/s12469-016-0121-3)의 고빈도·무작위 도착 맥락을 계승한 것으로 개인 대기 실측이 아닙니다.

새 날짜의 실측 정답·독립 검증 자료는 열지 않았습니다. 실제 외부 재차, 노선별 정원, 학생의 당일 최종 수업과 귀가 여부, 개인 수단 선호는 현재 자료만으로 분리해 식별하지 못합니다. 남은 차이를 맞추기 위한 목적지 배율·숨은 승객·20분 강제 이탈·40명 줄 절단은 하지 않았습니다. 공개V11과사이트는 변경하지 않았습니다.
'''
    write(w/'SOURCES_AND_ASSUMPTIONS.md',text)
def handoff(w):
    rec=read(w/'recommendation.json');proof=read(w/'artifact-verification.json');assert proof['status']=='PASS'
    trials=[]
    for model in ['261116102200','261116103210','261116105704',w.name]:
        d=read(w.parent/model/'pilot-decision.json')
        trials.append(f"|{model}|{d['main_cases']}+{d['diagnostic_cases']}|{d['over20_before']:.3f}→{d['over20_after']:.3f}|{d['field_error_sum_before']:.3f}→{d['field_error_sum_after']:.3f}|{d['status']}|")
    ledger='\n'.join(['# 후보별 실행과 사전 판정','',
        '각 실행은attempt01 한 개이며 완료 원장을 재사용했습니다. 중간102200·103210은각3조건,105704는본10+진단2조건,최종후보도본10+진단2조건으로이번작업은총30조건입니다. 독립적인30일의 실측 표본이 아닙니다.','',
        '|후보|파일럿 본+진단|20분 초과 가중 구간|재사용 관측 기대오차합|판정|','|---|---:|---:|---:|---|',*trials,'',
        '102200은긴대기가줄고관측분은거의같았습니다.103210은관측오차악화로확대를중단했습니다.105704는사용자의추가답변에따라주노선별선택과초기환승대기미예견을정의해전요일로확대했지만31.67분사례가남았습니다. 최종후보는초기와경로변경의인지범위를일치시킨대조입니다. 불리한후보·준비중시험실패/수정로그도보존했습니다.','',
        '모든 후보의config·lock·future 해시는실행전에고정했습니다. 모형조건을다시실행해성공값만선택하지않았으며20분/40명에맞춰수요·정원·개인성향을조정하지않았습니다.'])
    write(w/'EXPERIMENT_LEDGER.md',ledger+'\n')
    intro=f'''# 하교 행동·대기 모형 개선 후보 {w.name}

요청 직전261116010854와 비교한 결과입니다. 주노선별 초기 선택, 같은 자리의 합법 노선 검토, 원래 귀가 수단 보존과 초기/경로 변경의 환승 대기 인지를 맞췄습니다. 수치 성향·수요·목적지·운행·정원은 그대로입니다.

|지표|요청 직전 → 이번 후보|
|---|---:|
|전체 기록20분 초과 가중 대기 구간|{rec['over20_weight_before']:.3f}→{rec['over20_weight_after']:.3f}|
|최대 연속 대기|{rec['max_wait_before']:.3f}→{rec['max_wait_after']:.3f}분|
|재사용4관측×2배차의 기대 절대오차 합|{rec['reused_field_error_sum_before']:.3f}→{rec['reused_field_error_sum_after']:.3f}|
|법대 양방향의 전체 기록 최대 줄|{rec['law_all_recorded_max_before']:.3f}→{rec['law_all_recorded_max_after']:.3f}명 상당|

평균 총시간 변화 범위는{rec['mean_journey_delta_range'][0]:+.3f}~{rec['mean_journey_delta_range'][1]:+.3f}분, 미완료 가중치는{rec['unserved_weight']:.3f}입니다. 가중 방문은 고유 학생 수가 아닙니다. 관측을 이미 사용한 적합도 비교이며 독립 정확도 검증이 아닙니다.

중간105704의 최대 대기{rec['intermediate_primary_stop_max_wait']:.3f}분과도 구분해야 합니다. 파일럿 선택 판정과 기본 비교CSV는 그중간후보를대조하며,위표와상세보고서는요청직전후보와비교합니다.

- [원인·요일별 결과·실측 비교·남은 문제](RESULTS.md)
- [가정·자료·출처](SOURCES_AND_ASSUMPTIONS.md)
- [모든99노드의 전체 기록 대기](grid-all-recorded-stops.csv)
- [요일·정류장·30분 진입집단 대기](grid-all-recorded-half-hour-waits.csv)
- [초기·마감 포함 줄 최대/40명 초과 지속](grid-stop-queue-exposure.csv)
- [수업 종료부터 귀가까지](class-end-journey-comparison.csv)
- [대기 원인 원장](grid-wait-cause-ledger.json)
- [정문 유입·유출](gate-flow-before-after.json)
- [같은 운행의 모형 재차 비교](gate-service-diagnosis.json)
- [인지 전망·운영 ETA·실제 대기의 분리 검산](prediction-information-audit.json)
- [불리한 후보까지 포함한 실행 기록](EXPERIMENT_LEDGER.md)
- [고정 자료·난수·초기 선호·공개 모델 보존 검산](artifact-verification.json)
- [표 수치 검산](export-reconciliation.json)

20분/40명 기준과 운영 채택은recommendation.json의 별도 판정입니다. 운영 채택 권고는 보류하며 공개V11은{proof['production_model']}로 유지했습니다. 실제 재차·차종 정원·목적지별 승하차, 독립 날짜 검증과 사이트 연결·성능 평가는 별도로 남습니다.
'''
    write(w/'START_HERE.md',intro)
    names=['START_HERE.md','RESULTS.md','SOURCES_AND_ASSUMPTIONS.md','EXPERIMENT_LEDGER.md','recommendation.json','artifact-verification.json','export-reconciliation.json','prediction-information-audit.json']
    value={'release_id':w.name,'created_at':datetime.now(timezone.utc).isoformat(),'document_sha256':{n:sha(w/n) for n in names},
           'analysis_script_sha256':{p.name:sha(p) for p in ROOT.glob('*.py')},'new_date_accuracy':'NOT_EVALUATED','production_writes':False}
    write(w/'handoff-manifest.json',json.dumps(value,ensure_ascii=False,indent=2)+'\n');print('HANDOFF_COMPLETE',w.name,flush=True)
if __name__=='__main__':
    w=Path(sys.argv[1]).resolve()
    sources(w) if sys.argv[2]=='sources' else handoff(w)
