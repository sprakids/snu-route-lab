from pathlib import Path
import json,math,re

ROOT=Path(__file__).resolve().parent
VIZ=Path('C:/Users/김예준/.codex/visualizations/2026/10/21/01a15f4b-516c-79b1-9b9a-c31680e1acd7')
DATA=json.loads((ROOT/'reviewed_results.json').read_bytes())
DAYS=['월','화','수','목','금']
TARGETS={'all':('all','snu_all'),'shuttle':('all','snu_initial_shuttle'),'upper':('301_302','snu_all')}
METRICS={'wait':('wait_all_min','누적 대기'), 'total':('total_common_min','서울대입구 총 소요'),
         'restricted':('restricted_total_min','23:10까지 경과시간')}

def filt(rows,origin,scope,scenario=None):
    return [x for x in rows if x['origin']==origin and x['scope']==scope and (scenario is None or x['scenario']==scenario)]
def summarize(rows):
    w=sum(x['weight'] for x in rows);c=sum(x['common_complete_weight'] for x in rows)
    out={'weight':w,'common':c,'unserved':sum(x['unserved_weight_before'] for x in rows),
         'changed':sum(x['changed_weight_after'] for x in rows)}
    for metric,(col,_) in METRICS.items():
        den=c if metric=='total' else w
        out[metric]={key:sum((x[col+'_'+key] or 0)*(x['common_complete_weight'] if metric=='total' else x['weight']) for x in rows)/den if den else None for key in ['before','after']}
    out['worsened_weight']=sum(x['worsened_original_particle_weight'] for x in rows)
    return out

def main():
    all_day=[x for x in DATA['daily'] if x['period']=='all'];summaries={};configs={}
    for scenario in ['peak','regular']:
        for target,(origin,scope) in TARGETS.items():
            rows=filt(all_day,origin,scope,scenario);hourly=filt(DATA['hourly'],origin,scope,scenario)
            summaries[scenario+'|'+target]=summarize(rows)
            for metric,(col,title) in METRICS.items():
                daily_values=[x[col+'_'+k] for x in filt(all_day,origin,scope) for k in ['before','after'] if x[col+'_'+k] is not None]
                hourly_values=[x[col+'_'+k] for x in filt(DATA['hourly'],origin,scope) for k in ['before','after'] if x[col+'_'+k] is not None]
                high=max(1,math.ceil(max(daily_values)/5)*5)
                config={'id':'snu-rerouting-daily','title':'요일별 '+title+' (분)','height':290,
                    'description':'동일 수업 종료 흐름 · 서울대입구행 · 변경 전후',
                    'spec':{'type':'bar','x':'weekday','y':'minutes','series':'phase','yLabel':'분','showValues':True,
                            'showLegend':True,'yDomain':[0,high], 'valueFormat':{'style':'decimal','maximumFractionDigits':2}},
                    'columns':['weekday','phase','minutes'],
                    'rows':[[day,ko,next(x for x in rows if x['weekday']==day)[col+'_'+policy]] for day in DAYS for policy,ko in [('before','변경 전'),('after','변경 후')]]}
                configs['|'.join([scenario,target,metric,'daily'])]=config
                charts=[]
                domain=[0,max(1,math.ceil(max(hourly_values)/5)*5)]
                for policy,ko in [('before','변경 전'),('after','변경 후')]:
                    charts.append({'id':'snu-rerouting-'+policy,'title':ko+' · '+title+' (분)','height':280,
                        'spec':{'type':'heatmap','x':'hour','y':'weekday','value':'minutes','xLabel':'수업 종료 시각(시)','yLabel':'요일',
                            'xOrder':[str(h) for h in range(11,23)],'yOrder':DAYS,'colorDomain':domain,
                            'showValues':True,'missingValues':'gap','valueFormat':{'style':'decimal','maximumFractionDigits':2}},
                        'columns':['hour','weekday','minutes'],
                        'rows':[[str(h),day,next(x for x in hourly if x['weekday']==day and x['class_end_hour']==h)[col+'_'+policy]]
                                for day in DAYS for h in range(11,23)]})
                configs['|'.join([scenario,target,metric,'hourly'])]={'charts':charts}
    path=VIZ/'shuttle-rerouting-comparison.html';html=path.read_text(encoding='utf-8')
    blocks='\n'.join('<script type="application/json" data-viz-chart data-key="'+key+'">'+json.dumps(value,ensure_ascii=True,allow_nan=False).replace('<','\\u003c')+'</script>' for key,value in configs.items())
    if '<!-- REVIEWED_CONFIGURATIONS -->' in html:html=html.replace('<!-- REVIEWED_CONFIGURATIONS -->',blocks)
    else:
        html=re.sub(r'<script type="application/json" data-viz-(?:chart|state) data-key="[^"]+">.*?</script>\s*','',html,flags=re.S)
        html=html.replace('<script type="application/json" id="snu-compare-summaries">',blocks+'\n<script type="application/json" id="snu-compare-summaries">')
    html=re.sub(r'(<script type="application/json" id="snu-compare-summaries">).*?(</script>)',
                lambda m:m.group(1)+json.dumps(summaries,ensure_ascii=False,allow_nan=False)+m.group(2),html,flags=re.S)
    assert len(html.encode())<1000000 and '\\"' not in html
    path.write_text(html,encoding='utf-8')
    # Calculation notes retain the complete exact-value comparison without
    # changing the working simulator, its charts, or the distribution ZIP.
    lines=['# 경로 변경 전후: 같은 이동 흐름으로 비교','',
        '분석 기준: 2026-11-07 저장 v3·v4. 새 시뮬레이션 실행 없이 전체 감사 이동기록을 재집계했다.',
        '대상 시간: 수업 종료 11:20~23:10. 시간대는 최초 수업 종료시각으로 고정하며, 변경 뒤 정류장 도착시각으로 집단을 다시 나누지 않았다.',
        '대기는 줄을 떠나기 전 대기와 다른 버스·환승 대기를 합한 23:10까지의 누적값이다. 도보만 이동한 흐름은 0분이다.',
        '총시간은 수업 종료부터 서울대입구 대표점까지다. 건물 이탈·모든 보행·모든 대기·차내 이동을 포함한다.',
        '총시간 평균은 양쪽에서 전체 가중치가 모두 완주한 동일한 최초 입자 집단이다. 미도착을 0분이나 도착한 것으로 처리하지 않았다.',
        '전체 흐름의 23:10까지 경과시간도 restricted_total_min 열에 제공한다. 미도착도 포함하는 제한 지표이며 완주 총시간이 아니다.',
        '모든 수치는 수강인원 기반 가중 이동 사건의 모형 결과다. 고유 학생 수·실제 대기 측정치·독립 반복 평균이 아니다.','',
        '## 요일별 서울대입구행 전체','',
        '| 배차 | 요일 | 대기 전→후(분) | 대기 감소 | 총시간 전→후(분) | 총시간 감소 | 공통 완주 포함 비중 | 변경 전 미도착 가중치 |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for scenario in ['peak','regular']:
        for x in filt(all_day,'all','snu_all',scenario):
            lines.append(f"| {'피크 최소간격' if scenario=='peak' else '기준'} | {x['weekday']} | {x['wait_all_min_before']:.2f}→{x['wait_all_min_after']:.2f} | {x['wait_all_min_saved']:.2f} | {x['total_common_min_before']:.2f}→{x['total_common_min_after']:.2f} | {x['total_common_min_saved']:.2f} | {x['common_complete_share_pct']:.4f}% | {x['unserved_weight_before']:.4f} |")
    lines+=['','## 요일 × 수업 종료 시간대 전체표','',
        '대기와 총시간은 위의 서로 다른 분모 정의를 유지한다. 가중치 0인 칸은 결측이며 0분이 아니다. 11시 구간은 11:20 이후다. 23시 종료 입력은 없다.','']
    for scenario in ['peak','regular']:
        for day in DAYS:
            lines+=['',f"### {'피크 최소간격' if scenario=='peak' else '기준'} · {day}",'',
                '| 수업 종료 | 도착지 배정 가중치 | 대기 전→후(분) | 총시간 전→후(분) | 변경 전 미도착 | 변경 후 변경 가중치 |',
                '|---|---:|---:|---:|---:|---:|']
            for x in filt(DATA['hourly'],'all','snu_all',scenario):
                if x['weekday']!=day or not x['weight']:continue
                total=f"{x['total_common_min_before']:.2f}→{x['total_common_min_after']:.2f}" if x['common_complete_weight'] else '공통 완주 없음'
                lines.append(f"| {x['class_end_hour']}시 | {x['weight']:.2f} | {x['wait_all_min_before']:.2f}→{x['wait_all_min_after']:.2f} | {total} | {x['unserved_weight_before']:.4f} | {x['changed_weight_after']:.2f} |")
    lines+=['','## 월~금 가중 합산','',
        '| 배차·대상 | 누적대기 전→후 | 공통완주 총시간 전→후 | 전원 포함 23:10까지 경과시간 전→후 | 대상 가중치 |',
        '|---|---:|---:|---:|---:|']
    for key,s in summaries.items():
        lines.append(f"| {key} | {s['wait']['before']:.3f}→{s['wait']['after']:.3f} | {s['total']['before']:.3f}→{s['total']['after']:.3f} | {s['restricted']['before']:.3f}→{s['restricted']['after']:.3f} | {s['weight']:.2f} |")
    lines+=['','all=서울대입구행 전체, shuttle=변경 전 최초 경로에 셔틀이 포함된 집단, upper=301·302동 출발 집단. 배차 peak/regular는 같은 배차끼리 전후 비교했다.',
        '전 목적지(all_destinations)의 대기도 CSV에 있다. 이 행의 총시간은 각 가정 목적지까지이며 서울대입구까지가 아니다.',
        '전체 서울대입구행 가중치 31,002.90 중 변경 전 미도착 8.3417, 변경 후 0. 이 흐름의 누적대기는 전원 포함 값에 남겼고, 완주 총시간 비교에서는 별도로 분리했다.',
        '대표 난수 반복의 결과이며, 요금·날씨·실제 정체·시내버스 수용력·수업 외 승객의 행동은 검증되지 않았다. 최초 수단 선택도 기존 경로를 유지한다.',
        'wait_all_min_saved와 total_common_min_saved의 차이는 단순히 보행 증가가 아니다. 분모가 다르고 전자는 미완주 대기의 검열도 포함한다. 공통 완주 집단에서 구성시간을 비교해야 한다.',
        '원래 입자가 일부 분할된 경우 그 입자 전체가 양쪽 모두 완주했을 때만 총시간 공통 집단에 포함했다. 원래 입자별 평균 총시간이 1초 초과 증가한 경우도 CSV의 worsened_original_particle_weight로 기록했다. 실제 개인별 위험 비율은 아니다.','',
        '## 재현·확인','',
        '- `compare_full_trips.py`: 원래 입자 297,648개를 수업 종료 사건 6,201개에 대응. 같은 건물·요일·이탈 지연 1~8분을 전수 확인.',
        '- 모든 원래 입자의 가중치를 전후에서 대조했고, 분할 후의 최종 가중치를 다시 합산했다.',
        '- 최종 흐름의 셔틀 대기 합계를 별도 대기 사건 자료와 교차 대조했다. 이탈한 대기 사건도 포함한다.',
        '- 요일×시간 가중 합계와 요일별 합계를 재대조했다. 일별 평균을 단순 평균하지 않았다.',
        '- `independent_check.json`: 월요일 피크의 서울대입구행 전체를 원본 이력에서 별도 순회·집계해 주요 대기·총시간 평균과 1e-8분 이내 일치 확인.',
        '- `verification.json`: 입력 파일 SHA-256, 시간 창, 분모, 가중치·대기 노출 대조 결과.',
        '- 기존 사이트·모형·공유 ZIP은 변경하지 않았다.']
    (ROOT/'비교_정의와_결과.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    code=(ROOT/'compare_full_trips.py').read_text(encoding='utf-8')
    payload={'schemaVersion':1,'items':[{'id':'queue-leavers-included','title':'줄에서 떠난 흐름을 포함한 전후 비교','queries':[
        {'id':'full-history','summary':'같은 최초 가중 이동 흐름의 셔틀·시내버스 대기와 목적지 도착시각을 비교한다. 탑승자만으로 집단을 다시 정의하지 않는다.',
         'source':{'label':'v3·v4 전체 이동 감사기록과 수업 종료 입력',
                   'filters':['대상: 서울대입구행 전체 또는 변경 전 셔틀 포함 또는 301·302동 출발',
                              '수업 종료 창: 11:20~23:10','배차: 같은 조건끼리 전후 비교','시간대: 변경 전 수업 종료시각 고정'],
                   'caveats':['누적 대기는 미도착 흐름도 23:10까지 포함하므로 일부는 완전한 대기시간이 아닌 검열된 값이다.',
                              '완주 총시간은 양쪽 모두 완주한 동일 원래 입자 집단으로 비교하며 미도착은 별도로 집계한다.',
                              '실제 학생의 관측 결과가 아닌 대표 난수 반복의 가중 모형 결과다.']},
         'methods':[{'language':'python','code':code}]}]}]}
    (ROOT/'reviewed-sources.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'presentation_configurations.json').write_text(json.dumps(configs,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Native configs',len(configs),'fragment bytes',len(html.encode()),'working comparison notes saved.')
    print(json.dumps(summaries,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
