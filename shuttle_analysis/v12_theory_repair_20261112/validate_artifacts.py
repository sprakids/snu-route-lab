"""Reconcile delivered tables, source case keys, local links and explicit regressions."""
from pathlib import Path
import argparse
import csv,hashlib,json,re
ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent;WORK=ANALYSIS/'261112132736'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--final',action='store_true');args=parser.parse_args()
    report='RESULTS_FINAL.md' if args.final else 'RESULTS.md'
    recommendation='release_recommendation_final.json' if args.final else 'release_recommendation.json'
    target=WORK/('artifact_verification_final.json' if args.final else 'artifact_verification.json');assert not target.exists()
    d=read(WORK/'grid-diagnostics.json');v=read(WORK/'grid-validation.json');old=read(ANALYSIS/'261112111627/validation_reference_corrected.json')
    rows=d['cases'];assert len(rows)==10 and len({(r['case']['day'],r['case']['scenario']) for r in rows})==10
    assert all(r['case']['seed']==0 and not r['case']['case'].startswith('ablation') for r in rows)
    baseline={(r['case']['day'],r['case']['scenario'],r['case']['seed']):r for r in old['results']}
    maxima=[];mean_regressions=[];walking_increases=[];improvements={'mean_total':0,'p99_total':0,'max_total':0}
    for row in rows:
        c=row['case'];a=row['all_recorded_diagnostics']['finished_trip_quantiles'];b=baseline[c['day'],c['scenario'],c['seed']]['extended_diagnostics']['finished_trip_quantiles']
        maxima.append((row['all_recorded_diagnostics']['all_recorded_time_max_continuous_wait_min'],a['total_min']['maximum']))
        for name,key in [('mean_total','mean'),('p99_total','p99'),('max_total','maximum')]:improvements[name]+=a['total_min'][key]<b['total_min'][key]
        if a['total_min']['mean']>b['total_min']['mean']:
            mean_regressions.append({'day':c['day'],'scenario':c['scenario'],'mean_minutes_before':b['total_min']['mean'],
              'mean_minutes_after':a['total_min']['mean'],'increase_minutes':a['total_min']['mean']-b['total_min']['mean']})
        if a['walk_min']['mean']>b['walk_min']['mean']:
            walking_increases.append({'day':c['day'],'scenario':c['scenario'],'increase_minutes':a['walk_min']['mean']-b['walk_min']['mean']})
    csvcounts={}
    for name,expected in [('grid-all-stops.csv',990),('grid-half-hour-waits.csv',d['half_hour_rows']),('grid-field-comparison.csv',32),('grid-journey-comparison.csv',40),('origin-assignment-comparison.csv',8)]:
        with (WORK/name).open(encoding='utf-8-sig') as f:data=list(csv.DictReader(f))
        assert len(data)==expected,(name,len(data),expected);csvcounts[name]=len(data)
        if name=='grid-half-hour-waits.csv':assert all(int(r['queue_entry_half_hour'])%1800==0 and float(r['over20_episode_weight'])<1e-7 for r in data)
    linked=[]
    docs=[WORK/report,WORK/'README.md',WORK/'ORIGIN_CONTRAST.md',ROOT/'README.md',ROOT/'THEORY_REVIEW.md']
    for doc in docs:
        for url in re.findall(r'\]\(([^)]+)\)',doc.read_text(encoding='utf8')):
            if '://' in url or url.startswith('#'):continue
            path=(doc.parent/url.split('#')[0]).resolve();assert path.is_file(),(doc,url);linked.append(str(path))
    decision=read(WORK/recommendation);assert decision['report_sha256']==sha(WORK/report)
    assert read(WORK/'final_verification.json')['status']=='PASS'
    sources=[report,'README.md',recommendation,'grid-validation.json','grid-diagnostics.json','final_verification.json',
      'future_evaluation_plan.json','protocol_clarification.json','ORIGIN_CONTRAST.md','boundary-tests.log',*csvcounts]
    result={'status':'PASS_ARTIFACT_CONSISTENCY','release_id':WORK.name,'case_count':10,'same_seed_reference_check':'PASS',
      'maximum_continuous_wait_minutes':max(x[0] for x in maxima),'maximum_total_journey_minutes':max(x[1] for x in maxima),
      'improved_case_counts_vs_V12':improvements,'mean_total_regressions':mean_regressions,'mean_walking_increases':walking_increases,
      'csv_rows':csvcounts,'local_document_links_checked':len(linked),
      'preserved_initial_access_path_fragment_checks':sum(r['preserved_initial_access_path_trip_fragment_checks'] for r in rows),
      'artifact_sha256':{name:sha(WORK/name) for name in sources},
      'known_remaining_constraints':f'See {recommendation}: old field errors, named40-reference peaks and first-boardable prediction approximation',
      'empirical_validation':'NOT_EVALUABLE','production_replacement_allowed':False}
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(result['status'],result['improved_case_counts_vs_V12'],'mean regressions',mean_regressions,
      'walking increases',len(walking_increases),'links',len(linked),'initial path fragments',result['preserved_initial_access_path_fragment_checks'])
if __name__=='__main__':main()
