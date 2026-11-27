"""Copy analysis infrastructure into a separate, versioned R10 review."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parent
def main():
    parent=Path(json.loads((ROOT/'integrated_wait_candidate.json').read_bytes())['directory'])
    work=ROOT.parent/('prototype_review_'+parent.name.rsplit('_',1)[1]);work.mkdir()
    names=['validation_metrics.py','compare_known_queues.py','compare_journey_tails.py','queue_peaks_by_window.py','verify_production_unchanged.py',
           'build_final_review.py','make_final_figures.py','verify_report.py']
    for n in names:shutil.copy2(ROOT/n,work/n)
    p=work/'compare_journey_tails.py';s=p.read_text(encoding='utf8')
    s=s.replace('engineering_snu_half_hour_comparison','engineering_snu_departure_half_hour_comparison')
    s=s.replace('class_end_bin_start','departure_bin_start').replace('class_end_bin_end','departure_bin_end')
    s=s.replace('original class-end time half-hour, NOT queue-entry time or instant queue size','modeled trip departure (prepared plan[4], course-end based), NOT raw class dismissal, queue-entry time or instant queue size')
    p.write_text(s,encoding='utf8')
    p=work/'build_final_review.py';s=p.read_text(encoding='utf8')
    s=s.replace('부모 목요일peak seed0','부모 월요일regular seed1')
    s=s.replace('추가 도킹참조 실험20분 미충족',"추가 도킹참조 판정 {extra_clock['status']}")
    s=s.replace('32개 경계 검산','32개 경계 및3개 통합 검산')
    s=s.replace('현재 최소수정R9는30개 경계 검산과 독립 정적 검토를 거쳤다.','R9는30개 경계 검산을 거쳤지만 추가난수에서21.744분이 남았다. 현재R10은 기존제곱age불편율의 미래성장을 적분하는 가설을 더하고32개 경계·3개 통합 검산과 독립 정적 검토를 거쳤다.')
    s=s.replace('30개 경계검사는','32개 경계·3개 통합 검사는')
    s=s.replace('현재30검사 로그','현재32경계검사 로그')
    s=s.replace('이전CSV의class_end_bin_* 이름만 바로잡았고 수치·모형은 바꾸지 않았다.','현재CSV의departure_bin_* 열로 모형출발시각을 명시했다.')
    # The additional clock can pass or fail. Its result must be derived, never
    # hard-coded from the previous candidate's known failure.
    old='주 운행시계는 이 결과를 보기 전에 사용자 요청에 따라 V8분포로 고정했으며, 추가 실험까지 모두 통과한 것은 아니다.'
    assert old in s;s=s.replace(old,"주 운행시계는 이 결과를 보기 전에 사용자 요청에 따라 V8분포로 고정했다. 추가 실험 통과 여부도 해당 수치와 판정으로 확인한다.",1)
    old='별도 민감도인 정문 도킹 절대시계 참조에서는 최대';assert old in s
    s=s.replace(old,'별도 민감도인 정문 도킹 절대시계 참조의 판정은{extra_clock["status"]}이며 최대',1)
    s=s.replace('[추가 도킹참조 실패 상세](additional_clock_diagnostic.json)에는 대학원생활관21897의 두 가중 통행을 보존했다.',
                '[추가 도킹참조 상세](additional_clock_diagnostic.json)에도 현재후보의 판정을 보존했다. 이전R9의 도킹참조 실패는[원본](../prototype_review_261110185755/additional_clock_diagnostic.json)에 대학원생활관21897의 두 가중 통행으로 남겼다.')
    # A concise new-method section retains both mathematics and identification
    # limitations instead of claiming a proven psychological law.
    marker="      '\\n## 행동/예측과 운행시간의 요인 비교',";assert marker in s
    block='''      '\\n## R10의 미래 대기 불편 적분 가설',
      '\\nR9는고정10조건을통과했으나월요일seed1에서21.744분/0.118735가중통행이남았다. 이전변경4회후에도재검토했으므로횟수소진은아니다. [R9전체판정](../prototype_review_261110185755/RESULTS.md)과 [실패원본](../prototype_validation_261110190402/seed1_long_wait_reconstruction.json)을보존했다.',
      '\\n기존의age²×남은대기식은현재의불편율을고정해앞으로적용하는근사다. 산술오류라고단정하지않고, 미래대기중불편율도증가한다고내다보는별도행동가설을시험했다. 현재대기age=a, 앞으로W, 기존scaleS=600초이면 J(a,W)=W(a²+aW+W²/3)/S²이다. 새/후속정류장의age0항은각Wi³의합이고, 현재물리줄의교차항a²W1+aW1²만추가한다. 첫세제곱을중복가산하지않고, 같은줄의적격노선변경으로age를리셋하지않았다. 대기0이면지난대기를비용/ETA에다시더하지않는다.',
      '\\nJ는초상당의선호항이며 beta_wait*J/60을분상당비용에넣는다. 물리적ETA에더하지않는다. 기존R3의W²길이선호항은유지했고두심리기전이독립이거나실측으로식별됐다는주장은하지않는다. beta_wait=1/full=0예시에서새줄20분의대기관련비용은60→86.667분상당, 이미10분기다린뒤앞으로10분은30→43.333분상당이다. 실제시간은각각20분과10분으로그대로다. scale유지가작은효과를의미하지않는다.',
      '\\n한줄20분의J와두줄10분씩의J는달라새줄이동선호가커질수있으므로변경횟수·누적대기·도보·총시간의꼬리를함께검사한다. 점예측W를넣은J(W)이며불확실한W의기대불편E[J(W)]을계산한것이아니다. 비선형이어서J(E[W])와E[J(W)]는다르고분산·고차모멘트와현장정답이더필요하다.',
      '\\n[수학독립검토](../collaboration/r10_integrated_wait_math_review_20261110/READ_ONLY_REVIEW.md) · [현재코드독립정적검토](../collaboration/r10_static_review_261110193823/READ_ONLY_REVIEW.md) · [통합검사3개로그](../'+candidate.name+'/prediction-integration-tests-retry1.log). 실제승하차엔진·정원·수요·운행시계·무제한변경/위험률코드는R9와같다. 추가수치튜닝은없고식의미래성장가정만바꿨다.',
'''
    s=s.replace(marker,block+marker,1);p.write_text(s,encoding='utf8')
    p=work/'verify_report.py';s=p.read_text(encoding='utf8')
    s=s.replace("engineering_snu_half_hour_comparison.json","engineering_snu_departure_half_hour_comparison.json")
    s=s.replace("assert extra['over20_weight']>0","assert extra['over20_weight']>=0")
    s=s.replace("assert r['all_experiments_including_additional_clock_pass20'] is False","assert r['all_experiments_including_additional_clock_pass20']==(v['over20_episode_weight']<1e-7 and extra['over20_weight']<1e-7)")
    s=s.replace('additional_clock_remains_failed20=True',"additional_clock_remains_failed20=extra['over20_weight']>1e-7")
    p.write_text(s,encoding='utf8')
    (work/'creation_manifest.json').write_text(json.dumps({'candidate':str(parent),'previous_review':str(ROOT),
        'source_files':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names},
        'all_original_R9_files_preserved':True,'new_algorithm_promoted':False,'production_approval_required':True,
        'analysis_adaptations':['Correct departure-bin labels upfront','Reuse debug seed1 instead ofThursday','Derive additional-clock status dynamically','Add integrated-wait assumptions and identification caveats']},ensure_ascii=False,indent=2),encoding='utf8')
    (ROOT/'followup_review_location.json').write_text(json.dumps({'directory':str(work),'candidate':str(parent)},ensure_ascii=False,indent=2),encoding='utf8')
    print(work)
if __name__=='__main__':main()
