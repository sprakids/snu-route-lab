"""Independent arithmetic/binding checks over the retained paired results."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
summary=json.loads((ROOT/'comparison.json').read_text(encoding='utf-8'))
plans={k:json.loads((ROOT/(k+'-plan.json')).read_text(encoding='utf-8')) for k in ('old','new')}
chart=Path('C:/Users/김예준/.codex/visualizations/2026/11/03/01a1a1e8-54cf-7243-9ad9-0a31e6f31a06/admin-station-model-comparison.html').read_text(encoding='utf-8')
config=json.loads(re.search(r'<script type="application/json" data-viz-chart>\s*([\s\S]*?)\s*</script>',chart)[1])
ids=['route-5','route-17','route-0','route-10']
for plot,metric in zip(config['charts'],['total_seconds','wait_seconds']):
    for row,rid in zip(plot['rows'],ids):
        for col,label in [(1,'old'),(2,'new')]:
            candidate=next(c for c in plans[label]['candidates'] if c['id']==rid)
            assert abs(row[col]*60-candidate[metric])<1e-9
for p in plans.values():
    for c in p['candidates']:
        parts={kind:sum(l['seconds'] for l in c['legs'] if l['type']==kind) for kind in ['walk','wait','bus','board']}
        assert c['total_seconds']==sum(parts.values())
        for kind,field in [('walk','walk_seconds'),('wait','wait_seconds'),('bus','ride_seconds'),('board','boarding_seconds')]:
            assert c[field]==parts[kind]
old={c['id']:c for c in plans['old']['candidates']};new={c['id']:c for c in plans['new']['candidates']}
assert old.keys()==new.keys()
changes={key:{'total_delta_seconds':new[key]['total_seconds']-old[key]['total_seconds'],
    'wait_delta_seconds':new[key]['wait_seconds']-old[key]['wait_seconds']} for key in old if old[key]['total_seconds']!=new[key]['total_seconds']}
assert changes=={'route-10':{'total_delta_seconds':-60,'wait_delta_seconds':-60}},changes
release=ROOT.parent/'simulation_viewer_2026-11-07/public/routing-model/releases'
data={label:json.loads((release/(mid+'.json')).read_text(encoding='utf-8')) for label,mid in [('old','261109152540'),('new','261109173153')]}
clock_fields=['n','stops','capacity','offsets','anchor','loop']
for rid,route in data['old']['routes'].items():
    for field in clock_fields:assert route.get(field)==data['new']['routes'][rid].get(field),(rid,field)
bundle=json.loads((ROOT/'frozen-inputs.json').read_text(encoding='utf-8'))
cache=[v for k,v in bundle['cache'].items() if k.startswith('arrivals-') and v]
valid=sum(any(a.get('provided_at') is not None and -5<=bundle['asof']-a['provided_at']<=150 for a in v.get('values',[])) for v in cache)
result={'status':'PASS','paired_candidate_ids':len(old),'changed_total_time_candidates':changes,
    'chart_payloads':len(config['charts']),'all_80_candidate_time_sums_reconciled':True,
    'shuttle_clock_capacity_topology_equal':True,'valid_city_arrival_cache_entries':valid,
    'city_arrival_note':'No valid direct arrival observations; city alternatives use the same saved position/history/service estimates.',
    'scope':'Single-departure model comparison; not measured travel-time savings or independent empirical validation.'}
(ROOT/'checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=True,indent=2))
