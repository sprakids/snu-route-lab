"""Publish only aggregate candidate replay files and an honest fit explanation."""
from pathlib import Path
from collections import Counter
import csv, html, json, math, shutil
import gate_access_calibration as trial


def main():
    selected=trial.read(trial.WORK/'selected_candidate.json');assert selected['status']=='PASS'
    work=trial.WORK/selected['directory'];verified=trial.read(work/'independent_verification.json')
    assert verified['status']=='PASS' and verified['simulation_runs']==10
    public=trial.ROOT/'public';out=public/'data/capacity_v7';out.mkdir(exist_ok=True)
    for name in ['common','charts',*[f'{s}-{d}' for s in ('regular','peak') for d in ('mon','tue','wed','thu','fri')]]:
        for suffix in ('.json','.json.gz'):shutil.copy2(work/'public_data'/f'{name}{suffix}',out/f'{name}{suffix}')
    for suffix in ('.json','.json.gz'):
        shutil.copy2(work/'public_data'/f'half_hour{suffix}',public/'data/half_hour_v1'/f'capacity_v7{suffix}')
    screen=trial.read(trial.WORK/'screening_results.json')
    candidate=next(r for r in screen['candidates'] if r['alpha']==selected['alpha'])
    prep=trial.read(work/'preparation_verification.json')
    with (work/'reallocated_particles.csv').open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
    upper=math.fsum(float(r['weight']) for r in rows if r['building'] in ('301','302'))
    buildings=Counter()
    for r in rows:
        if r['weekday']=='월':buildings[r['building']]+=float(r['weight'])
    labels={'admin_snu_1653':'16:53 행정관 셔틀','culture_1655':'16:55 문화관입구','snu_gate_1703':'17:03 서울대학교 21128'}
    fits=[]
    for before,after in zip(screen['baseline_fit'],candidate['observation_fit']):
        assert before['id']==after['id']
        fits.append({'label':labels[before['id']],'reported_people_interval':before['people_interval'],
                     'before_minute_mean':before['uniform_minute_mean'],'after_minute_mean':after['uniform_minute_mean'],
                     'before_minute_range':before['temporal_min_max'],'after_minute_range':after['temporal_min_max'],
                     'before_expected_absolute_interval_error':before['expected_absolute_distance_to_report_interval'],
                     'after_expected_absolute_interval_error':after['expected_absolute_distance_to_report_interval']})
    summary={'model_id':selected['model_id'],'algorithm_id':selected['algorithm_id'],'dataset':'capacity_v7',
             'alpha':selected['alpha'],'max_gate_walk_seconds':trial.CUTOFF,
             'observations_used_for_selection':3,'observation_time_model':'uniform within reported minute',
             'independent_empirical_validation':False,'queue_fit_is_waiting_time_validation':False,
             'weekday_results_other_than_monday_are_extrapolations':True,
             'fit_comparison_scenario':'peak','fits':fits,
             'reallocated_weight_by_day':prep['rerouted_weight_by_day'],
             'original_total_weight_by_day':prep['total_weight_by_day'],
             'engineering_301_302_initial_reallocation_weight':upper,
             'maximum_particle_mass_error':verified['maximum_particle_mass_error'],
             'simulation_runs':10,'original_hashes_unchanged':verified['original_hashes_unchanged'],
             'default_dataset':'capacity_v5','default_routing_release':'261109152540'}
    trial.save(public/'gate-access-summary.json',summary)
    fitlines=[]
    for r in fits:
        lo,hi=r['reported_people_interval'];count=str(lo) if lo==hi else f'{lo}~{hi}'
        spread='~'.join(f'{v:.1f}' for v in r['after_minute_range'])
        fitlines.append(f"| {r['label']} | {count} | {r['before_minute_mean']:.1f} | {r['after_minute_mean']:.1f} | {spread} |")
    daylines=[]
    for day in ('월','화','수','목','금'):
        moved=prep['rerouted_weight_by_day'][day];total=prep['total_weight_by_day'][day]
        daylines.append(f'| {day} | {total:.1f} | {moved:.1f} | {moved/total*100:.2f}% |')
    md=f'''# 정문 도보 접근 보정 후보 {selected['model_id']}

사용자가 보고한 2026-11-09 월요일 대기인원 3건을 참고해 초기 경로 선택을 바꾼 후보입니다. 실제 이동 경로를 확인한 결과나 독립 정확도 검증은 아닙니다.

## 무엇을 바꿨나

서울대입구역으로 향하는 기존 가중 이동 중 정문까지 도보 15분 이내인 경우, 가까울수록 처음부터 서울대학교 정류장 21128로 걸어가 5개 노선 중 먼저 탈 수 있는 차량을 이용하도록 일부 초기 경로를 재배분했습니다. 경로 변경 후에도 같은 차량의 공유 정원과 대기열을 계산합니다.

선택 확률은 `0.75 × max(0, 1 − 개인별 정문 보행시간 / 900초)`입니다. 0.75는 모든 학생의 75%라는 뜻이 아닙니다. 최대 15분 접근 범위와 이 거리별 선호 형태는 잠정 설정입니다. 0.25·0.50·0.75 세 후보를 같은 난수로 비교해 세 관측의 분내 기대 절대 구간 오차가 가장 작은 조건을 골랐습니다. 나머지 출발지·목적지, 출발 시각, 수강 기반 총량, 보행망, 개인 보행배율, 정원·배차·속도는 유지했습니다.

## 실측을 어떻게 비교했나

관측은 00초가 아니라 해당 분 안의 임의 시각입니다. 모델의 모든 대기량 변화 구간을 지속시간으로 가중했습니다. 분 평균과 별개로 임의 시각의 대기량이 보고된 인원 구간에서 벗어나는 절대 거리도 평균했습니다. 가장 잘 맞는 초를 사후 선택하지 않았고 33~39명을 36명으로 바꾸지 않았습니다.

| 관측 | 보고 인원 | 기존 분 평균 | 후보 분 평균 | 후보 분내 변화 |
| --- | ---: | ---: | ---: | ---: |
{chr(10).join(fitlines)}

표의 모델 값은 사람을 직접 센 값이 아니라 가중 이동량 상당입니다. 범위는 한 분 동안의 시간 변화이며 신뢰구간이 아닙니다. 같은 3건을 후보 선택에 사용했으므로 이 표를 독립 정확도 검증으로 부를 수 없습니다. 월요일 이외 결과는 같은 선택 규칙을 적용한 외삽입니다. 실제 대기시간·승차확률 개선도 아직 검증하지 않았습니다.

## 총수요에서 얼마나 옮겼나

| 요일 | 기존 전체 가중 이동량 | 초기 정문 경로 재배분 | 전체 대비 |
| --- | ---: | ---: | ---: |
{chr(10).join(daylines)}

수요를 새로 더하지 않았습니다. 301·302동의 초기 경로를 직접 재배분한 양은 {upper:.1f}입니다. 다른 승객의 경로 변경이 차량 혼잡·후속 대기에 미치는 영향은 함께 계산됩니다. 숫자는 고유 학생 수나 실제 이용자 수가 아닙니다.

## 확인한 것과 남은 것

평일 5일 × 배차 2개를 계산하고 전체 입자 질량, FIFO, 승하차·정원, 차량 이동, 30분 집계와 대기열을 별도 검산했습니다. 기존 v5·v6 자료와 운영 경로 추천의 기본 대기모델은 보존했습니다. 기본 화면은 한국 시간 기준 현재 요일·시각으로 시작하며 링크의 지정값과 사용자의 선택을 우선합니다. 재생 범위 밖 또는 주말에는 참고 표시임을 알립니다.

교외 배경 재차 인원, 차량별 실제 정원·실차 배차, 방문객 등 수강편람 밖 수요, 실제 노선 선호는 여전히 불확실합니다. 새로운 날짜의 독립 관측이 필요합니다. 같은 날 인접 시점 3건만으로 실제 행동 비중을 확정하지 않았습니다.

## 자료와 출처

- 실측: 사용자가 이 프로젝트 대화에 보고한 행정관 53명·문화관 5명·서울대학교 33~39명. 서울대학교는 21128 방향을 확인했으며 문화관은 문화관입구 21297로 대응한 해석입니다. 개별 노선 의도·정확한 초·승차 진행 상태는 미확인입니다.
- 수요·경로 원본: 기존 v5 수강편람 기반 가중 이동과 보존된 보행망. [기존 가정·자료 설명](methodology.html)을 함께 확인해 주세요.
- 보행망: 기존에 보존한 OpenStreetMap 보행망의 큰 연결 성분과 110m 연결 제한을 유지했습니다. [OpenStreetMap 출처](https://www.openstreetmap.org/copyright).
- [기계 판독용 집계·비교 결과](gate-access-summary.json). 원본 보존 해시와 상세 경로 재배분·계산 로그는 프로젝트의 비공개 분석 폴더에 보관했습니다.

[보정 후보 지도](./?dataset=gate_access_v1) · [기존 v5 지도](./) · [관측 도로속도 참고판](./?dataset=empirical_speed_v1)
'''
    (public/'gate-access-methodology.md').write_text(md,encoding='utf-8')
    # Small, predictable Markdown subset; retain local navigation and full text.
    import re
    def inline(text):
        escaped=html.escape(text)
        escaped=re.sub(r'`([^`]+)`',r'<code>\1</code>',escaped)
        return re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'<a href="\2">\1</a>',escaped)
    chunks=[];table=[]
    def flush():
        if not table:return
        head,*body=table
        chunks.append('<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+inline(x)+'</th>' for x in head)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+inline(x)+'</td>' for x in row)+'</tr>' for row in body)+'</tbody></table></div>');table.clear()
    for line in md.splitlines():
        if line.startswith('|'):
            if not re.fullmatch(r'[| :\-]+',line):table.append([x.strip() for x in line.strip('|').split('|')])
            continue
        flush()
        if line.startswith('# '):chunks.append('<h1>'+inline(line[2:])+'</h1>')
        elif line.startswith('## '):chunks.append('<h2>'+inline(line[3:])+'</h2>')
        elif line.startswith('- '):chunks.append('<p>• '+inline(line[2:])+'</p>')
        elif line.strip():chunks.append('<p>'+inline(line)+'</p>')
    flush()
    page='<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>정문 도보 보정 후보 · 가정과 실측 비교</title><link rel="stylesheet" href="methodology.css"><link rel="stylesheet" href="campus-theme.css"><script defer src="campus-theme.js"></script><body><a class="skip-link" href="#content">본문으로</a><header class="doc-header"><a class="doc-brand" href="./?dataset=gate_access_v1">하교길 실험실</a><nav><a href="./">기존 지도</a><a href="gate-access-methodology.md">MD 원문</a></nav></header><main class="doc-layout" style="display:block;max-width:1000px"><article id="content">'+''.join(chunks)+'</article></main></body></html>'
    (public/'gate-access-methodology.html').write_text(page,encoding='utf-8')
    trial.save(trial.WORK/'export_verification.json',{'status':'PASS','model_id':selected['model_id'],'public_dataset':'capacity_v7',
               'aggregate_only':True,'dataset_files':13,'private_reallocation_rows_published':False,'default_model_promoted':False})
    (trial.WORK/'README.md').write_text(md.replace('(methodology.html)','(../public/methodology.html)').replace('(gate-access-summary.json)','(../public/gate-access-summary.json)'),encoding='utf-8')
    print(json.dumps({'status':'PASS','model_id':selected['model_id'],'dataset':'capacity_v7','fits':fits},ensure_ascii=False))


if __name__=='__main__':main()
