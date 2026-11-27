"""Local human-readable result and immutable handoff index."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,hashlib,re
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,s):
    assert not p.exists(),p
    p.write_text(s,encoding='utf8')
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');a=p.parse_args();w=Path(a.candidate).resolve();v=read(w/'artifact-verification.json');r=read(w/'recommendation.json');d=read(w/'grid-diagnostics.json');assert v['status']=='PASS'
    lines=[f'# 대기·정문 예측 개선 후보 {w.name}','',
      '최근 반영한 하교 행동을 유지하면서 개인 기다림 분포, 초기 시내버스 승차지 선택, 풀린 뒤 재검토 자격을 수정했습니다. 정원·운행·수요·목적지를 바꾸지 않았습니다.','',
      f"평일5일×기본/피크10조건과 월요일 원인 분리2조건을 각각 한 번 계산했습니다. 동작 검사{v['unit_tests']['total']}개와 초기 선호 경계{v['supplemental_loyalty_guard_checks']}검사, 인원·정원·FIFO·시계·경로 검사를 통과했습니다.",'',
      f"- 전체 기록 최대 연속대기: **{r['max_wait_before']:.2f}→{r['max_wait_after']:.2f}분**.",
      f"-20분 초과 가중 대기 구간: **{r['over20_weight_before']:.3f}→{r['over20_weight_after']:.3f}**, {r['over20_reduction']*100:.1f}% 감소.",
      f"-과거 네 관측×두 배차 조건의 기대 절대오차 합: **{r['reused_field_error_sum_before']:.3f}→{r['reused_field_error_sum_after']:.3f}**, {r['reused_field_error_reduction']*100:.1f}% 감소.",
      f"-평균 모의 총시간 변화: **{r['mean_journey_delta_range'][0]:+.3f}~{r['mean_journey_delta_range'][1]:+.3f}분**. 미완료 가중치 합{r['unserved_weight']:.3f}.",'',
      '가중 구간은 고유 학생 수가 아닙니다. 과거 네 관측은 이미 사용했던 자료이므로 독립 정확도 검증이 아닙니다. 평균·최장 여정이 늘어나는 조건과20분 초과가 남으며, 정문 관측33~39명에 비해 예측이 여전히 작습니다. 운영 교체 권고는 보류합니다.','',
      '## 왜 달라졌나요','',
      '기존20분 초과의97.68%는 모형이 미측정 개인차로 허용한 인내 범위 안이었습니다. 중앙값20분을 유지하되 분산을 좁힌 시나리오와 넓게 유지한 진단을 비교했습니다. 또 기존 초기 선택은 미래 도착 초를 정확히 아는 최소값 하나였는데, 배차 기대 대기·개인 판단 차이·거리 선호를 사용하도록 바꿨습니다. 초기 빈줄 기본 위상만 교체했으며 FIFO/정원 추가 지연과 경로 가능성에는 기존 시각 정보가 남습니다.','',
      '한 번 대안 검토가 허용된 학생이 이후 다시 초기 선호 제약으로 닫히지 않도록 했습니다. 처음 셔틀을 선호하는 행동, 두 번의 실제 모의 만차 경험, 재방문 금지, 무제한 변경·반복 회피, 기숙사 도보·도보 중 승차, 정문 최종 대안과5516 방향 규칙은 유지했습니다. 개인 인내나20분에 무조건 떠나게 하지 않았습니다.','',
      '정문17:03 평균 줄은4.29→13.38명으로 변했지만,16:30~17:04 유입 총량은 약40명 상당으로 비슷합니다. 도착·승차 시간 분포가 달라진 결과이며 실제 정문 학생 수요 전체가 회복됐다고 주장하지 않습니다. 외부 승객·수업 외 사람·개인 선호를 분리할 추가 관측이 필요합니다.','',
      '## 팀 공유 자료','',
      '- [원인·요일별 결과·실측 비교·남은 문제](RESULTS.md)',
      f"- [전체 기록 정류장 표 {d['all_recorded_stop_rows']}행](grid-all-recorded-stops.csv)",
      f"- [전체 기록 진입시각30분 표 {d['all_recorded_half_hour_rows']}행](grid-all-recorded-half-hour-waits.csv)",
      '- [수업 종료부터 도착까지](class-end-journey-comparison.csv)',
      '- [개인 기준 초과·예측·선택 근거 원장](grid-wait-cause-ledger.json)',
      '- [정문 유입·승차 분리](gate-flow-before-after.json)',
      '- [실제 같은17개 모의 버스의 재차 비교](gate-service-diagnosis.json)',
      '- [가정·자료·출처](SOURCES_AND_ASSUMPTIONS.md)',
      '- [고정 입력·실행·모드·난수·운영 보존 검산](artifact-verification.json)',
      '- [내보낸 표 수치 검산](export-reconciliation.json)',
      '- [사전 파일럿 판정](pilot-decision-v2.json)','',
      f"공개 운영 모델은{v['production_model']}로 유지했습니다. 사이트·경로 추천·active/latest를 바꾸지 않았으며, 새 날짜 실측 검증·브라우저 성능·운영 교체가 끝난 모델로 표시하지 않습니다.",'']
    # Keep Markdown list markers readable.
    text='\n'.join(lines).replace('\n-20','\n- 20').replace('\n-과거','\n- 과거').replace('\n-평균','\n- 평균');write(w/'START_HERE.md',text)
    links=0
    for name in ['START_HERE.md','RESULTS.md','SOURCES_AND_ASSUMPTIONS.md']:
        for href in re.findall(r'\]\(([^)]+)\)',(w/name).read_text(encoding='utf8')):
            if href.startswith(('http://','https://','#')):continue
            assert (w/href).resolve().exists(),(name,href);links+=1
    docs=['START_HERE.md','RESULTS.md','SOURCES_AND_ASSUMPTIONS.md','recommendation.json','artifact-verification.json','export-reconciliation.json']
    write(w/'handoff-manifest.json',json.dumps({'release_id':w.name,'created_at':datetime.now(timezone.utc).isoformat(),'document_sha256':{n:sha(w/n) for n in docs},
        'analysis_script_sha256':{p.name:sha(p) for p in ROOT.glob('*.py')},'local_links_verified':links,'new_field_accuracy':'NOT_EVALUATED','production_writes':False},ensure_ascii=False,indent=2))
    print('HANDOFF_READY',w.name,links,'links',flush=True)
if __name__=='__main__':main()
