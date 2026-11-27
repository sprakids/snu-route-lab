"""Build explanatory scenario evidence. None of these means are ETA inputs."""
import csv,hashlib,json,math
from pathlib import Path
from adaptive import POLICY

def build(source=None,target=None):
    source=Path(source) if source else Path(__file__).resolve().parents[1]/'adaptive_comparison_2026-11-07'
    names=['비교_정의와_결과.md','요일_시간대별_전후비교.csv','reviewed_results.json','verification.json','independent_check.json']
    evidence={name:source.joinpath(name).read_bytes() for name in names}
    assert json.loads(evidence['verification.json'])['status']=='PASS'
    assert json.loads(evidence['independent_check.json'])['status']=='PASS'
    reviewed=json.loads(evidence['reviewed_results.json'])
    rows=list(csv.DictReader(evidence['요일_시간대별_전후비교.csv'].decode('utf-8-sig').splitlines()))
    assert len(rows)==len(reviewed['hourly'])==720
    summaries=[]
    for scenario in ('peak','regular'):
        for origin,scope in [('all','snu_all'),('all','snu_initial_shuttle'),('301_302','snu_all')]:
            group=[r for r in rows if r['scenario']==scenario and r['origin']==origin and r['scope']==scope]
            def mean(field,weight):
                terms=[(float(r[field]),float(r[weight])) for r in group if r[field] and float(r[weight])>0]
                return math.fsum(v*w for v,w in terms)/math.fsum(w for v,w in terms)
            item={'scenario':scenario,'origin':origin,'scope':scope,
                'weight':math.fsum(float(r['weight']) for r in group)}
            for side in ('before','after'):
                item['wait_'+side]=mean('wait_all_min_'+side,'weight')
                item['total_'+side]=mean('total_common_min_'+side,'common_complete_weight')
            summaries.append(item)
    out={'schema':'adaptive_reference_v1','policy':POLICY,'display_only':True,'eta_adjustment_seconds':0,
         'observed_validation':False,'source_sha256':{n:hashlib.sha256(b).hexdigest() for n,b in evidence.items()},
         'definitions':{'wait':'최초 수업 종료 11:20~23:10 집단의 줄 이탈 전·시내버스·환승 누적 대기. 미완료는23:10절단.',
                        'total':'양쪽에서 완주한 동일 최초 가중 집단의 총시간. 현재 정류장 대기 인원이 아님.',
                        'restricted_total':'23:10절단 경과시간이며 완료 이동시간이 아님.'},
         'summaries':summaries,'note':'모형 비교 설명·검산용. 평균 절감·탑승자만의 평균은 경로 ETA에 차감하지 않습니다.'}
    target=Path(target) if target else Path(__file__).parent/'data/adaptive_reference.json'
    target.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    return out

if __name__=='__main__':
    x=build();print({'schema':x['schema'],'display_only':x['display_only'],'summary_count':len(x['summaries'])})
