"""Safe, aggregate-only provenance for the inline findings."""
import ast
import json
from pathlib import Path
from analyze_saved import ROOT, write_json

def main():
    c=json.loads((ROOT/'calibration_candidates.json').read_text(encoding='utf-8'))
    meta=json.loads((ROOT/'calibration_contract.json').read_text(encoding='utf-8'))
    src=(ROOT/'analyze_saved.py').read_text(encoding='utf-8');tree=ast.parse(src)
    method='import math, statistics\n\n'+'\n\n'.join(ast.get_source_segment(src,n) for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('q','summary'))
    queries=[]
    for key,label,files,definition,extra,columns in [
     ('headways_17','정류소 통과 간격',['headway_samples_stable_dates.json','headway_candidates_17.csv'],
      '통과 간격은 같은 정류장에서 서로 다른 차량을 검출한 시각의 차이입니다. 차고지 출발간격이나 승객의 대기시간이 아닙니다.',
      ['정류장 중심 60m 이내','stopFlag=true','직전 제공시각과의 차이 120초 이내','통과 간격 15~3600초'],
      ['name','stop','n','mean_seconds','median_seconds','p90_seconds']),
     ('rides_17','정류소 검출 사이 이동시간',['observed_intervals.json','ride_candidates_17.csv'],
      '이동시간은 같은 차량의 두 정류장 검출 시각 사이 경과시간입니다. 정차와 신호 지연을 포함할 수 있습니다.',
      ['정류장 순번 차이 1~12','두 검출 간 경과시간 0초 초과 1800초 이하'],
      ['name','from_stop','to_stop','n','median_seconds','p90_seconds'])]:
        rows=[{k:x.get(k) for k in columns} for x in c[key]]
        queries.append({'id':key.replace('_','-'),'source':{'label':label,'files':[{'label':x} for x in files],
         'metricDefinitions':[{'label':label,'definition':definition}],
         'filters':['한국시간 17시대',*extra],
         'caveats':['검출 사이에 빠진 차량이 있으면 통과 간격이 실제보다 길어질 수 있습니다.',
                     '안정된 검출기 기준으로 확보된 날짜는 이틀뿐이며 같은 차량의 여러 구간은 독립 표본이 아닙니다.'],
         'evidenceFlow':[{'kind':'validation','title':'저장 통계 대조','detail':'11월 10~11일의 노선별 16개 일자·노선 조합에서 원본 재구성 통과 간격 수가 저장 통계와 모두 일치했습니다.'}]},
         'reportingPeriod':'2026-11-10~2026-11-11','columns':columns,'rows':rows,
         'preview':{'kind':'aggregate','note':'17시대에 선택한 정류장 또는 구간의 집계입니다.'},
         'methods':[{'language':'python','code':method}]})
    congestion=[x for x in c['campus_outbound_congestion'] if x['name'] in ['5511','5513','5516']]
    congestion_rows=[{k:x[k] for k in ['name','period','n','congested','congested_fraction']} for x in congestion]
    pairs=[x for x in c['paired_grade_changes'] if x['name'] in ['5511','5513','5516'] and x['n']]
    pair_rows=[{k:x[k] for k in ['name','from_stop','to_stop','n','rise','same','fall']} for x in pairs]
    payload={'schemaVersion':1,'items':[
      {'id':'observed-bus-intervals','title':'시내버스 통과 간격과 이동시간','queries':queries},
      {'id':'observed-bus-congestion','title':'교내 하교 방향의 혼잡 변화','queries':[
       {'id':'campus-congestion-cells','source':{'label':'저장된 혼잡등급 통과 관측',
         'files':[{'label':'grades_by_route_section_hour_weekdays.csv'},{'label':'calibration_candidates.json'}],
         'links':[{'label':'서울시 버스위치정보 API 항목 정의','url':'https://www.data.go.kr/data/15000332/openapi.do'}],
         'metricDefinitions':[{'label':'혼잡 관측 비율','definition':'혼잡 관측 비율은 유효 혼잡등급 통과 관측 중 등급 5·6이 차지하는 비율입니다.'}],
         'filters':['5511 순번 12~21','5513 순번 1~9','5516 순번 12~17','유효 등급 3·4·5·6','정보 없음 0 제외'],
         'caveats':['시간대별 갱신 밀도가 달라 혼잡 비율 비교는 초기 경향입니다.',
                    '등급 변화는 승차·하차 인원이나 남은 정원으로 환산하지 않습니다.',
                    '관악02-1·02-2의 유효 혼잡등급은 0건으로, 여유하다는 뜻이 아닙니다.']},
        'reportingPeriod':'2026-11-09~2026-11-11; 15:00~19:00와 그 외 수집 시간 비교',
        'columns':['name','period','n','congested','congested_fraction'],'rows':congestion_rows,
        'preview':{'kind':'aggregate','note':'교내 하교 방향 3개 노선의 시간대별 집계입니다.'},
        'methods':[{'language':'calculation','code':'혼잡 관측 비율 = (등급 5 관측 수 + 등급 6 관측 수) / 등급 3~6 관측 수'}]},
       {'id':'paired-grade-movements','source':{'label':'동일 차량·추정 회차의 구간 전후 비교',
         'files':[{'label':'calibration_candidates.json'},{'label':'calibration_candidates.py'}],
         'metricDefinitions':[{'label':'혼잡등급 전이','definition':'혼잡등급 전이는 같은 차량·추정 회차에서 두 구간의 등급을 연결해 비교한 변화입니다.'}],
         'filters':['첫 구간 관측시각 15시 이상 19시 미만','두 관측시각 차이 0초 초과 30분 이하'],
         'caveats':['API 구간 순번의 변화이며 특정 정류장에서 탄 인원이나 내린 인원을 직접 측정한 결과가 아닙니다.']},
        'reportingPeriod':'2026-11-09~2026-11-11','columns':['name','from_stop','to_stop','n','rise','same','fall'],
        'rows':pair_rows,'preview':{'kind':'aggregate','note':'유효 등급을 양쪽 구간에서 확인한 동일 차량·회차만 연결했습니다.'}}]},
      {'id':'shuttle-history-gap','title':'셔틀 배차간격의 실측 범위','queries':[{
        'id':'shuttle-storage-contract','source':{'label':'현재 셔틀 수집·저장 코드와 현장 관측',
          'files':[{'label':'shuttle_live.py'},{'label':'worker.mjs'},{'label':'queue_admin_snu_1523.json'}],
          'metricDefinitions':[{'label':'셔틀 배차 이력','definition':'셔틀의 최신 위치 캐시는 덮어써지며 연속 운행 이력을 보존하는 자료가 아닙니다.'}],
          'caveats':['BUSIN 도식 좌표는 GPS가 아니고 공급자 제공시각도 없습니다.',
                     '11월 10일 개인 대기 189초는 실제 배차간격이나 67명 전원의 대기시간이 아닙니다.',
                     '44명 정원과 피크 2대 운행은 사용자 보고이며 실제 배차간격 분포는 아직 식별되지 않았습니다.'],
          'evidenceFlow':[{'kind':'validation','title':'운행 이력 저장 경로 확인','detail':'최신 셔틀 상태는 shuttle-cache-v1에 덮어쓰며, 날짜별 원본과 route_stats에는 8개 시내버스 노선만 저장합니다.'}]},
         'summary':'셔틀의 실제 배차간격 분포와 교통량별 완료 주행시간은 현재 축적 자료에서 계산할 수 없습니다.'}]}]}
    write_json(ROOT/'reviewed_sources.json',payload)
    print('safe_source_items',len(payload['items']))

if __name__=='__main__':main()
