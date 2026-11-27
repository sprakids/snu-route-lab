"""Create the reviewed readable calculation record and fixed chart payloads."""
from pathlib import Path
from datetime import datetime,timezone
import csv,json,math,hashlib
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'outputs_v2'
VIZ=Path('C:/Users/김예준/.codex/visualizations/2026/10/21/01a15f4b-516c-79b1-9b9a-c31680e1acd7')
assert json.loads((OUT/'verification.json').read_text(encoding='utf-8'))['status']=='PASS'
assert json.loads((OUT/'independent_verification.json').read_text(encoding='utf-8'))['status']=='PASS'
with (OUT/'waiting_hourly.csv').open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
specs=json.loads((OUT/'model_specs.json').read_text(encoding='utf-8'));nodes=specs['nodes'];days='월화수목금'
lookup={(r['config'],r['node'],r['weekday'],int(r['hour'])):r for r in rows}
def val(r,k):return None if r[k]=='' else float(r[k])
def fmt(x):return '—' if x is None else f'{x:.1f}'
def table(node,config='base60'):
 lines=['| 정류소 도착시간대 | 월 | 화 | 수 | 목 | 금 |','|---|---:|---:|---:|---:|---:|']
 for h in range(11,24):
  rr=[lookup[(config,node,d,h)] for d in days]
  lines.append('| '+rr[0]['arrival_window']+' | '+' | '.join(fmt(val(r,'mean_wait_min')) for r in rr)+' |')
 return '\n'.join(lines)
peaks=[]
for node in nodes:
 for day in days:
  eligible=[lookup[('base60',node,day,h)] for h in range(12,19) if val(lookup[('base60',node,day,h)],'mean_wait_min') is not None]
  if not eligible:continue
  r=max(eligible,key=lambda x:float(x['mean_wait_min']))
  peaks.append({k:r[k] for k in ['weekday','node','label','arrival_window','arrival_weight','mean_wait_min','p90_wait_min','mean_schedule_wait_min','mean_capacity_extra_min','phase_mean_min','phase_mean_max']})
with (OUT/'weekday_peak_summary.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(peaks[0]));w.writeheader();w.writerows(peaks)
def phase_table(node):
 lines=['| 요일 | 도착시간대 | 예상 도착 가중치 | 평균 대기 | 배차·준비 대기 | 정원 부족 추가 대기 | P90 |','|---|---|---:|---:|---:|---:|---:|']
 for r in peaks:
  if r['node']==node:lines.append('| '+' | '.join([r['weekday'],r['arrival_window'],fmt(float(r['arrival_weight'])),fmt(float(r['mean_wait_min'])),fmt(float(r['mean_schedule_wait_min'])),fmt(float(r['mean_capacity_extra_min'])),fmt(float(r['p90_wait_min']))])+' |')
 return '\n'.join(lines)
report=[
'할루시네이션 방지 O',
'# 요일·시간대별 셔틀 대기시간의 조건부 추산',
'작성일: 2026-11-07 KST. **실제 대기시간 예측 정확도를 검증한 결과가 아닙니다.** 앞서 계산한 수강인원 기반 평균 이동량에 운행계획과 정원을 붙인 시나리오입니다. 원래의 수강인원 가중치를 실제 학생 수나 현장 승객 수로 바꾸어 부르지 않습니다.',
'## 결과를 읽는 기준',
'- 시간대는 **수업 종료시각이 아니라 정류소 도착시각**입니다. 12:00–13:00은 그 시간대에 도착한 모형 통행의 평균 대기입니다.\n- 대기는 정류소 도착부터 승차까지이며 승차 준비20초를 포함합니다. 건물 이탈·정류소까지 도보·차내시간은 포함하지 않습니다.\n- 기준은 기숙사19.49%, 수업 직후 이동50%, 교외 방향은 과거 참고 비중55.7:27.2:17.0을99.9로 정규화한 시나리오입니다. 현재 학생의 실제 목적지·거주율은 아닙니다.\n- **대형 차량60명은 사용자 제안 가정**입니다. 소형 역순환은 공식 표의25인승을 정원25명으로 가정했습니다. 승차정원 등록증·실제 입석 가능 인원을 확인한 값은 아닙니다.\n- 행정관 입구역행은11~15시10분,15~19시4분(공식3~5분의 중간),19~20시15분,20~21시30분으로 계산합니다. 대학동행은11~19시10분, 양 노선 야간21:10~23:10은30분마다2대 동시 출발로 계산했습니다.\n- 순환은 낮6분(공식5~7분 중간),19~21시20분이며302동 마지막 출발21:00을 둡니다. 역순환은302동09:50~17:10의20분 간격을 사용했습니다.301동 통과시각은 기존 이동모형의 구간거리·속도 가정으로 산출했습니다.\n- 공개되지 않은 주간 출발 분 단위 시각은20개 위상으로 바꾸어 비교했습니다. 시간대별 평균은 이20개 경우를 같은 비중으로 합친 값이며, 실제 배차시각의 관측분포가 아닙니다.\n- 원래10회 이동 시뮬레이션의 **평균 유입량을 대기열에 넣은 결과**입니다.10회 각각의 대기를 계산해 평균한 결과나 신뢰구간으로 부르지 않습니다.',
'## 행정관 → 서울대입구역: 평균 대기시간(분)',table('admin_snu'),
'12~19시 중 요일별 평균 대기가 가장 큰 시간대의 분해입니다. P90은 모형에서 승차한 가중치의90%가 이 시간 이내 기다렸다는 의미이며, 신뢰구간이나 현장 관측 백분위가 아닙니다.',phase_table('admin_snu'),
'입구역행의 화요일14시대는 해당 시간의 새 도착량만으로 판단하지 않습니다. 앞선 시간대에 쌓인 대기열을 계속 이월하기 때문에, 도착량이 줄어도 평균 대기가 길게 남을 수 있습니다. 이는 FIFO 계산의 설명이며 실제 화요일 현장을 측정한 원인 분석은 아닙니다.',
'## 행정관 → 대학동: 평균 대기시간(분)',table('admin_daehak'),phase_table('admin_daehak'),
'## 윗공대 주요 승차지: 평균 대기시간(분)',
'**해석 제한이 특히 큽니다.** 순환차량이302동에 도착했을 때 기존 탑승객이 없다는 기준이며,302동에서 탄 모형 승객은301동까지 계속 타고 있다고 가정해 같은 차량의 잔여 정원을 공유합니다. 다른 교내 정류장·수업 외 이동·기존 탑승객 전체를 복원한 노선 전체 모형이 아닙니다. 순환302동의 가용정원을30명으로 낮춘 민감도도 별도 CSV에 있습니다. 여기서 순환 대기가 짧게 나왔다고 실제 윗공대가 덜 혼잡하다고 결론 내릴 수 없습니다.',
]
for node in ('circle_302','circle_301','reverse_302','reverse_301'):report+=['### '+nodes[node][2],table(node)]
report += [
'‘—’는 해당 구간의 모형 도착량이 없어서 대기 평균을 계산하지 않았다는 의미입니다. 실제 대기가0분이라는 뜻이 아닙니다. 역순환은17:10의302동 출발 종료 이후 미운행과도 구분해야 합니다. 일부 역순환 시간대의 이동 가중치는1명 상당보다도 작아, 그 시간 평균을 대표적인 학생 경험으로 해석하지 않습니다.',
'## 가정 변화에 대한 점검',
'별도 CSV에는 기준 외에 입구역행 오후3분/5분 배차, 대형44명, 순환302동의 가용정원30명, 즉시 이동25%/75%, 교외 세 방향 균등배분을 계산했습니다. 원래 경로 선택은 고정하고 정류소별 입력량·공급 조건만 바꿉니다.',
'**균등배분은 실제 대기 예측으로 사용하면 안 됩니다.** 대학동행 수요가 크게 늘어난 상태에서 경로 변경·줄 이탈을 막고 대기열을 계속 이월하면 수요일18시대 평균이 약234.5분까지 나옵니다. 이는 이 가정 조합에서 공급을 초과한 줄을19시 이후 야간버스까지 강제로 기다리게 한 결과입니다. 현실의 학생들이4시간 가까이 기다린다는 근거가 아닙니다. 이전 이동모형에 정원 제약이 없었다는 한계와 목적지·즉시 이동 비율에 대한 높은 민감성을 드러내는 진단으로 남깁니다.',
'## 계산 절차와 이유',
'1. 이전 conditional_mean_bins.csv의 목적지별·요일별·노선별·정류소별5분 가중치에 기존 시나리오 확률을 적용합니다. 입구역행과 대학동행, 순환과 역순환을 하나의 줄로 합치지 않기 위해 노선까지 구분합니다.\n2. 원래 저장된 historical_reference 및 equal_reference의 같은 셀과 대조해 입력을 정확히 복원했는지 확인합니다.\n3.5분 구간 안에서는 균등하게 도착한다고 놓고5초 간격으로 분배합니다. 원자료보다 세밀한 도착 시각을 관측한 것이 아니라 구간 내부를 재구성하는 가정입니다.\n4. 승차 준비20초 후부터 이용 가능한 버스를 찾고, 먼저 도착한 가중치부터 정원만큼 승차시킵니다. 못 탄 가중치는 다음 차량으로 넘깁니다.\n5.302동에서 탄 인원을 같은301동 통과 차량의 정원에서 차감합니다.302동 이전 배경 탑승객과301동 하차는 미확인입니다.\n6. 시간 평균은 승차 가중치로 계산합니다. 승차 실패 후 다음 차량을 기다리는 시간도 포함하고, 평균·P90·정원 부족으로 인한 추가 대기를 분리합니다.\n7. 막차 이후 미탑승 가중치는 별도로 보존하며0분 대기로 넣지 않습니다. 앞선 시간대의 모형 대기열을 이어받기 위해11:20 이전 모형 유입도 계산에 넣되 보고 구간은11:20~23:10으로 제한합니다.',
'## 남는 한계',
'- 수강인원 합에는 동일 학생의 여러 수업이 포함되며 실제 출석·그날의 마지막 수업·귀가 시각이 없습니다.\n- 실제 목적지 비율·귀가율·현장 유입량으로 보정되지 않았습니다. 이 자료만으로 내일의 실제 대기시간을 확정할 수 없습니다.\n- 교통정체·차량 몰림·결행·탑승 처리 지연·출입문 혼잡·실제 정원과 기존 탑승객을 관측하지 않았습니다.\n- 정원 부족 이후의 경로 재선택·줄 이탈·다음 수단으로의 전환이 없습니다. 환승 정류소 도착량도 이전 결과의 시각을 고정하므로, 앞선 승차 지연이 다음 환승에 전파되는 현상을 반영하지 않습니다.\n- 수업 외 이동·연구실 퇴실·도서관 이용·비수강생 등 배경 수요가 없습니다. 해당 누락과 과도한 통행 생성은 서로 다른 방향의 오차를 만들 수 있으므로 결과를 엄밀한 하한·상한으로 부르지 않습니다.\n- 9~10월 한시 증차·시험기간 야간 추가차량을 일반11월 평일에 연장하지 않았습니다. 일반학기 평일의 조건부 계산이며 특정 날짜의 현장 예측이 아닙니다.',
'## 근거와 재현',
'- [학교 공식2026-2 운행 안내](https://cse.snu.ac.kr/ko/community/notice/25464): 적용기간과 정규·한시·야간·역순환 계획.2026-11-07에 웹 공지를 다시 확인했습니다.\n- 기존 모형·강좌·보행·노선 자료: course_demand_2026-11-06 및 scenario_comparison_2026-11-07의 보존 원본. 정확한 해시는 outputs_v2/source_manifest.json.\n- 계산 코드: estimate_wait.py. 주 결과: outputs_v2/waiting_hourly.csv, waiting_5min.csv, waiting_daily.csv.\n- 조건: outputs_v2/model_specs.json. 검산: verification.json, independent_verification.json, independent_terminal_check.csv.\n-30초 분배의 초기 결과는 일부 대기의 차이가0.39분으로 검산 기준0.25분을 넘었습니다. 삭제하지 않고 outputs/에 실패 표시와 함께 남겼으며, 최종은5초 분배 outputs_v2입니다.1초 분배와 비교한 표본 최대 차이는0.105분입니다.\n- 독립 검산은 모든 요일의 두 행정관 줄에서 위상3의115개 시간 셀을 승객 우선 배정 방식으로 다시 계산해 가중 대기시간 합의 차이0을 확인했습니다.302→301 정원 공유·막차 이후 미탑승 보존의 수작업 기대값도 대조했습니다. 이것은 코드·계산 검증이며 현장 예측 정확도 검증이 아닙니다.',
]
(ROOT/'요일시간별_셔틀대기_조건부추산.md').write_text('\n\n'.join(report)+'\n',encoding='utf-8')
factors='''할루시네이션 방지 O

# 이전 하교 이동경로 분석에서 고려한 요소

1. 평일 수업 요일·종료시각: 이동 발생의 출발 시점을 정했습니다.
2. 실제 강의실 건물·강좌 수강인원: 개설 학과 대신 강의동에서 출발하며, 인원은 통행 사건의 가중치로 썼습니다. 고유 학생 수가 아닙니다.
3. 수업 직후 거주방향 이동 비율: 기준50%,25%·75% 민감도입니다. 개인의 마지막 수업·실제 귀가 여부는 모릅니다.
4. 거주·목적지 가정: 기숙사19.49%, 기숙사 대표점919동/900동, 교외 입구역·낙성대·대학동 대표점. 균등·과거 방향 비중·목적지 변화 시나리오이며 실제 응답 결과는 아닙니다.
5. 건물 이탈시간: 삼각분포1·3·8분을 가정했습니다. 실내 이동·출입구별 실측값은 없습니다.
6. 정류소까지·환승·최종 목적지까지의 보행: OSM 통로·계단·거리, 보행속도0.9·1.2·1.5m/s, 계단 기본0.7m/s를 사용했습니다. 건물 대표점과 연결부·실제 경사·야간 통행 가능성은 현장 미검증입니다.
7. 수단과 교통망: 도보, 시내버스5511·5513·5516·관악02-1·관악02-2, 행정관·대학동·순환·역순환 셔틀을 비교했습니다. 승하차 가능 지점·방향·정차 순서와 최대1회 환승을 고려했습니다.
8. 운행 시간과 배차: 셔틀 정규 시간표·역순환/야간 정시 출발을 사용하고, 시내버스는 저장된 대표 간격과 미관측 출발 위상 가정을 사용했습니다. 실제 당일 GPS·도착예정으로 계산한 경로는 아닙니다.
9. 차내 이동과 승차 준비: 차내 이동시속18km, 정류장당15초, 승차 준비20초를 가정했습니다.
10. 경로 선택과 취향 차이: 예상 총 이동시간에 환승1회당2분의 선택 부담과 Gumbel(scale90초)의 임의 선호 차이를 적용했습니다. 새 계획서의 시간·혼잡·도보·환승에 대한 사용자별 가중치를 실제 입력한 분석은 아닙니다.
11.10회 반복과5분 집계: 강좌·목적지당12개 가중 입자를 사용해 계산 안정성을 살폈고, 첫 승차와 환승 정류소 도착을5분 단위로 집계했습니다. 환승은 추가 승차 사건이며 새로운 학생이 아닙니다.

**이전 분석에 없었던 요소:** 실제 차량 정원·기존 탑승객·만차로 인한 다음 차 대기·실제 줄 길이·착석 확률·정체에 따른 당일 운행 지연·정원 제약에 따른 경로 재선택입니다. 이번 후속 계산은 여기에 사용자 제안 대형60명 가정과 일부 주요 승차지의 FIFO 대기열을 추가한 조건부 분석입니다.

근거: course_demand_2026-11-06/시뮬레이션_결과와_가정.md, simulate_stop_inflow.py, scenario_comparison_2026-11-07/scenario_specs.json, simulation_outputs/FILE_LAYOUT.md. 변경된 프로젝트 계획의 구현 완료 여부와 구분합니다.
'''
(ROOT/'이전_이동경로_고려요소.md').write_text(factors,encoding='utf-8')
configs=[]
for node,(_,_,label) in nodes.items():
 selected=[lookup[('base60',node,d,h)] for d in days for h in range(12,19)]
 values=[{ 'hour':f'{int(r["hour"])}시','weekday':r['weekday'],'wait_min':val(r,'mean_wait_min')} for r in selected]
 assert len(values)==35 and len({(x['weekday'],x['hour']) for x in values})==35
 assert all(x['wait_min'] is None or 0<=x['wait_min']<=20 for x in values)
 desc='정류소 도착시간 기준·12:00–19:00·실측이 아닌 조건부 추산. '
 desc+=('대형60명, 입구역 오후4분 배차.' if node.startswith('admin') else '소형25명,302→301 정원 공유·배경 승객 미반영.' if node.startswith('reverse') else '302동 승차 전 가용60명·302→301 정원 공유·배경 승객 미반영.')
 desc+=' 빈칸은 모형 도착량 없음.'
 configs.append({'node':node,'config':{'id':'wait-'+node,'title':label+' 평균 대기(분)','description':desc,'spec':{'type':'heatmap','x':'hour','y':'weekday','value':'wait_min','xOrder':[f'{h}시' for h in range(12,19)],'yOrder':list(days),'xLabel':'정류소 도착 시간대','yLabel':'요일','colorDomain':[0,20],'showValues':True,'missingValues':'gap','valueFormat':{'style':'decimal','maximumFractionDigits':1}},'rows':values,'height':320}})
blocks='\n'.join('<script type="application/json" data-viz-chart data-node="'+x['node']+'">\n'+json.dumps(x['config'],ensure_ascii=False,indent=2).replace('<','\\u003c')+'\n</script>' for x in configs)
template=(ROOT/'wait-chart-template.html').read_text(encoding='utf-8')
fragment=template.replace('<!-- REVIEWED_CHART_CONFIGS -->',blocks)
assert '\\"' not in fragment and len(fragment.encode())<1000000
VIZ.mkdir(parents=True,exist_ok=True)
chart=VIZ/'shuttle-wait-by-weekday.html';chart.write_text(fragment,encoding='utf-8')
(OUT/'chart_configs.json').write_text(json.dumps(configs,ensure_ascii=False,indent=2),encoding='utf-8')
preview=[{'weekday':r['weekday'],'node':r['label'],'hour':r['arrival_window'],'mean_wait_min':val(r,'mean_wait_min'),'arrival_weight':float(r['arrival_weight'])} for r in rows if r['config']=='base60' and r['node']=='admin_snu' and 12<=int(r['hour'])<19]
receipt={'schemaVersion':1,'items':[{'id':'conditional-shuttle-wait','title':'이전 이동량으로 추산한 요일·시간대별 셔틀 대기','assumptions':['대형60명은 사용자 제안이며 확인된 승차정원이 아닙니다. 역순환은25명으로 가정했습니다.','기숙사19.49%·즉시 이동50%·과거 목적지 비중은 시나리오입니다.','302동 이전의 배경 승객과 경로 재선택·환승 지연 전파를 반영하지 않았습니다.'],'queries':[{'id':'queue-hourly','source':{'label':'수업 종료 이동모형과2026-2 셔틀 운행계획','files':[{'label':'conditional_mean_bins.csv'},{'label':'waiting_hourly.csv'},{'label':'estimate_wait.py'},{'label':'verification.json'},{'label':'independent_verification.json'}],'links':[{'label':'서울대학교 공식 운행 안내','url':'https://cse.snu.ac.kr/ko/community/notice/25464'}],'metricDefinitions':[{'label':'조건부 평균 대기시간','definition':'정류소 도착부터 승차까지의 시간을 모형 승차 가중치로 평균합니다. 준비20초와 정원 부족 후 다음 차 대기를 포함합니다.'}],'filters':['요일: 월~금','전체 계산: 정류소 도착11:20~23:10','그림: 정류소 도착12:00~19:00','대표 노선·승차지6개','기준 시나리오: historical_reference'],'caveats':['수강인원 기반 통행 사건은 실제 승객 수가 아닙니다.','이전10회 계산의 평균 유입량에 대한 대기열 결과이며 현장 예측 검증·신뢰구간이 아닙니다.','그림의 빈칸은 모형 도착량이 없어서 평균을 계산하지 않은 경우입니다. 실제 대기0분이 아닙니다.'],'evidenceFlow':[{'kind':'calculation','title':'기존 이동량에서 대기시간으로','detail':'노선별5분 도착 가중치를5초 간격으로 분배한 뒤20개 미관측 출발 위상에서 FIFO 승차·잔류를 계산했습니다.302동 승차량은 같은301동 통과 차량의 잔여정원에서 차감합니다.'},{'kind':'validation','title':'독립 검산','detail':'기존 시나리오 셀 복원 오차는5.7e-14이하였습니다. 행정관 두 줄의 모든 요일115개 시간 셀을 별도 승객 우선 배정으로 확인해 가중 대기합 차이0이었습니다. 표본5초/1초 계산 차이는 최대0.105분입니다.'}]},'reportingPeriod':'2026학년도2학기 일반학기 평일의 조건부 시나리오','columns':[{'field':'weekday','label':'요일'},{'field':'node','label':'승차지·노선'},{'field':'hour','label':'도착시간대'},{'field':'mean_wait_min','label':'평균 대기(분)'},{'field':'arrival_weight','label':'모형 도착 가중치'}],'rows':preview,'methods':[{'language':'calculation','code':'평균 대기 = Σ(승차 가중치 × 정류소 도착부터 승차까지의 시간) / Σ승차 가중치\n정원 부족 추가 대기 = 실제 배정된 출발시각 − 같은 도착시각에서 정원을 무시했을 때의 첫 이용 가능 출발시각\n각 출발 위상은1/20 비중으로 합산합니다.'}]}]}]}
(OUT/'sources_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
print('chart',chart,'configs',len(configs),'cells',len(configs)*35)
print('report',ROOT/'요일시간별_셔틀대기_조건부추산.md')
