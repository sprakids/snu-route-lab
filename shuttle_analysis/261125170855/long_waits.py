"""Trace every over-20-minute physical queue episode back to its vehicle events."""
import math
import csv
import json
from collections import defaultdict

from evaluate import HERE, PRIOR, read, table
from simulate import prior


def main():
    nodes = read(PRIOR / 'viewer-data/common.json.gz')['nodes']
    rows = []
    changed = {}
    for summary in sorted((HERE / 'runs/candidate').glob('*/summary.json')):
        case = read(summary)
        key = summary.parent.name
        audit = read(summary.parent / f'audit-{key}.json.gz')
        final = [v for v in audit['behavior_decisions'] if v['reason']=='last_eligible_service_departed']
        changed[key] = {'rerouted_weight':sum(v['weight'] for v in final),
                        'to_walk_weight':sum(v['weight'] for v in final if v['kind']=='walk')}
        if key.endswith('tue'):
            # Regression reproduced by both services in the previous matched run.
            target = [v for v in final if v['uid']==23016 and v['origin']==20]
            assert target and all(v['continuous_wait_seconds']<1e-5 for v in target)
            changed[key]['agriculture_episode'] = [
                {k:v[k] for k in ('time','kind','continuous_wait_seconds','weight')} for v in target]
        if case['over20_weight'] <= 1e-7:
            continue
        episodes = defaultdict(float)
        for node, start, end, weight, uid in prior.physical_waits(audit):
            if end - max(start + 1200, prior.field.seconds('11:20')) > 1e-6:
                episodes[node, start, end, uid] += weight
        assert math.isclose(sum(episodes.values()), case['over20_weight'], abs_tol=1e-6)
        for (node, start, end, uid), weight in episodes.items():
            visits = [w for w in audit['wait_audit'] if w['node'] == node and w['id'] == uid
                      and abs(w['physical_stop_entry'] - start) < 1e-5
                      and start <= w['end'] <= end + 1e-5]
            eligible = {tuple(pair) for w in visits for pair in w['eligibility']}
            buses = [e for e in audit['events'] if e[1] == node and start < e[0] <= end + 1e-5
                     and tuple(e[11:13]) in eligible]
            rows.append(dict(day=case['day'], service=case['service'], stop=nodes[node]['name'],
                             entry_seconds=start, end_seconds=end, minutes=(end-start)/60,
                             weight=weight, routes=' / '.join(sorted({str(r) for r, k in eligible})),
                             departures=len(buses), full_departures=sum(e[7] >= e[3]-1e-6 for e in buses),
                             outcome=' / '.join(sorted({w['outcome'] for w in visits if abs(w['end']-end)<1e-5}))))
    if rows:
        table(HERE/'20분초과_원인.csv', rows)
    else:
        with (HERE/'20분초과_원인.csv').open('w', encoding='utf-8-sig', newline='') as f:
            csv.writer(f).writerow(('day','service','stop','entry_seconds','end_seconds','minutes',
                                    'weight','routes','departures','full_departures','outcome'))
    (HERE/'막차후_경로전환.json').write_text(json.dumps(changed,ensure_ascii=False,indent=2),encoding='utf8')
    print(len(rows), sum(r['weight'] for r in rows), flush=True)


if __name__=='__main__':
    main()
