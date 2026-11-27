"""Build source-backed assumptions and a full-stop review from verified results."""
from pathlib import Path
import html,json,math
from prepare_walk_choices import ROOT,read
from selected_walk_choice import selected_work

def render_md(text):
    import re
    def inline(line):
        return re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'<a href="\2">\1</a>',html.escape(line))
    output=[];table=[]
    def flush():
        if not table:return
        head,*rows=table
        output.append('<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+inline(c)+'</th>' for c in head)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+inline(c)+'</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table></div>');table.clear()
    for line in text.splitlines():
        if line.startswith('|'):
            if not re.fullmatch(r'[| :\-]+',line):table.append([c.strip() for c in line.strip('|').split('|')])
            continue
        flush()
        if line.startswith('# '):output.append('<h2>'+inline(line[2:])+'</h2>')
        elif line.startswith('## '):output.append('<h3>'+inline(line[3:])+'</h3>')
        elif line.strip():output.append('<p>'+inline(line)+'</p>')
    flush();return ''.join(output)

def build():
    WORK=selected_work()
    v=read(WORK/'independent_verification.json');assert v['status']=='PASS' and v['simulation_runs']==10
    mon=next(c for c in v['run_summaries'] if c['weekday']=='mon' and c['scenario']=='peak')
    def f(n):return f'{n:.2f}'
    table='\n'.join(f"| {t['name']} {t['ars']} | {f(t['before_max_queue'])} | {f(t['after_max_queue'])} |" for t in mon['targets'].values())
    labels={'admin_snu_1653':'16:53 행정관 셔틀','culture_1655':'16:55 문화관입구 21297','snu_gate_1703':'17:03 서울대학교 21128'}
    def count(r):
        a,b=r['people_interval'];return str(a) if a==b else f'{a}~{b}'
    fits='\n'.join(f"| {labels[r['after']['id']]} | {count(r['after'])} | {f(r['after']['uniform_minute_mean'])} | {f(r['after']['temporal_min_max'][0])}~{f(r['after']['temporal_min_max'][1])} |" for r in v['all_stop_quality']['field_fit'])
    refit=read(WORK/'prepared.json.gz').get('initial_gate_refit')
    refit_note=''
    if refit:
        refit_note=f"초기 정문 도보 접근의 기존 선택 계수는 {refit['previous_alpha']:.2f}에서 {refit['alpha']:.2f}로 소폭 재적합했습니다. 같은 3건의 분내 시각 미상 관측으로 선택한 보정이며 독립 검증이 아닙니다. 이 계수가 전체 학생의 {refit['alpha']*100:.0f}%라는 뜻은 아닙니다. 동일한 이동 일부의 최초 경로를 기존 경로로 돌렸으며 총수요·목적지·출발시각·배차·정원·속도를 유지했습니다. 줄에 도착한 뒤의 재판단에는 아래의 새 거리 선호를 사용합니다."
    daylabels={'mon':'월','tue':'화','wed':'수','thu':'목','fri':'금'}
    comparisons=[]
    for row in v['run_summaries']:
        if row['scenario']!='peak':continue
        m=row['paired_metrics'];cell=lambda k:f"{m[k]['before']:.2f} → {m[k]['after']:.2f}"
        comparisons.append(f"| {daylabels[row['weekday']]} | {cell('wait_seconds')} | {cell('walking_seconds')} | {cell('total_seconds')} | {cell('route_changes')} |")
    comparison_table='\n'.join(comparisons)
    md=f'''# 혼잡에 따른 확률적 경로 변경 · v9

수강 기반 가중 이동을 보존하고, 긴 줄에서 다른 노선·교내 셔틀·직접 도보를 다시 고려하는 행동 규칙을 바꿨습니다. 월~금 × 기준/피크 배차 10개 경우를 모두 재계산했습니다.

## 원인과 수정

이전 하교 방향 법대·사회대입구 21298과 서울대정문 21299에서는 5516에서 내려 5511로 환승하는 흐름이 많았습니다. 앞 정류장에서 이미 모형 정원이 찬 5511을 여러 대 보내면서 줄이 쌓였고, 인근 정류장 도보 대안의 누락과 고정 경로 변경 한도가 긴 대기를 키웠습니다. 실제 학생들이 이렇게 오래 기다렸다는 관측 결과는 아닙니다.

새 모형은 인근 시내·교내 순환·역순환·통학 셔틀과 직접 도보를 비교합니다. 같은 목적지로 바로 연결되는 호환 노선은 같은 물리적 승차지에서 함께 고려합니다. 이동 후 정류장에서도 모형의 공유 정원과 FIFO 대기를 계산합니다.

{refit_note}

줄이 짧고 대기도 짧으면 당초 계획을 유지합니다. 줄이 참고정원의 60% 이상(최소 12명 상당), 대기 5분 이상, 본인의 만차 경험 또는 해당 정류소의 혼잡 선호 조건이 재판단을 활성화합니다. 계수는 잠정 행동 시나리오입니다.

## 변경 횟수에는 상한이 없습니다

0회·1회가 흔하고 두 번째부터는 급격하게 드물어지도록, 이전 변경 횟수가 n이면 평상시 기본 변경 성향에 0.30^n을 곱합니다. 1번째/2번째/3번째/4번째의 상대 기본 가중치는 100/30/9/2.7이고 이후도 양수입니다. 횟수 예산·소진·마지막 변경을 도보로 제한하는 규칙은 없습니다.

반복 만차, 길어진 대기와 혼잡 불편은 별도의 재판단 성향을 높입니다. 평균 1회는 참고 목표이며, 불필요한 이동을 시켜 평균을 맞추지 않습니다. 실제 횟수는 계산 결과입니다. 같은 자리에서 호환 노선을 고르는 것은 실제 도보 경로 변경과 구분합니다.

같은 노선의 뒤 정류장으로 걷는 선택은 완전히 제외하지 않고 낮은 8% 고려 가중치를 줍니다. 여러 노선·후보가 있다는 이유로 확률이 중복 증폭되지 않게 한 번의 행동 단위로 적용합니다. 방금 떠난 줄로 되돌아가는 선택도 5%의 낮은 고려도를 갖되 완전히 차단하지 않습니다. 시간에 따라 실제 여석·줄이 달라집니다.

## 보행 경로의 거리

거리만 본 평상시 상대 도보 고려도는 0~500m에서 동일합니다. 500~1,000m에서는 1에서 0.3으로 선형 감소하고, 1km를 넘으면 0.3 × exp(-(거리-1000)/150)로 빠르게 감소합니다. 800m 약58%, 1km 30%, 1.2km 약7.9%, 1.5km 약1.1%입니다. 500m 이내를 100으로 놓은 고려도이며 실제 학생 도보 분담률이 아닙니다.

직선거리 대신 보존한 OpenStreetMap 보행망 경로를 씁니다. 개인별 기존 보행 시간 배율과 경사·계단 비용은 ETA에 유지했습니다. 후보 생성은 인근 기본 6개 정류소와 노선 다양성 후보, 보행 경로 1.5km까지를 기본으로 합니다. 직접 목적지 도보는 더 긴 거리도 낮은 기본 고려도를 갖습니다. 만차·장기 대기 때는 일반적인 장거리 도보 거부감도 완화할 수 있습니다. 이 수치는 사용자의 거리 가설을 구현한 시나리오이며 독립 설문에서 추정한 비율이 아닙니다.

## 모든 정류장의 20분 검사

20분은 이상 사례를 찾는 검토 기준입니다. 대기시간을 20분으로 잘라내거나 그 시각에 무조건 사람을 없애지 않습니다. 같은 정류소에서 노선 선택이 달라져도 연속 대기가 초기화되지 않도록 인접 대기 구간을 합쳤습니다. 준비시간 20초도 포함합니다. END의 지도 표시용 1초는 제거했고 미완료·검열은 별도로 봅니다.

기존 v7 peak에서는 표시 시간대와 겹치는 20분 초과 대기사건량이 월2784.80/화2751.20/수2708.11/목2172.87/금132.77명 상당·회였습니다. 같은 이동이 여러 정류장에서 길게 기다리면 여러 번 세며 실제 고유 학생 수가 아닙니다.

새 후보는 모든 요일·정류장과 두 배차 시나리오의 개별 연속대기, 승하차 수지·정원·FIFO·질량·차량 위치/시간 연결을 독립 재검산했습니다. 상세 결과는 아래 검토표와 CSV에서 확인할 수 있습니다.

## 출발 후 전체 경로의 기다림과 총시간

피크 시나리오에서 전후 공통으로 완료된 동일 원래 가중 이동 집단의 평균입니다. 대기는 여러 정류소를 합친 누적 대기, 총시간은 모형 출발부터 목적지까지이며 수업 종료 후 출발 전 지체는 제외합니다. 출발시각이 같으므로 전후 차이는 그 지체를 새로 빼서 만든 효과가 아닙니다. 단위는 분, 변경은 회입니다. 줄에서 이탈한 경우도 포함합니다. 대기 감소와 추가 도보의 교환을 함께 봐야 합니다.

| 요일 | 누적 대기 이전→새모형 | 도보 이전→새모형 | 총시간 이전→새모형 | 변경 횟수 이전→새모형 |
|---|---:|---:|---:|---:|
{comparison_table}

## 약 40명 참고 기준

서울대정문 21269/21299와 법대·사회대입구 21270/21298의 약40명은 사용자 기억에서 나온 참고값이며 현장 실측 상한이 아닙니다. 개인별 혼잡 거부감을 시나리오에 반영하고 결과의 최대 줄을 검사했습니다. 인원을 잘라내지 않았습니다. 서울대학교 21128은 별도 정류소이며 이 참고 상한을 적용하지 않습니다.

월요일 피크의 최대 대기열(명 상당):

| 정류소 | 이전 v7 | v9 |
|---|---:|---:|
{table}

## 기존 현장 관측과 비교

사용자가 보고한 월요일 관측 3건입니다. 초가 미상이므로 해당 분 안의 균등 시각으로 비교하고 33~39명은 구간으로 유지했습니다. 분 평균은 관측 순간의 인원과 다른 통계입니다.

| 관측 | 보고 인원 | 모형 분 평균 | 분내 변화 범위 |
|---|---|---:|---:|
{fits}

세 관측의 기대 절대 구간 오차 합은 이전 {f(v['field_fit_selection_rule']['sum_expected_absolute_interval_error_before'])}, 새 모형 {f(v['field_fit_selection_rule']['sum_expected_absolute_interval_error_after'])}명 상당으로 사실상 비슷합니다. 사례별로 좋아진 곳과 나빠진 곳이 있습니다. 같은 자료로 후보를 검토·선택했으므로 독립 예측 정확도 검증이 아닙니다. 선택 후 다른 날짜의 대기시간·승차량 관측으로 검증해야 합니다.

## 자료와 유지한 조건

- 기존 보존 수강·수업 종료 기반 가중 이동, 건물 출발지·목적지 참고비중·기숙사 참고비율·출발시각을 유지했습니다. 가중 이동 사건량은 고유 학생 수가 아닙니다.
- 공식 노선·정류소 순서와 보존 운행계획, 공유 정원(통학60/역순환25, 시내50/마을24 참고), 기존 교내40/교외65 상한 및 저장 구간속도 조건을 유지했습니다. 현재 실차 GPS·차량별 등록정원·실제 출발표를 새로 관측한 것은 아닙니다.
- 사용자 관측: 행정관16:53 53명, 문화관16:55 5명, 서울대학교21128 17:03 33~39명. 정확한 초·노선별 의도는 미상입니다.
- 사용자 행동 가설: 긴 줄에서 다른 노선·교내 셔틀·도보를 재검토, 횟수 제한 없음/두 번째부터 급감, 반복 만차·긴 대기일수록 확률 상승, 0~500m 유사/1km 이후 급감, 두 장소 약40명 참고, 20분 초과 검토.
- 교외에서 타고 들어오는 배경 승객과 실제 전체 수요, 개인 선호는 여전히 미확인입니다. 현장 대기시간 실측으로 이번 감소를 검증한 것은 아닙니다.
- 공식 시간표 참고는 [학내외 버스 정류장·시간](https://www.snu.ac.kr/about/gwanak/shuttles/shuttle_stops)과 [교내순환 셔틀 안내](https://www.snu.ac.kr/about/gwanak/shuttles/campus_shuttles)를 우선합니다. 학기·계절학기·방학과 적용 기간을 섞지 않습니다. 이번 비교는 기존 v7의 기준/피크 운행계획을 고정했으며 실제 회차별 출발표를 새로 실측한 것은 아닙니다.
- 새로 확보한 서울시 월별 시간대 승하차 합계와 일별 승하차 합계는 별도의 단위입니다. 합쳐서 날짜×시간별 실측이나 개인 대기시간으로 만들지 않았으며 이번 행동 비교의 수요에 새로 합산하지 않았습니다.

기존 v3~v8, 폐기한 후보와 원본 과학 자료는 보존했습니다. 수요 삭제·정원 증대·배차/속도 변경으로 줄을 줄이지 않았습니다. [기존 전체 자료·출처](methodology.html) · [이전 v7](./?dataset=gate_access_v1) · [현재 지도](./)
'''
    public=ROOT/'public';(public/'walk-choice-methodology.md').write_text(md,encoding='utf8')
    # A read-only companion to the existing app: it neither changes parameters
    # nor starts simulations, and uses only the verified aggregate export.
    page='''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>경로 변경 가정·전 정류장 대기검사</title><link rel="stylesheet" href="methodology.css"><link rel="stylesheet" href="campus-theme.css"><script defer src="campus-theme.js"></script><style>.review-main{max-width:1100px;margin:auto;padding:30px 20px 60px}.review-main h1{line-height:1.5}.review-main p{line-height:1.9}.review-main label{display:inline-grid;gap:7px;margin:12px 16px 12px 0}.review-main select,.review-main input{max-width:100%;padding:8px;border:1px solid var(--campus-line);background:var(--campus-field);color:inherit;border-radius:8px}.review-table{overflow:auto;max-height:520px}.review-table table{width:100%;font-size:12px;border-collapse:collapse;white-space:nowrap}.review-table td,.review-table th{padding:9px;border-bottom:1px solid var(--campus-line)}.review-table th{position:sticky;top:0;background:var(--campus-surface)}.curve-wrap{max-width:700px}.curve-wrap svg{width:100%;height:auto;color:var(--campus-accent)}#distance{width:min(500px,85vw)}.sources{white-space:pre-wrap;line-height:1.8;overflow-wrap:anywhere}</style></head><body><header class="doc-header"><a class="doc-brand" href="./">하교길 실험실</a><nav><a href="./">지도</a><a href="walk-choice-methodology.md">MD 원문</a></nav></header><main class="review-main"><h1>혼잡에 따른 경로 변경과 대기 검사</h1><p>변경 횟수에는 상한이 없습니다. 두 번째부터 기본 성향이 급격하게 낮아지고, 만차·대기·혼잡은 재판단 가능성을 높입니다. 모든 수치는 가중 모형 결과이며 실제 학생 이동·대기시간의 관측값이 아닙니다.</p><h2>0~500m는 같은 기본 도보 고려도</h2><p>거리만 본 평상시의 상대 고려도입니다. 실제로 걷는 비율은 줄·버스 여석·총시간·이전 변경 이력에도 달려 있습니다.</p><div class="curve-wrap"><svg id="walking-curve" viewBox="0 0 660 260" role="img" aria-label="500미터까지 일정하고 1킬로미터 이후 급감하는 상대 도보 고려도"></svg></div><label for="distance">보행 경로 거리<input id="distance" type="range" min="0" max="2000" step="5" value="500"></label><p id="distance-value" aria-live="polite"></p><h2>모든 요일·정류장 연속대기</h2><p>같은 정류장의 연속 대기를 합치고, 줄에서 걸어 나간 경우도 포함합니다. 평균과 90백분위는 이 표의 전체 대기 결과 기준입니다. 지도 그래프의 ‘탑승 완료자 평균’과 분모가 다릅니다. 20분은 검토 기준이며 강제 시간 제한이 아닙니다.</p><label>요일<select id="review-day"><option value="mon">월요일</option><option value="tue">화요일</option><option value="wed">수요일</option><option value="thu">목요일</option><option value="fri">금요일</option></select></label><label>배차<select id="review-scenario"><option value="peak">피크 최소 간격</option><option value="regular">기준 배차</option></select></label><label>정류장 검색<input id="review-search" type="search" placeholder="정류소 이름 또는 ARS"></label><p id="change-summary"></p><p id="review-status" role="status">검증 자료를 불러오고 있습니다.</p><div class="review-table"><table><thead><tr><th>정류소·ARS</th><th>평균(분)</th><th>90백분위(분)</th><th>최대(분)</th><th>이전 최대(분)</th><th>20분 초과(명 상당·회)</th><th>최대 줄(명 상당)</th></tr></thead><tbody id="review-body"></tbody></table></div><p><a href="walk-choice-waits.csv" download>전체 990개 정류장·요일·배차 집계 CSV</a> · <a href="walk-choice-methodology.md">가정·출처 MD</a> · <a href="./?dataset=gate_access_v1">이전 v7 지도</a></p><details><summary>가정·자료·한계 전체 설명 펼치기</summary><div class="sources">'''+render_md(md)+'''</div></details></main><script type="module" src="walk-choice-review.js"></script></body></html>'''
    (public/'walk-choice-methodology.html').write_text(page,encoding='utf8')
    print('Built verified assumptions, walking curve and full-stop review page')

if __name__=='__main__':build()
