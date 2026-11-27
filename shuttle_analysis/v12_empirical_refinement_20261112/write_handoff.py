"""Share reviewable private results and freeze analysis provenance, no live changes."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent;WORK=ANALYSIS/'261112171315'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    assert not p.exists(),str(p);p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
def main():
    d=read(WORK/'release_recommendation_final.json');check=read(WORK/'artifact_verification_final.json')
    public=read(WORK/'final_verification.json');assert public['status']=='PASS'
    shared=ANALYSIS/'collaboration/v12_empirical_refinement_261112171315';shared.mkdir()
    papers=read(ANALYSIS/'collaboration/v12_additional_papers_20261112/source_manifest.json')
    source_root=ANALYSIS/'collaboration/v12_additional_papers_20261112'
    for paper in papers['papers']:
        assert sha(source_root/paper['file'])==paper['sha256']
    sources={p.name:sha(p) for p in ROOT.glob('*.py')}
    sources.update({p.name:sha(p) for p in ROOT.glob('*.json')})
    sources['ADDITIONAL_THEORY.md']=sha(ROOT/'ADDITIONAL_THEORY.md')
    provenance={'release_id':WORK.name,'created_at':datetime.now(timezone.utc).isoformat(),
      'analysis_source_sha256':sources,
      'legacy_minute_statistics_helper_sha256':sha(ANALYSIS/'v12_build_2026-11-12/validation_v12.py'),
      'peer_primary_manifest_sha256':sha(source_root/'source_manifest.json'),
      'new_primary_papers':papers['papers'],
      'additional_primary_context':{'title':'Kaparias, Rossetti and Trozzi2015, Analysing passenger arrivals rates and waiting time at bus stops',
        'url':'https://openaccess.city.ac.uk/id/eprint/6257/',
        'role':'Arrival, actual waiting and perceived waiting measurement scope; no numeric transfer of foreign distributions'},
      'inheritance_source_inventory':'../261112111627/evidence_inventory_final.json',
      'canonical_report_sha256':sha(WORK/'RESULTS_FINAL.md'),'artifact_check_sha256':sha(WORK/'artifact_verification_final.json'),
      'runtime_future_freeze_sha256':sha(WORK/'future_evaluation_plan.json'),
      'no_new_day_outcomes_opened':True,'production_writes':False}
    save(WORK/'analysis_provenance_final.json',provenance)
    payload={'status':'PRIVATE_CANDIDATE_READY_FOR_REVIEW','candidate':WORK.name,'parent':'261112132736',
      'operating_model':'capacity_v11/261110162302','canonical_report':str(WORK/'RESULTS_FINAL.md'),
      'result':d,'artifact_verification':check,
      'public_readback_status':public['status'],'runtime_source_hash_checks':public['local_source_hash_checks'],
      'future_frozen_files':public['future_hashes_verified'],
      'integration_rule':'Do not replace active routing model, lab default, public latest.json or deploy prototype until explicit user approval. Existing V11 preserved.',
      'tail_review':'Read-only trace review requested separately; no causal isolation or complete continuing-value repair claimed.',
      'production_writes':False}
    save(shared/'handoff.json',payload)
    md=[f'# 추가 논문·실측 정합성 보정 공유 — {WORK.name}','',
      '비운영 후보입니다. 운영 V11은 그대로 유지하고, 사용자 명시 승인 전에는 경로 앱의 활성 모델·실험실 기본값·공개latest.json을 전환하지 않습니다.','',
      '[최종 보고서](../../261112171315/RESULTS_FINAL.md), [상세 전달값](handoff.json), [새 논문과 가정](../../v12_empirical_refinement_20261112/ADDITIONAL_THEORY.md), [소스·분석 계보](../../261112171315/analysis_provenance_final.json).','',
      '- 알려진 선행 승차를 미래 차 혼잡 비용에 반영하고, 과거 제약으로 생긴 예약 용량은 실제 승객과 구분했습니다.',
      '- 기존 동결 개인 보행 배율을 복원했습니다. 서울대 실측 속도분포가 아닙니다.',
      '- 미측정 수업 종료→출발 시차의 공통 배율α1.125를 과거 세 방향확인 관측에 후향 보정했습니다. 유효 시각 조정이며 실제 퇴실 행동의 식별이 아닙니다.',
      f"- 정규화 손실은 {d['primary_normalized_loss_before']:.6f}→{d['primary_normalized_loss_after']:.6f}, 감소 {d['primary_loss_decrease_fraction']*100:.2f}%입니다. 네 과거 관측 중3건의 절대 구간 오차가 감소했고, 월16:53행정관은9.888→11.360명분으로 악화했습니다.",
      f"- 평일×regular/peak10조건,67개 시험 통과. **모든 기록 시각**의 최대 연속 대기는 {d['maximum_all_recorded_continuous_wait_min']:.6f}분입니다. 분석창 안 최대18.728670분과 구분합니다.20분 초과·미완료 가중치는0입니다.",
      '- 출발→목적지 평균은7/10조건에서 줄었지만 수업 종료→목적지 평균은10조건 모두0.22~0.53분 늘었습니다. 예측 보정을 서비스 개선 효과로 해석하지 않습니다.',
      '- 최장 총시간은103.706497분입니다. 화요일의 한 희소한 조각에서27.461→101.474분/7회변경이 남습니다.20분 통과가 전체 경로의 현실성을 보장하지 않으며 별도 읽기 전용 원인 검토를 요청했습니다.',
      '- 40명 참고값 초과는8/40정류장×조건이며 법대·사회대입구21270이 남습니다. 수요를 잘라내거나 정원·배차를 늘려 통과시키지 않았습니다.',
      '- 새 날짜 정답은 열지 않았습니다. 과거4점은 재사용한 보정/선택 자료이며 독립 정확도 검증이 아닙니다. 문화관 방향도 미확정입니다.',
      f"- 전체정류장{check['stop_rows']}행·30분{check['half_hour_rows']}행·줄대조{check['field_rows']}행·분포40행·수업종료기준40행을 보존했습니다. 원표는 후보 폴더에 있습니다.",
      f"- 소스{public['local_source_hash_checks']}확인·공개8HTTP읽기·향후평가22파일해시 확인이 통과했습니다. 운영 쓰기는 없습니다.",'']
    (shared/'README.md').write_text('\n'.join(md),encoding='utf8')
    index=ROOT/'README.md';assert not index.exists()
    index.write_text('# V12 추가 논문과 실측 정합성 개선\n\n[최종 후보 보고서](../261112171315/RESULTS_FINAL.md)와 [구현 에이전트 전달](../collaboration/v12_empirical_refinement_261112171315/README.md)을 보세요.\n\n과거 관측에 맞춘 제한된 후향 보정이며 운영V11은 유지했습니다. 실패 후보·수업종료기준 부담·긴 희소 여정의 퇴행도 보존했습니다.\n',encoding='utf8')
    print('HANDOFF_READY',shared,flush=True)
if __name__=='__main__':main()
