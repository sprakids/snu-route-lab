"""One bounded, separately frozen sensitivity; preserve all earlier evidence."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib, json, shutil

HERE = Path(__file__).resolve().parent
ANALYSIS = HERE.parent
PARENT = ANALYSIS / '261116112731'
COMMON = ANALYSIS / 'v12_linear_wait_sensitivity_20261116'

def read(p): return json.loads(p.read_bytes())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p, value):
    assert not p.exists(), p
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')

def main():
    assert not COMMON.exists()
    COMMON.mkdir()
    for p in HERE.glob('*.py'):
        if p.name != Path(__file__).name:
            shutil.copy2(p, COMMON / p.name)
    stamp = datetime.now(timezone(timedelta(hours=9))).strftime('%y%m%d%H%M%S')
    work = ANALYSIS / stamp
    work.mkdir()
    old = read(PARENT / 'repair_manifest.json')
    for p in PARENT.glob('*.py'): shutil.copy2(p, work / p.name)
    for name in ['input_manifest.json', 'capacity44_amendment.json', 'pair_amendment.json', 'USER_DIRECTIVE.md']:
        shutil.copy2(PARENT / name, work / name)
    for name, digest in old['frozen_payloads'].items():
        assert sha(PARENT / name) == digest
        dest = work / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PARENT / name, dest)
    for p in PARENT.glob('physical_paths_*.json.gz'): shutil.copy2(p, work / p.name)
    p = work / 'policy.py'
    text = p.read_text(encoding='utf8')
    needle = "            if config.get('waiting_burden_scope')=='whole_journey':\n"
    assert text.count(needle) == 1
    text = text.replace(needle, """            if config.get('student_strategy') and config.get('student_wait_discomfort_model')=='linear_future_with_failure':
                # Sensitivity, not an empirically identified SNU utility model.
                # Actual elapsed wait still governs patience/review opportunities.
                # Preserve the inherited current-queue denied-bus penalty.
                if not changing:
                    base+=state['traits'].wait*config.get('waiting_discomfort_full_sensitivity',0.)*state['full_passes']*pred.first_wait/60
                return base
""" + needle)
    p.write_text(text, encoding='utf8')
    cfg = read(PARENT / 'config.json')
    cfg.update(release_id=stamp, version_family='V12-linear-future-wait-sensitivity',
        student_wait_discomfort_model='linear_future_with_failure',
        wait_discomfort_interpretation='Bounded sensitivity removes only the unmeasured quadratic/cubic future-wait increment from student decision utility. Existing linear waiting tastes, current-queue full-bus penalty, patience, age/full review hazard, unlimited reroutes and repeated-walk rule remain. No claim that nonlinear preferences are a coding error or that linearity is identified for SNU.',
        sensitivity_interpretation='Literal user clarification retained: future transfer waiting is not anticipated in initial or later choice. Perceived costs remain separate from operational forecasts and realized physical FIFO/capacity/time.')
    save(work / 'config.json', cfg)
    days = [('월','mon'),('화','tue'),('수','wed'),('목','thu'),('금','fri')]
    cases = [{'case':f'linear-combined-{scenario}-{eng}', 'mode':'combined', 'day':day, 'scenario':scenario,
              'seed':0, 'operations':'v12_empirical'} for scenario in ['regular','peak'] for day,eng in days]
    selection = ('Exactly two main Monday/Tuesday regular pilot cases once each; no duplicate diagnostic model run. '
                 'Compare to fully evaluated C261116105704. Require physical and user-behavior gates, no unserved, '
                 'nonworsening sum of all-recorded over20 episode mass and reused four-observation expected error, '
                 'nonworsening pilot maximum wait and each weekday mean journey, with one strict improvement. '
                 'Only then execute eight remaining main cases once. Report all worsening tails and law queues. '
                 'No coefficient search or further post-outcome tuning; keep all negative evidence.')
    save(work / 'experiment_lock.json', {'status':'REGISTERED_BEFORE_EXECUTION','release_id':stamp,
         'implementation_parent':str(PARENT),'comparison_parent':'261116105704','pilot_cases':cases,
         'selection_rule':selection,'new_day_outcomes_opened':False,'production_replacement_allowed':False,
         'retained_user_behavior':read(PARENT / 'experiment_lock.json')['retained_user_behavior']})
    protected = old['protected'].copy()
    for folder in [PARENT, ANALYSIS/'261116105704']:
        for p in folder.iterdir():
            if p.is_file(): protected[str(p)] = sha(p)
    save(work / 'repair_manifest.json', {'parent':str(PARENT),'comparison_parent':'261116105704',
         'release_id':stamp,'protected':protected,'frozen_payloads':old['frozen_payloads'],
         'config_sha256':sha(work/'config.json'),'production_writes':False})
    protocol = '''# 마지막 대기 비용 민감도 비교

사용자의 주노선 승차 기준과 환승 대기 미예견을 초기·이후 선택 모두에 유지한다. 이전112731은 대기 최댓값을 일부 줄였지만 평균 귀가시간이 월3.645분·화3.490분 늘고20분초과 및 관측 오차가 악화되어 채택하지 않았다.

기존 추가 대기 부담 G(A+W)-G(A)는 실측으로 추정되지 않은 이차·삼차항이다. 이를 코딩 오류나 중복 계산이라고 확정하지 않는다. 개인 인내와 재검토 기회는 별개 장치이므로 그대로 둔다. 마지막 한 가지 민감도로 학생 선택비용에서 이 추가 다항식만 제외한다. 원래 개인별 선형 대기·보행·차내·환승·변경·혼잡 계수와 현재 줄의 만차 추가 부담, 확률적 재검토, 개인P, 도보·되돌아가지 않기·정문 최후 대안은 유지한다.

''' + selection + '''

20분이나40명을 강제로 만족시키지 않는다. 정원·수요·목적지·출발·운행·숫자 계수·새날짜 실측은 건드리지 않는다. D의 효용·인지값은 실제 이동시간이 아니며 물리모형은 그대로이다. 유럽 평가 지침의 선형 대기 가중은 일반적인 비교 구조의 예시일 뿐 서울대 행동 계수의 근거는 아니다. 권고배율2도 적용하지 않는다.

배경 원문: https://www.gov.uk/government/publications/webtag-tag-unit-a1-3-user-and-provider-impacts-march-2017 (May2026 PDF,4.4.1~4.4.2). 공개V11·경로API·active/latest는 변경하지 않는다.
'''
    (COMMON / 'PROTOCOL.md').write_text(protocol, encoding='utf8')
    p = COMMON / 'check_pilot.py'
    t = p.read_text(encoding='utf8')
    needle = "and max(new_max)<=max(old_max)+1e-7 and (after<before-1e-7 or e1<e0-1e-7)"
    assert needle in t
    p.write_text(t.replace(needle, "and max(new_max)<=max(old_max)+1e-7 and all(x<=1e-7 for x in means) and (after<before-1e-7 or e1<e0-1e-7)"), encoding='utf8')
    # Legacy nonlinear-component tests remain meaningful with student wrapper off.
    p = COMMON / 'check_legacy.py'
    t = p.read_text(encoding='utf8')
    t = t.replace("'test_review_perception']", "'test_review_perception','test_linear_wait_sensitivity']")
    p.write_text(t, encoding='utf8')
    save(COMMON / 'candidate.json', {'release_id':stamp,'path':str(work),'parent':str(PARENT)})
    print(work, flush=True)

if __name__ == '__main__': main()
