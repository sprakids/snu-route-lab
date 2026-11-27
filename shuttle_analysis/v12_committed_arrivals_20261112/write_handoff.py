"""Concrete private review package; no active model or public latest update."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import csv,hashlib,json,re
ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent;PARENT=ANALYSIS/'261112171315'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    assert not p.exists(),str(p);p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
def main():
    w=ANALYSIS/'261112210916';d=read(w/'release_recommendation_final.json');audit=read(w/'artifact_verification_final.json')
    integrity=read(w/'final_verification.json');assert integrity['status']=='PASS'
    assert d['report_sha256']==sha(w/'RESULTS_FINAL.md')
    shared=ANALYSIS/'collaboration/v12_committed_arrivals_261112210916';shared.mkdir(exist_ok=True)
    assert not list(shared.iterdir()),'Preserve any completed delivery'
    runtime=[];old=read(PARENT/'grid-validation.json')['results']
    for r in read(w/'grid-validation.json')['results']:
        b=next(b for b in old if all(b['case'][k]==r['case'][k] for k in ('day','scenario','seed','operations')))
        runtime.append({'weekday':r['case']['day'],'scenario':r['case']['scenario'],
          'parent_seconds':read(Path(b['source_directory'])/'result.json')['elapsed_seconds'],
          'candidate_seconds':read(Path(r['source_directory'])/'result.json')['elapsed_seconds'],
          'interpretation':'Observed local batch elapsed, not controlled benchmark or website loading time'})
    runtime_path=w/'runtime-comparison.csv'
    if runtime_path.exists():
        existing=list(csv.DictReader(runtime_path.open(encoding='utf-8-sig')))
        assert existing==[{k:str(v) for k,v in r.items()} for r in runtime]
    else:
        with runtime_path.open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,list(runtime[0]));writer.writeheader();writer.writerows(runtime)
    peer=ANALYSIS/'collaboration/v12_committed_review_261112210916';e=read(peer/'evidence.json')
    assert isinstance(e['report_sha256'],dict)
    for name,digest in e['report_sha256'].items():assert digest==sha(peer/name),name
    save(w/'analysis_provenance_final.json',{'release_id':w.name,'declared_at':datetime.now(timezone(timedelta(hours=9))).isoformat(),
      'analysis_source_sha256':{p.name:sha(p) for p in ROOT.iterdir() if p.is_file() and p.suffix in ('.py','.md','.json')},
      'peer_final_review_sha256':sha(peer/'READ_ONLY_REVIEW_FINAL.md'),'peer_evidence_sha256':sha(peer/'evidence.json'),
      'parent_report_sha256':sha(PARENT/'RESULTS_FINAL.md'),'current_report_sha256':sha(w/'RESULTS_FINAL.md'),
      'spec_sha256':sha(ROOT/'SPEC.md'),'additional_tests_sha256':sha(ROOT/'test_timed_coverage_addendum.py'),
      'runtime_note':'Both numerical outcomes and batch cost are exposed; runtime not a controlled benchmark',
      'new_day_outcomes_opened':False,'production_writes':False})
    save(shared/'handoff.json',{'status':'PRIVATE_VARIANT_WITH_P99_REVIEW_FLAG','candidate':w.name,'parent':PARENT.name,
      'canonical_report':str(w/'RESULTS_FINAL.md'),'result':d,'verification':audit,
      'operating_model':'capacity_v11/261110162302','information_scope':'Already-started simulated approach/ready intentions, not actual student GPS or live demand',
      'original_pilot_budget_failure_preserved':True,'integration_rule':'Preserve V11 active routing/lab/latest until explicit user approval. Do not convert synthetic flows into live individual ETA or numeric observed occupancy.',
      'production_writes':False})
    t=d['target_trace'];delta=1-d['primary_loss_after']/d['primary_loss_before']
    lines=['# 후반 도보 선호 유지와 탑승 예측 보완 공유','',
      '[최종 보고서](../../261112210916/RESULTS_FINAL.md), [전달값](handoff.json), [정보 가정·명세](../../v12_committed_arrivals_20261112/SPEC.md), [독립 정적 검토](../v12_committed_review_261112210916/READ_ONLY_REVIEW_FINAL.md).','',
      '사용자 확인대로 후반 도보 선호·누적대기 부담·변경횟수 확률·alpha1.125·원본 수요·차량 시계/정원을 유지했습니다. 현재 큐 외에 이미 출발해 걷거나 준비 중인 모의 수요만 미래 FIFO 예측에 반영하고 거절 비용 성분 로그를 보완했습니다. 미래 미출발/사후 큐는 입력하지 않았습니다.','',
      f"과거 방향확인3점 손실 {d['primary_loss_before']:.6f}→{d['primary_loss_after']:.6f}, 추가 감소 {delta*100:.2f}%입니다. 개선은 정문1관측이며 나머지3개는1e-7내 동일합니다. 독립 현장 검증이 아닙니다.",'',
      f"최대 연속대기는 모든 기록에서 {d['maximum_all_recorded_continuous_wait_min']:.6f}분,20분 초과와 미완료 가중치는0입니다. 평균 총시간 감소{d['mean_total_improved']}/10조건, p99감소{d['p99_total_improved']}/10조건, 최대 감소{d['max_total_improved']}/10조건입니다. 모든 지표 개선은 아닙니다.",'',
      f"추적 조각은 {t[0]['weighted_mean_total_min']:.3f}→{t[1]['weighted_mean_total_min']:.3f}분입니다. 질량을 보존했고 후반 도보 선택을 유지했습니다. 전체 원표와 분포는 후보 폴더에 있습니다.",'',
      '파일럿 화요일p99가1.088분 늘어 원래1분 검토 예산을5.284초 넘었습니다. 이 실패를 보존한 채 더 넓은 진단을 수행한 것입니다. 원래 예산을 통과했다고 표시하거나 임의로 기준을 바꾸지 않습니다.','',
      '현재 의도·준비시각을 예측기가 안다는 모의 정보 가정입니다. 미출발 수요·차내 승객의 미래 환승·이후 실제 재선택까지 완전히 예측한 것은 아닙니다. 사이트 또는 경로 API가 실제 학생을 추적한다고 표시해서는 안 됩니다.','',
      f"시험76개와 추가3개, 최종 관련13개 재확인,10조건 원장 감사, 소스{integrity['local_source_hash_checks']}확인·공개8HTTP읽기·향후22해시 확인을 기록했습니다. 전체정류장{audit['stop_rows']}행·30분{audit['half_hour_rows']}행·줄대조48행·분포40행·수업종료40행입니다. 배치 실행시간도runtime-comparison.csv에 공개했습니다.",'',
      '운영V11과171315·탈락/실패 증거를 보존했습니다. 사용자 명시 승인 전 활성 모델·실험실 기본값·latest.json을 전환하거나 배포하지 않습니다.','']
    (shared/'README.md').write_text('\n'.join(lines),encoding='utf8')
    (ROOT/'README.md').write_text('# 작은 추가 수정 완료\n\n[최종 결과](../261112210916/RESULTS_FINAL.md), [구현 에이전트 전달](../collaboration/v12_committed_arrivals_261112210916/README.md)을 확인하세요. 후반 도보 선호는 유지했습니다. 파일럿p99 검토예산 초과와 남은 정보 한계도 공개합니다. 운영V11은 유지했습니다.\n',encoding='utf8')
    for p in (shared/'README.md',ROOT/'README.md'):
        for href in re.findall(r'\]\(([^)]+)\)',p.read_text(encoding='utf8')):assert (p.parent/href).resolve().exists(),href
    print('HANDOFF_COMPLETE',shared,flush=True)
if __name__=='__main__':main()
