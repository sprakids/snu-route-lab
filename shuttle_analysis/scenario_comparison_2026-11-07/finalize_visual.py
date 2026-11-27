"""Bind reviewed values to the literal, task-owned inline chart fragment."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parent
VIZ=Path('C:/Users/김예준/.codex/visualizations/2026/10/21/01a15f4b-516c-79b1-9b9a-c31680e1acd7/shuttle-destination-sensitivity.html')
data=json.loads((ROOT/'comparison_chart_data.json').read_text(encoding='utf-8'))
stops=['snu-410','120000174','120000173','snu-1001','snu-901','120900172']
labels={'snu-410':'행정관 (셔틀)','120000174':'유회진학술정보관·제1공학관 (시내)',
        '120000173':'제2공학관 (시내)','snu-1001':'301동 (교내셔틀)',
        'snu-901':'302동 (교내셔틀)','120900172':'노천강당 (시내)'}
lookup={(r['scenario'],r['window'],r['stop_id']):r for r in data['rows']}
maximum=max(r['peak_5min_weight'] for r in data['rows'] if r['stop_id'] in stops)
domain_top=50*(int(maximum/50)+1)
blocks=[]
for scenario in data['scenarios']:
    for scope,title_scope in [('afternoon','15:00–23:10'),('all','11:20–23:10')]:
        name=scenario['name']
        rows=[[labels[stop],lookup[('historical_reference',scope,stop)]['peak_5min_weight'],
               lookup[(name,scope,stop)]['peak_5min_weight']] for stop in stops]
        summary=(f"비교: {scenario['label']} · 교외 목적지 {100*scenario['external_mix'][0]:.2f} / "
                 f"{100*scenario['external_mix'][1]:.2f} / {100*scenario['external_mix'][2]:.2f}% · "
                 f"기숙사 {100*scenario['dorm_share']:.2f}% · 즉시 이동 50%")
        config={
            'id':'shuttle-stop-peak-chart',
            'title':f'정류장별 최대 5분 유입 · {title_scope}',
            'description':'월~금 중 최대값 · 최초·환승 탑승 포함 · 조건부 예상 통행 가중치, 실측 인원·대기열 아님',
            'summary':summary,'height':480,
            'spec':{'type':'horizontalBar','y':'정류장','x':['과거 참고','비교 시나리오'],
                    'xLabel':'예상 탑승 통행 가중치 / 5분','showValues':True,'showLegend':True,
                    'startAtZero':True,'xDomain':[0,domain_top],
                    'valueFormat':{'style':'decimal','maximumFractionDigits':1},
                    'colors':{'과거 참고':'var(--chart-2)','비교 시나리오':'var(--chart-1)'}},
            'columns':['정류장','과거 참고','비교 시나리오'],'rows':rows}
        payload=json.dumps(config,ensure_ascii=False).replace('<','\\u003c')
        blocks.append(f'<script type="application/json" data-viz-chart data-state="{name}|{scope}">\n{payload}\n</script>')
fragment=VIZ.read_text(encoding='utf-8')
assert fragment.count('<!-- CHART_PAYLOADS -->')==1, 'Use the preserved literal template; do not append duplicate configurations'
fragment=fragment.replace('<!-- CHART_PAYLOADS -->','\n'.join(blocks))
assert len(fragment.encode('utf-8'))<1_000_000
VIZ.write_text(fragment,encoding='utf-8')
print(json.dumps({'configs':len(blocks),'value_domain':[0,domain_top],'bytes':len(fragment.encode('utf-8'))}))
