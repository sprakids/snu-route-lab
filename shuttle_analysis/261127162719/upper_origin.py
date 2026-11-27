"""Count actual first vehicle boardings by the building of the original Thursday class."""
from collections import Counter
from score import HERE,ROOT,TARGET,NEAR,loc,read,write_rows,POLICIES


def run():
    coursefile=ROOT/'scenario_comparison_2026-11-07/simulation_outputs/input_snapshot/course_endings_current.json'
    courses=[r for r in read(coursefile) if r['included_main'] and r['weekday'] in '월화수목금' and r['end_minute']<=1390]
    replacements=read(ROOT/'261124103744/inputs/thu.json.gz')['replacements']
    parent={r['plan'][0]:r['donor'] for r in replacements}
    common=read(ROOT/'261125170855/viewer-data/common.json.gz')
    baseline={}
    rows=[]
    for v in (*POLICIES,'october02'):
        name='peak-thu'
        a=read(loc(v,name)/f'audit-{name}.json.gz')
        counts=Counter()
        for trip in a['legs']:
            uid=trip['id']
            section=courses[(parent.get(uid,uid)-1)//48]
            assert section['weekday']=='목'
            building=str(section['building'])
            if building not in ('300','301','302'):continue
            w=trip['weight']
            counts[building,'all']+=w
            first=next((leg for leg in trip['legs'] if leg[0]==3),None)
            if first:
                node=common['nodes'][first[4]]
                if node.get('city'):
                    counts[building,node['stop_id']]+=w
        for building in ('300','301','302'):
            total=counts[building,'all']
            if total==0:
                continue
            assert abs(total-baseline.setdefault(building,total))<1e-6
            rows.append(dict(model=v,building=building,upper_trips=total,target=counts[building,TARGET],
                             next_stop=counts[building,NEAR],target_pct=100*counts[building,TARGET]/total))
        if v!='V12':
            summary=read(loc(v,name)/'summary.json')
            assert abs(sum(counts[b,TARGET] for b in baseline)-summary['upper_actual']['first_board_mass'])<1e-6
    write_rows(HERE/'출발동별_첫승차.csv',rows)


if __name__=='__main__':
    run()
