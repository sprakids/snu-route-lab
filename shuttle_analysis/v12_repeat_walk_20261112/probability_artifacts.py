"""Controlled probability law and actual decision-opportunity distributions."""
from pathlib import Path
import argparse,csv,gzip,hashlib,json,math,sys
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def csvout(p,rows):
    assert not p.exists();f=p.open('w',encoding='utf-8-sig',newline='');w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows);f.close()
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');p.add_argument('--group',default='grid');a=p.parse_args();w=Path(a.candidate).resolve();sys.path.insert(0,str(w))
    from preferences import exponential_walk_shift
    cfg=read(w/'config.json');table=[]
    for base in (.01,.05,.1,.25,.5):
        for n in range(9):
            opts=[{'cost':0.,'prior':base,'option':{'stages':[]}},{'cost':0.,'prior':1-base,'option':None}]
            shift,d=exponential_walk_shift(opts,cfg,n);expected=1-(1-base)**(2**n)
            expected=min(max(base,1-cfg['repeat_walk_numeric_epsilon']),expected)
            assert abs(d['target_probability']-expected)<1e-11
            table.append({'fixed_reference_probability':base,'completed_changes':n,'target_probability':d['target_probability'],
              'numeric_saturation':d['numeric_saturation'],'scenario_growth_factor':cfg['repeat_walk_growth_factor']})
    law=w/'probability-law.csv'
    if not law.exists():csvout(law,table)
    v=read(w/(a.group+'-validation.json'));stats=[];checks=0;max_error=0.
    for r in v['results']:
        case=r['case'];report=r['policy_report'];did={'월':'mon','화':'tue','수':'wed','목':'thu','금':'fri'}[case['day']]
        for s in report['repeat_walk_choice_statistics']:
            mass=s['decision_weight'];available=s['walk_available_weight']
            stats.append({'weekday':case['day'],'scenario':case['scenario'],'phase':s['phase'],'completed_changes':s['completed_changes'],
              'decision_count':s['decisions'],'decision_weight':mass,'walk_available_weight':available,
              'mean_unboosted_probability':s['unboosted_probability_weighted_sum']/mass,
              'mean_reference_probability':s['reference_probability_weighted_sum']/mass,
              'mean_target_probability':s['target_probability_weighted_sum']/mass,
              'realized_terminal_walk_fraction':s['terminal_walk_selected_weight']/mass,
              'scope':'weighted decisions, repeat observations of same synthetic travelers, not unique students'})
        path=Path(r['source_directory'])/f"audit-{case['scenario']}-{did}.json.gz";audit=read(path)
        events=[(e,e.get('change_count_before')) for e in audit['behavior_decisions']]+[(e,e.get('change_count')) for e in audit['boarding_choices']]
        for e,count in events:
            d=e.get('terminal_walk_rule')
            if d is None:continue
            assert count==d['completed_changes']
            p0=d['reference_probability'];n=count;g=d['growth_factor']
            if p0<=0:expected=0.
            elif p0>=1:expected=1.
            else:
                exponent=n*math.log(g)
                if exponent>700:expected=max(p0,1-cfg['repeat_walk_numeric_epsilon'])
                else:expected=-math.expm1(math.log1p(-p0)*math.exp(exponent))
                expected=min(max(p0,1-cfg['repeat_walk_numeric_epsilon']),expected)
            err=abs(d['target_probability']-expected);max_error=max(max_error,err)
            assert err<1e-7,(case,e.get('uid'),count,p0,d['target_probability'],expected)
            assert d['target_probability']>=d['unboosted_probability']-1e-10
            checks+=1
        print('PROBABILITY_AUDITED',case['case'],flush=True)
    csvout(w/f'{a.group}-walking-by-change-count.csv',stats)
    result={'status':'PASS_CONTROLLED_LAW_AND_RECORDED_TARGETS','group':a.group,'controlled_rows':len(table),
      'recorded_probability_checks':checks,'maximum_probability_formula_error':max_error,'actual_opportunity_rows':len(stats),
      'conditional_choice_not_review_hazard':True,'growth_not_empirically_estimated':True,'production_writes':False}
    target=w/f'{a.group}-probability-validation.json';assert not target.exists();target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print('PROBABILITY_VALIDATION_COMPLETE',checks,'error',max_error,flush=True)
if __name__=='__main__':main()
