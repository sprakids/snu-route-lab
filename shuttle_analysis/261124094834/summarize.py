"""Summarize validated R and capacity-matched controls. Run after all cases finish."""
import csv
import hashlib
import json
import math
from pathlib import Path
from population import DAILY_TRIP_LIMIT,check_result

HERE=Path(__file__).resolve().parent
CONTROL=HERE.parent/'261124094645'
DAYS=dict(zip('월화수목금',['mon','tue','wed','thu','fri']))

def load(p):
    return json.loads(p.read_bytes())

def receipt(directory,case):
    location=directory/'runs'/case
    if directory==HERE and case.startswith('dry-50-') and not location.exists():
        location=directory/'runs'/case.removeprefix('dry-50-')
    found=list(location.glob('attempt-*/result.json'))
    if len(found)!=1:
        raise RuntimeError(f'Expected one verified case: {directory.name}/{case}')
    path=found[0]
    r=load(path)
    assert r['status']=='verified' and r['core']['status']=='PASS' and r['candidate']['capacity']==44
    assert r['invariants']['capacity_violations']==0
    return path,r

def fmt(v):
    return f'{v:,.2f}'

def summarize():
    caps=load(HERE/'daily_limit_verification.json')['days']
    execution_sources=[]
    for meta_path in sorted((HERE/'runs').glob('*/attempt-*/case.json')):
        meta=load(meta_path)
        receipt_file=meta_path.parent/'result.json'
        results=load(receipt_file)
        check_result(results)
        has_guard='population.py' in meta['sha256']
        source_path=(HERE/'pre_population_run.py.txt' if not has_guard else
                     HERE/'guarded_trial_run.py.txt' if 'weather' in meta else HERE/'run.py')
        actual_source=hashlib.sha256(source_path.read_bytes()).hexdigest()
        day=meta['day']
        assert caps[day]['all_plan_weights_bit_identical'] and not caps[day]['binding']
        assert math.isclose(results['invariants']['input_weight'],caps[day]['admitted'],abs_tol=1e-6)
        execution_sources.append(dict(case=meta['case'],guard_in_running_worker=has_guard,
            effective_runner_sha256=actual_source,on_disk_runner_sha256_at_recording=meta['sha256']['run.py'],
            daily_total=caps[day]['admitted'],cap_does_not_change_any_input_weight=True))
    assert len(execution_sources)==10
    output=[]
    compar=[]
    lines=['# V11 기반 하교 모형 R261124094834','',
        '행정관↔대학동 셔틀의 한 대당 승객 정원을 44명으로 정정하고, 수업 종료 시각별 즉시 하교확률과 집까지의 도보 선택을 적용했습니다. 하루 전체 하교 이동 상한은 사용자 지정 30,000건입니다.','',
        '교외에 다녀온 뒤 다시 하교하는 이동을 수용하도록 일별 이동 건수를 단위로 씁니다. 정류장 대기·승차·환승·경로 변경은 출발 시 부여한 한 건의 이동에 속합니다. 수강편람으로 생성한 가중 이동이므로 한 사람의 실제 재출입 횟수는 미측정입니다.','',
        '## 수업이 끝난 뒤 하교할 확률','',
        '각 수업의 실제 종료 분에 확률을 적용합니다. 15:00부터 16:00까지가 최고이고 앞뒤는 선형으로 연결했습니다. 16:00 정각에 끝난 수업도 최고 구간에 포함합니다. 수업별 확률의 변화는 기존 50%에서 최대 5%포인트입니다. 기존과 같은 요일별 총량을 유지하도록 수강인원으로 가중했고, 일일 한도가 걸리면 모든 출발 수요를 같은 비율로 줄입니다. 평일 시간표의 6,201개 수업 종료 기록에 적용했습니다. 나머지 학생의 이후 활동과 귀가 시각은 이 세션 자료로는 알 수 없습니다.','',
        '|요일|12시 종료|15~16시 종료|18시 종료|하루 하교 이동(건 상당)|30,000건까지 여유|',
        '|---|---:|---:|---:|---:|---:|']
    for d,did in DAYS.items():
        path,r=receipt(HERE,f'dry-50-regular-{did}')
        profile=load(path.parent/'departure_profile.json')
        p=profile['hourly_clock_rates'];cap=caps[d]
        assert cap['all_plan_weights_bit_identical'] and profile['total_trip_mass']==cap['admitted']<=DAILY_TRIP_LIMIT
        lines.append(f"|{d}|{p['12']:.1%}|{p['15']:.1%}|{p['18']:.1%}|{cap['admitted']:,.1f}|{cap['remaining']:,.1f}|")
        for service in ('regular','peak'):
            name=f'dry-50-{service}-{did}'
            rp,new=receipt(HERE,name)
            _,capacity=receipt(CONTROL,f'dry-0-{service}-{did}')
            _,walk=receipt(CONTROL,name)
            for model in (new,capacity,walk):
                assert model['invariants']['unserved_trip_weight']>=0
            output.append(dict(day=d,service=service,version=new['model_id'],capacity_people=new['capacity'],
                daily_trip_count=check_result(new)['entered'],
                v11_cap44_queue=capacity['candidate']['queue_after_1700'],cap44_walk_queue=walk['candidate']['queue_after_1700'],
                final_queue=new['candidate']['queue_after_1700'],final_boarded=new['candidate']['boarded'],
                final_ready_queue=new['candidate']['ready_left'],max_stop_wait_minutes=new['max_wait_min'],
                over20_episode_weight=new['over20_weight'],unserved=new['invariants']['unserved_trip_weight'],
                capacity_violations=new['invariants']['capacity_violations'],fifo_checks=new['core']['checks']['fifo_events'],
                per_stop_file=str((rp.parent/'all_stop_waits.json').relative_to(HERE))))
    lines.extend(['','월요일 15:00~15:30 종료 수업의 수강인원 합은 5,060명입니다. 즉시 하교 수요는 기존 2,530건에서 약 2,738건으로 늘었습니다. 절대 규모가 가장 큰 30분 구간은 월요일 15:00, 수요일 12:00, 화·목·금요일 16:30에 시작합니다. 수업별 하교확률과 해당 시각에 끝나는 수업의 수강인원이 함께 수요를 결정합니다.','',
        '[시간대별 확률 곡선](월요일_하교확률.svg) · [요일별 30분 수요와 분모](요일별_30분_하교수요.csv) · [하루 상한 검산](daily_limit_verification.json)','',
        '## 월요일 행정관 대학동행','',
        '사용자는 비가 많이 온 월요일 16:59에 만차 출발 후 1명이 남았다고 보고했습니다. 모형의 가장 가까운 승차 처리는 17:00이고, 아래 값은 그 처리 직후입니다. 지도 대기는 승차 준비 중인 학생까지 포함합니다. 출발 전 줄과 해당 정류장에서 실제 탑승한 인원은 미측정입니다.','',
        '|조건|정원|탑승|승차 가능 상태로 남은 줄|지도 전체 잔여 줄|','|---|---:|---:|---:|---:|'])
    for label,dr,case,selector in [
        ('공개 V11에 저장된 당시 설정',CONTROL,'dry-0-regular-mon','baseline'),
        ('정원만 수정, 기존 50% 하교확률',CONTROL,'dry-0-regular-mon','candidate'),
        ('정원 수정 + 도보 선택, 기존 50% 하교확률',CONTROL,'dry-50-regular-mon','candidate'),
        ('최종 R, 도보 선택 + 시간별 하교확률',HERE,'dry-50-regular-mon','candidate')]:
        p,res=receipt(dr,case);m=res[selector]
        compar.append(dict(label=label,case=case,directory=dr.name,**m))
        lines.append(f"|{label}|{m['capacity']}|{fmt(m['boarded'])}|{fmt(m['ready_left'])}|{fmt(m['queue_after_1700'])}|")
    lines.extend(['','최종 R은 날씨 입력 없이 일반 평일 조건 하나를 사용합니다. 도보 전환율 50%의 분모는 원래 대학동 셔틀을 첫 수단으로 선택한 대학동행 수요입니다. 집까지 가까운 출발지일수록 도보를 선택할 가능성이 높습니다. 직접 도보를 선택한 계획은 V11 방식대로 해당 보행 경로로 집까지 이동합니다. 기준·피크는 V11에서 제공하는 두 가지 배차 계획입니다.','',
        '44명 대조군의 지도 잔여 19.79명에서 도보 선택을 적용하면 13.79명이 되고, 시간별 하교확률까지 적용하면 14.36명입니다. 최종 R은 만차를 재현했으나 관측된 잔여 1명에 비해 줄이 여전히 큽니다. 실제 출발은 16:59분 중이었고 모형은 17:00에 승차 처리합니다.','',
        '## 운행 검증','',
        f"평소 조건 월~금 × 기본·피크 배차 10개에서 단일 정류장 최장 대기는 {max(r['max_stop_wait_minutes'] for r in output):.2f}분입니다. 20분 초과 대기 사건의 가중 합은 {sum(r['over20_episode_weight'] for r in output):.2f}건, 미처리 이동의 가중 합은 {sum(r['unserved'] for r in output):.2f}건, 정원 위반은 {sum(r['capacity_violations'] for r in output)}건입니다. 각 운행에서 전체 정류장의 줄과 FIFO 승차 순서, 경로별 가중 인원 보존을 검산했습니다. [요일·운행별 결과](요일별_정원44명_비교.csv)",'',
        '수업 후 하교 수요 상한은 차량 배정 전에 적용합니다. 모든 실제 평일 입력이 상한 아래였고, 기존에 완료한 운행도 모든 원천 이동의 가중치와 시간별 확률이 상한 적용 전후 완전히 같음을 대조했습니다. 별도 테스트에서는 40,000건이 제안된 경우를 만들어 30,000건 이내로 축소하고, 출발지·목적지·피크 시간대를 보존하는지 확인했습니다.','',
        '## 실행과 근거','',
        '이 폴더에서 Python과 프로젝트의 NumPy 환경으로 실행합니다. 다음 명령은 일반 월요일의 기본 배차 결과를 조회하거나 아직 없는 조건을 계산합니다.','',
        '```powershell','python -B -X utf8 run.py --day 월 --service regular','```','',
        '차량당 44명은 사용자 확인값입니다. 2024~2026학년도 나라장터 입찰 과업지시서는 제3노선에 44인승 이상을 규정하고, 서울대 2026년 2학기 시간표는 해당 시간대에 10분 간격을 제시합니다. [사용자 정정](../field_observations_2026-11-24/daehak_capacity.json) · [과업지시서 원문](../priority_sources_2026-11-07/contracts/sources/붙임5_과업지시서.hwp) · [서울대 운행 시간표](https://psir.snu.ac.kr/event/download?filename=%2Fevent_attachment%2F20260827%2F202608271104300169.pdf)','',
        '하교확률의 시각별 형태와 하루 상한은 사용자 시나리오에 해당합니다. 수강편람 입력은 기존 V11에서 사용한 공개 수업별 수강인원·요일·종료시각 자료를 따릅니다. [수업 종료 입력](../scenario_comparison_2026-11-07/simulation_outputs/input_snapshot/course_endings_current.json) · [확률 코드](departure.py) · [상한 코드](population.py) · [실행 코드](run.py) · [월요일 원장](runs/regular-mon/attempt-01/result.json)',''])
    with (HERE/'요일별_정원44명_비교.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(output[0]));w.writeheader();w.writerows(output)
    (HERE/'README.md').write_text('\n'.join(lines),encoding='utf8')
    (HERE/'comparison.json').write_text(json.dumps(dict(model='R261124094834',daily_limit=DAILY_TRIP_LIMIT,
        weekdays=output,monday=compar,execution_sources=execution_sources,verified_final_cases=len(list((HERE/'runs').glob('*/attempt-*/result.json'))),
        verified_reference_cases=len(list((CONTROL/'runs').glob('*/attempt-*/result.json')))),
        ensure_ascii=False,indent=2),encoding='utf8')

if __name__=='__main__':
    summarize()
