"""Publish a local evidence report; this file cannot publish to Vercel."""
from pathlib import Path
import json,hashlib,csv

ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text(encoding='utf8'))
def main():
    result=read(ROOT/'comparison.json');rows=result['results'];replay=read(ROOT/'long_wait_reconstruction.json');micro=read(ROOT/'micro_sensitivity.json')
    names={'control-regular-fri':'정원·차량 처리 대조(금)','physics-regular-mon':'물리시간만 분리(월)',
        'behavior-regular-mon':'선호·순차선택만(월)','combined-regular-mon':'결합(월)','combined-regular-fri':'결합(금)',
        'combined-peak-mon':'결합·피크배차(월)','combined-regular-mon-seed1':'결합(월) seed1',
        'combined-regular-mon-seed2':'결합(월) seed2','fare-scenario-regular-mon':'추가요금 선택비용(월)'}
    lines=[]
    for row in rows:
        m=row['scope']['all']['metrics'];lines.append(f"|{names[row['case']['case']]}|{m['total_min']['baseline']:.2f} → {m['total_min']['prototype']:.2f}|{m['wait_min']['prototype']:.2f}|{m['walk_min']['prototype']:.2f}|{row['maximum_continuous_wait_min']:.2f}|{row['over20_weight']:.2f}|{row['elapsed_seconds']:.1f}|")
    checks=sum(r['checks']['capacity_events'] for r in rows);long=next(r for r in rows if r['case']['case']=='combined-regular-mon')
    subject=replay['subject'];hist=long['change_distribution'];total=sum(hist.values())
    distributions=' / '.join(f'{k}회 {100*w/total:.2f}%' for k,w in hist.items())
    note=f'''# 분리형 프로토타입 첫9파일럿 · 검증과 미채택 사유

2026-11-10 작성. 이 결과는 **운영 미채택·독립정답 부족 NOT_EVALUABLE**입니다. 삭제하거나 개선 작업을 종료한 것이 아닙니다. 후속 후보는 [별도 실험 안내](followup_experiment.json)에 기록합니다. 사용자의 추가 지시대로 **승인 전 운영 V11 교체는 금지**합니다.

## 무엇을 실제 구현했나

물리 이동시간, 분 상당 선호비용, 차량별 유한 정원/FIFO, 지속적인 개인 성향과 사건 시점의 확률적 판단을 코드로 분리하고9개 사전등록 파일럿을 실제 실행했습니다. 보행 가중치2는 ETA를2배로 만들지 않습니다. 총시간은 실제 모형의 걷기·대기·차내 이동 사건시각 합계입니다. 추가요금은 원/시간 VOT로 선택비용에만 변환합니다. 이미 기다린 시간을 잔여 ETA에 다시 더하지 않습니다.

보행은 동일한 OSM 경로에4.8km/h를 적용하고 확인 가능한 계단 구간만3배 시간 시나리오, 숫자로 표현된 경사만 상대 경사 시나리오를 적용했습니다. 고도·경사가 없는 구간은 추정 불가로 표시하고 평지 기본값을 사용했습니다. 새로운 전역 최적 보행 경로를 구한 것은 아닙니다. log-normal 성향, 위험률·선택 온도·VOT·도보 계수는 학교 실측으로 추정한 값이 아닌 미보정 사전 시나리오입니다.

큰 가중 집단은 최대1명 상당 합성 패킷으로 분할하고 부모 통행의 질량을 보존했습니다. 이는 실제 고유 학생 명부가 아닙니다. 출발지·출발시각·목적지·수요를 같은 부모 통행에 맞춰 비교했고, 경로 전환은 기존 수요의 재배분입니다.

정원·공급 수정 효과와 새 알고리즘 효과가 섞이지 않도록 첫9파일럿의 최종 attempt04는 모두 행정관→설입 주간44명/차·가정한15~19시 두 대 묶음의 같은 입력을 사용했습니다. 다른 노선 정원·도로·배차·속도 가정은 유지했습니다. 야간60명은 확인되지 않은 기존 가정입니다. 비교 기준은 같은 입력으로 재계산한 V11의 기존 행동 엔진입니다.

## 비교 결과

단위는 분이며 모든 부모 가중 통행을 포함합니다. 대기는 한 정류장의 연속 대기가 아닌 여정 누적 대기입니다. 최대 연속 대기와20분 초과량은 별도 열로 표시했습니다. 초과량은 한 통행이 여러 정류장에서 넘으면 여러 번 세는 가중 사건량입니다. 원래 결과에서 미완료 통행량은0이었습니다. 기록 실행시간은 같은 PC의 병렬 작업 경과시간이며 통제된 성능 벤치마크가 아닙니다.

|파일럿|같은 공급 기준 총시간 → 후보 총시간|후보 누적 대기|후보 도보|최대 연속 대기|20분 초과 가중 사건량|실행 초|
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(lines)}

물리시간만 바꾼 월요일은 총시간27.50→26.18분,20분 초과0이었습니다. 선호·순차 선택을 바꾸면32.59분과 장기 대기가 생겼으므로 첫 실험의 큰 악화는 새로운 행동·예측 부분과 연결됩니다. 이는 구성요소를 나눈 모형 안의 진단입니다. 실제 이동시간 정확도가 좋아지거나 나빠졌다는 실측 성능 판정은 아닙니다. 금요일 평균 총시간이 줄어도 장기 대기64.91명 상당·회가 남아 운영 적합으로 판단하지 않았습니다.

결합 월요일의 실제 변경 횟수 분포는 {distributions}입니다. 횟수의 예산·최댓값·소진은 없습니다. 원래 기본 성향의0.3배 반복 감소와 만차·대기 스트레스가 함께 작동했습니다. 평균1회는 강제 할당 목표가 아닙니다.0~500m 기본 도보 고려도는 동일하고1km 뒤 급감합니다.

## 20분 초과 원인 추적

가장 긴 결합 월요일 사례는 국제대학원(21285)에서 낙성대 방향 관악02-2를 기다린 가중0.2192 통행입니다. 연속 대기{long['maximum_continuous_wait_min']:.2f}분, 이전 변경2회, 개인 만차 경험41회, 이 구간의 자발적 승차 거절0회였습니다. 변경 제한 소진이나 자발적 거절만으로 설명할 수 없습니다.

1.14시 상태를 재구성하니 앞줄은1.315명 상당이고 당시 예측은7.53분 뒤 승차였습니다. 실제 모형 승차까지317.53분이 걸렸으며 이후31번의 해당 버스가 모두 만차였습니다. 미래 차량이 아직 출발하지 않아 차내 인원이0인 상태를 하류 도착 여석으로 쓰면서, 상류 정류장 수요로 다시 채워질 위험을 배우지 못했습니다. 재구성에는 해당 시점까지의 줄·차내 상태만 예측 입력으로 사용했고, 이후 실제 기록은 오차 진단에만 사용했습니다.
2.같은 물리적 정류장의 기존 후보에는5511→관악02-1 환승 전략이 있으나, 새 선택부가 같은 정류장 대안을 건너뛰고 단일 단계 호환 풀만 확장해 이 전략이 빠졌습니다. 같은 줄에서 가능한 다른 노선의 자격을 완성해야 합니다. 이때 대기 시각·FIFO 순서·변경 횟수를 초기화하면 안 됩니다.
3.반복 횟수의0.3배가 스트레스 위험률까지 곱해져 여러 번 바꾼 사람의 재판단이 과하게 약해졌습니다. 후속 후보에서는 기본 반복 성향 감소와 개인 만차·대기 스트레스를 분리합니다. 이를20분에서 무조건 나가는 규칙으로 대체하지 않습니다.

후속 후보는 이 원인에 맞춘 동일 정류장 전략·과거 여석 기반 예측·연속 스트레스 위험률 수정과 관측 기반 운행시간 결합을 별도 실험으로 계속합니다. 기존9파일럿의 실패 증거는 그대로 둡니다.

## 독립 정합성 검산

원래9개의 전체 감사자료에서 부모별 질량·개인 성향 지속·보행 물리시간·여정 시간 연결·실제 승하차·재차량·정원·자발적 거절을 구분한 적격FIFO·준비 전 취소·대기열 재구성을 검사했습니다. 총{checks:,}개의 정류장 차량 사건을 대조했습니다. 대조 금요일은 같은 공급의 V11과 차량 사건22,701개·대기 방문32,671개·완료 분할 궤적28,886개가 완전히 같았습니다.21개 경계 검산도 통과했습니다. 내부 수지 통과와20분 품질 기준 통과는 다른 판단입니다.

[전체 비교 CSV](comparison.csv) · [전 정류장891행](all_stops_waits.csv) · [정밀 비교 JSON](comparison.json) · [장기 대기 재구성](long_wait_reconstruction.json) · [사전 실험표](experiment_lock.json) · [입력 동결](input_manifest.json).

원래 개별 검산 JSON의 일부 열 이름에_seconds가 남았지만 숫자는 이미 분 평균이었습니다. 원본 검산은 보존하고 비교 JSON/CSV의 열 이름을_min으로 정정했습니다. 숫자·모형 실행·결론은 바꾸지 않았습니다. 기준 엔진이 기록하지 않은 요금은0원이 아니라 결측으로 표시했습니다.

## 실측의 사용 범위와 판정

11/9의53명·5명·정문33~39명은 이전 후보 선택에 이미 썼으므로 독립 검증이 아닙니다.11/10의 합류15:23·외부 줄67명·개인189초·탑승 후30초 사건은 정원44명 정정과 외부 진단에 사용했으며 선호계수를 맞추거나 최종 미사용 정답으로 쓰지 않았습니다. 분내 임의 초를 가장 잘 맞는 초로 대체하지 않습니다. 날짜11/10은 대화일·화요일을 근거로 기록한 것이며 별도 날짜 확인은 없었습니다. 사진 두 장은 한 사건입니다.

서울시 일별 승하차와 월별 시간대 합계는 날짜×시간별 줄·대기 정답이 아닙니다. 승차를 그대로 도착 수요로 넣거나, 혼잡등급을 임의 인원으로 바꾸거나, 관측과 모형의 차이를 전부 교외 배경 승객으로 채우지 않았습니다. 실제 교외 재차·하차 인원은 여전히 부족합니다.

따라서 미사용 날짜의 정류장·방향·시각별 줄/개인 대기/승하차 정답이 없어 정확도 교체 판정은 NOT_EVALUABLE입니다. 내부20분 기준도 실패했으므로 첫 후보를 운영에 쓰지 않습니다. 향후 기준을 통과하더라도 운영 V11 교체에는 사용자의 새 명시 승인이 필요합니다. 자동 교체·예약 배포는 없습니다.

## 두 대 승차 처리의 별도 작은 모형

차량44명 두 대의 도착·문 열림·개별 승차·출발을 분리한 작은 모형도 구현했습니다.1,296개 사전 명시 가정 조합 중864개에서 관측자가 같은 두 대 안에 탔으며, 합류→탑승53~384초·탑승 후0~30초가 나왔습니다. 이는 여석·도착 지연·승차 처리·배분 가정에 따른 민감도 범위이며 관측 적합도나 신뢰구간이 아닙니다. 가장 잘 맞는 조합을 골라 보정하지 않았습니다. 원래 전역 네트워크 모형은 여전히 도착·탑승·출발을 한 사건으로 근사합니다. 작은 모형을 전역 네트워크에 완전히 결합했다고 주장하지 않습니다.

[작은 모형 실험표](micro_experiment_lock.json) · [전체 민감도 CSV](micro_sensitivity.csv). 실제 도착·문 열림·당시 차내/여석을 추가로 알아야189초를 도착 대기와 승차 처리로 나눌 수 있습니다. 탑승 후30초는 차량 전체 정차시간이 아닙니다.

## 참고한 원리와 직접 확인한 출처

- [OTP2.8 경로 요청 설명](https://docs.opentripplanner.org/en/v2.8.0/RouteRequest/): 물리 보행시간과 선호비용 계수를 구분했습니다. 이 기본값이 서울대 실측 계수라는 뜻은 아닙니다.
- [MATSim2025 scoring 원본](https://raw.githubusercontent.com/matsim-org/matsim-libs/2025.0/matsim/src/main/java/org/matsim/core/config/groups/ScoringConfigGroup.java): 시간·수단별 효용을 분리한다는 구조를 참고했습니다. 효용 수치를 그대로 분 단위로 복사하지 않았습니다.
- [Visum 용량제약 설명](https://cgi.ptvgroup.com/vision-help/VISUM_2025_ENG/Content/1_Benutzermodell%20OeV/1_6_Kapazitaetsbeschraenkung.htm): 용량과 경로 매력을 함께 보되 실제 여석 장부를 분리했습니다.
- [Drabicki 외, 실시간 혼잡정보와 BusMezzo](https://www.tandfonline.com/doi/abs/10.1080/23249935.2020.1809547): 연결편·승차/대기·하차의 순차 판단 구조를 참고했습니다. 원문 PDF 다운로드는 실패했으며 출판사 검색에 노출된 본문 범위만 확인했습니다. 이 프로토타입은 새 조기하차 선택을 구현하지 않았습니다.
- [NIST 위험률 설명](https://www.itl.nist.gov/div898/handbook/apr/section1/apr162.htm): 시간에 따른 누적 위험으로 재생·폴링 주기와 선택 빈도를 분리했습니다. 특정 분포가 서울대에서 추정됐다는 뜻은 아닙니다.
- [서울시 교통요금·환승 안내](https://news.seoul.go.kr/traffic/traffic_price): 성인 교통카드·새 환승 체인 시나리오의 추가요금을 계산했습니다. 개인의 실제 교통카드·기존 결제 이력은 모릅니다.
- [Tobler 원문 저장소](https://escholarship.org/uc/item/05r820mz): 원문 접근이 차단되어 수치 검증을 완료하지 못했습니다. 상대 경사식은 이름 붙인 가정이며 원문을 모두 확인했다고 주장하지 않습니다.
- [서울대 학내외 정류장·운행 안내](https://www.snu.ac.kr/about/gwanak/shuttles/shuttle_stops) · [교내순환 안내](https://www.snu.ac.kr/about/gwanak/shuttles/campus_shuttles). 명목4분/3분 및15~19시 적용 창은 모형 시나리오이며 실제 회차별 출발 기록이 아닙니다.

## 운영과 파일 보존

운영은 [V11 지도](https://snu-shuttle-simulation.vercel.app/)와 [정원·공급 설명서](https://snu-shuttle-simulation.vercel.app/capacity-correction.html)를 유지합니다. 활성 모델261110162302, payload SHA256 f39be2fbe61185f198ac27da9b8b57565cccfb80824e0a4f8f65f68915cbd130입니다. 이는 행동 알고리즘 교체가 아닌 정원·공급 정정입니다.

기준 H 입력·원래 엔진·V7~V11 릴리스·원래9파일럿·중단한 부분 실행·실패 로그를 보존했습니다. 초기 보정용 소스와 UI·공개latest를 프로토타입 코드가 덮어쓰지 않습니다. 후속 개발과 모바일 UI 수정도 이 승인 경계를 유지합니다.
'''
    (ROOT/'RESULTS.md').write_text(note,encoding='utf8')
    (ROOT/'README.md').write_text('''# 분리형 하교길 프로토타입

[첫9파일럿 결과와 근거](RESULTS.md)를 먼저 확인해 주세요. NOT_EVALUABLE·운영 미채택이며, 사용자의 새 지시에 따라 후속 개발을 계속합니다. 운영 V11을 바꾸려면 명시 승인이 필요합니다.

실행: experiment_lock.json의9개 유한 파일럿은 runs/<case>/attempt_04에 완료했습니다. 같은 시도를 덮어쓰지 마세요. analyze.py --resume는 감사·런타임 소스 해시를 확인해 수치 검산 결과를 재사용하고 비교표만 재생성합니다. 새 조건 실행은 새 후보 디렉터리에서 사전 실험표를 만든 뒤 진행합니다. run_remaining.py를 무작정 반복 실행하지 마세요.

build_engine.py는 초기 1회 생성용입니다. 현재engine.py의 후속 FIFO 수정이 검토된 소스이므로 재생성하지 않도록 방어 코드를 넣었습니다. 원래 source_snapshot과 중단·실패 기록은 보존합니다.

prepare.py는 원래 수요 질량·출발·목적지를 보존합니다. physics.py는 물리 시간, preferences.py/fares.py는 선호와 추가요금, capacity.py는 유한 여석, hazard.py는 사건시간, policy.py는 순차선택, engine.py는 실제 차량·여행자 장부, analyze.py는 독립 검산/비교, dwell.py는 별도 승차처리 작은 모형입니다. 내부 숫자를 실측으로 표시하지 마세요.
''',encoding='utf8')
    print('Wrote preserved nine-pilot results, sources, limitations and continuing-development status',flush=True)

if __name__=='__main__':main()
