"""Align analysis/report labels with the new, separately registered mechanism."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib
ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent
w=ANALYSIS/'261116122336';D=ANALYSIS/'261116112731';E=ANALYSIS/'261116120358'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    assert not p.exists(),p
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
assert not (ROOT/'reporting-ready.json').exists()
for name in ['class_end_journey_metrics.py','diagnose_gate_flow.py','gate_service_diagnosis.py','physical_components.py','verify_artifacts.py']:
    p=ROOT/name;t=p.read_text(encoding='utf8');p.write_text(t.replace('261116105704','261116010854'),encoding='utf8')
p=ROOT/'verify_artifacts.py';t=p.read_text(encoding='utf8')
start=t.index('    units={}\n');end=t.index('    links=0\n',start)
t=t[:start]+'''    units={}
    for n in ['enabled-final.log','legacy-final.log']:
        content=(w/n).read_text(encoding='utf8');matches=re.findall(r'Ran (\\d+) tests?',content)
        assert len(matches)==1 and re.search(r'^OK\\s*$',content,re.M)
        units[n]=int(matches[0])
    assert units=={'enabled-final.log':129,'legacy-final.log':89}
    assert read(w/'static-current-pressure-proof.json')['status']=='PASS_STATIC_CURRENT_PRESSURE_SCOPE'
'''+t[end:]
p.write_text(t,encoding='utf8')
p=ROOT/'report_results.py';t=p.read_text(encoding='utf8')
t=t.replace('추가 수정의 직접 대조군은 중간 후보261116105704이며 파일럿 판정·기본 비교CSV는 그 기준입니다. 두 기준을 구분합니다.',
            '파일럿 판정·기본 비교CSV도 요청 직전 기준입니다. 개발 부모112731과 중간105704·실패한120358은 별도 기록으로 구분합니다.')
a='7. 인지 일치만 적용한112731은 월·화 평균 귀가시간이 각각3.645/3.490분 늘어 채택하지 않았습니다. 이번은 그 행동을 유지하면서 실측 미추정 이차·삼차 대기 추가 부담만 제외한 사전 등록 민감도입니다. 원래 선형대기 성향과 현재 줄의 만차 부담,개인P와 연령·만차에 따른 재검토는 유지했습니다. 비선형 효용이 중복 버그라고 확정하거나 선형 효용을 서울대 실측으로 추정한 것은 아닙니다.'
b='7. 인지 일치만 적용한112731은 월·화 평균 귀가시간이3.645/3.490분 늘었고,비선형 대기 부담만 제외한120358도6.344/5.028분 늘어 채택하지 않았습니다. 이번은112731의 비용식과 최신 인지를 유지한 별도 상태 분리입니다. 한 번 선호가 풀린 뒤 수단을 자유롭게 고르는 상태와 현재 줄에서 다시 변경해야 하는 사유를 구분했습니다. 새 정류장에서도 현재 예상 대기·실제 만차/추가 통과·운행부재의 기존 조건이 있어야 재검토합니다. 수단 자유를 다시 잠그거나 개인P·시계·만차를 지우지 않습니다. 기존의 영구재검토는 단위시험에도 고정된 의도적 가정이었으므로 우연한 코딩오류라고 부르지 않습니다.'
assert a in t;t=t.replace(a,b)
t=t.replace('[마지막 민감도 사전 계획](../v12_linear_wait_sensitivity_20261116/PROTOCOL.md)', '[현재 줄의 변경 사유 분리 사전 계획](../v12_current_pressure_20261116/PROTOCOL.md)')
t=t.replace("'intermediate_prototype_cases':22", "'intermediate_prototype_cases':24")
p.write_text(t,encoding='utf8')

text=(ANALYSIS/'v12_linear_wait_sensitivity_20261116/SOURCES_AND_ASSUMPTIONS.md').read_text(encoding='utf8')
text=text.replace('사용자 설명을 초기·이후에 모두 적용한112731 및120358을 구분합니다.',
                  '사용자 설명을 초기·이후에 모두 적용한112731·120358과 현재 줄의 변경 사유를 분리한122336을 구분합니다.')
text+='''
## 이번122336의 별도 수정

이 후보는112731의 기존 비선형 비용식과 최신 환승 대기 미예견을 유지합니다.120358의 선형 비용 민감도는 실패해 채택하지 않았습니다.122336은 수단의 영구적인 자유와 현재 정류장에서 다시 물리 경로를 바꿀 사유를 분리합니다. 새 줄의 예상 대기·실제 만차/추가 통과·운행부재가 기존 기준을 충족할 때만 다시 검토합니다. 원래 선호·개인P·시계·누적 경험을 새로 뽑거나 삭제하지 않고 변경횟수 상한·쿨다운도 추가하지 않았습니다.

기존 ‘한 번 풀리면 항상 stressed’ 규칙은 의도적으로 시험된 가정이었습니다. 새 분리는 사용자의 반복 혼잡 설명에 맞춘 행동 가정 교정이며 단순 오탈자 수정이나 실측으로 식별한 인과효과로 부르지 않습니다. [사전 계획](PROTOCOL.md)을 함께 보십시오.
'''
(ROOT/'SOURCES_AND_ASSUMPTIONS.md').write_text(text,encoding='utf8')

t=(ANALYSIS/'v12_linear_wait_sensitivity_20261116/build_final_review.py').read_text(encoding='utf8')
t=t.replace("'261116112731','261116120358']", "'261116112731','261116120358','261116122336']")
t=t.replace("E='261116120358'", "E='261116122336'")
t=t.replace('초기·이후 모두 미예견한112731과 마지막120358의 파일럿은 아래에 실패 결과까지 공개합니다.',
            '초기·이후 모두 미예견한112731·120358과 현재 줄의 변경 사유를 분리한122336은 아래에 실패 결과까지 공개합니다.')
t=t.replace('마지막 두 후보112731·120358은105704의 월·화 기본배차와 비교합니다.',
            '112731·120358은105704의 월·화 기본배차와 비교하며,122336은 요청 직전010854와 비교합니다.')
t=t.replace('120358은 같은 미예견 행동을 유지하고 실측 미추정 이차·삼차 대기 추가 부담만 제외한 마지막 민감도입니다. 선형 대기 성향과 만차 부담,개인 인내·재검토 기회는 유지했습니다.',
            '120358은 같은 미예견 행동을 유지하고 이차·삼차 추가 부담만 제외했으나 월·화 평균 귀가시간이6.344/5.028분 늘어 실패했습니다.122336은112731의 비용식을 유지한 채 수단 자유와 현재 줄의 변경 사유를 분리했습니다. 한번 자유를 얻었다는 사실만으로 새 줄의 문제를 자동 부여하지 않습니다. 현재 예상 대기·만차/추가 통과·운행부재 조건은 그대로입니다.')
t=t.replace('f"120358의 월·화 평균 총시간 변화는 각각', 'f"122336의 요청 직전 대비 월·화 평균 총시간 변화는 각각')
(ROOT/'build_final_review.py').write_text(t,encoding='utf8')

names=read(next((w/'runs').glob('*/attempt_01/started.json')))['code_sha256']
changed=[n for n in names if sha(D/n)!=sha(w/n)]
assert changed==['behavioral_policy.py'],changed
a=read(D/'config.json');b=read(w/'config.json')
numbers={k:v for k,v in a.items() if type(v) in (int,float)}
assert all(b[k]==v for k,v in numbers.items())
frozen=read(w/'repair_manifest.json')['frozen_payloads']
assert all(sha(w/n)==sha(D/n)==h for n,h in frozen.items())
save(w/'static-current-pressure-proof.json',{'status':'PASS_STATIC_CURRENT_PRESSURE_SCOPE',
    'changed_runtime_modules':changed,'runtime_modules':17,'existing_numeric_parameters_unchanged':numbers,
    'unchanged_frozen_payloads':len(frozen),'configuration_differences':{k:[a.get(k),b.get(k)] for k in set(a)|set(b) if a.get(k)!=b.get(k)},
    'policy_sha256_equal_to_D':sha(w/'policy.py')==sha(D/'policy.py'),'production_writes':False})
save(ROOT/'reporting-ready.json',{'created_at':datetime.now(timezone.utc).isoformat(),'release_id':w.name,
    'scope':'Analysis labels and report-only scripts aligned; frozen model source/protocol/config unchanged.'})
print('PRESSURE_REPORTING_READY',w.name,changed)
