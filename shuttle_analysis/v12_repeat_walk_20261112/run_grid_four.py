"""Finite, source-guarded candidate cases; existing receipts are reused, never rerun."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import argparse,importlib,hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    assert not p.exists(),str(p)
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
def main():
    parser=argparse.ArgumentParser();parser.add_argument('candidate');parser.add_argument('group',choices=['observations','grid']);args=parser.parse_args()
    work=Path(args.candidate).resolve();sys.path.insert(0,str(work))
    import artifacts,run_case,analyze_followup,validation_metrics
    spec=read(work/'experiment_lock.json');manifest=read(work/'repair_manifest.json')
    cfg_hash=sha(work/'config.json');code=run_case.code_manifest()
    def guard():
        assert sha(work/'config.json')==cfg_hash
        assert run_case.code_manifest()==code
        for path,digest in manifest['protected'].items():assert sha(Path(path))==digest,path
        artifacts.check_baseline()
    group=args.group;marker=work/f'{group}-started.json';assert not marker.exists(),'Owned group already consumed'
    if group=='observations':cases=[x for x in spec['pilot_cases'] if x['day'] in ('월','화') and x['scenario']=='regular']
    else:cases=[x for x in spec['pilot_cases'] if not x['case'].startswith('ablation')]
    guard();save(marker,{'cases':cases,'runtime_sha256':code,'config_sha256':cfg_hash,'production_writes':False,'executor_workers':4,'coordinator_script_sha256':sha(Path(__file__))})
    frozen=artifacts.read(work/'frozen/prepared_capacity44_pair.json.gz')
    def worker(case):
        folder=work/'runs'/case['case']/'attempt_01';receipt=folder/'repair_analysis.json'
        if receipt.exists():
            row=read(receipt);audit=folder/f"audit-{case['scenario']}-{artifacts.DAYS[case['day']]}.json.gz"
            assert row['audit_sha256']==sha(audit) and row['case']==case
            print('REUSE_COMPLETED',case['case'],flush=True);return row
        assert not folder.exists(),'Preserve incomplete run; do not create duplicate'
        with (work/(case['case']+'.log')).open('x',encoding='utf8') as stream:
            done=subprocess.run([sys.executable,'-X','utf8',str(work/'run_case.py'),case['case']],cwd=work,stdout=stream,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        assert done.returncode==0,(case['case'],done.returncode)
        guard();row=analyze_followup.verify(case,folder,frozen)
        audit=artifacts.read(folder/f"audit-{case['scenario']}-{artifacts.DAYS[case['day']]}.json.gz")
        row['extended_diagnostics']=validation_metrics.diagnostics(audit,artifacts.START,artifacts.END)
        if audit['prototype_config'].get('waiting_burden_scope')=='whole_journey':
            error=max(abs(t['completed_wait_seconds']-sum((min(l[2],artifacts.END) if t['unserved'] else l[2])-l[1] for l in t['legs'] if l[0]==1)) for t in audit['legs'])
            assert error<2e-5,error
            row['cumulative_wait_reconstruction_max_error_seconds']=error
        row['source_directory']=str(folder);row['unserved_trip_weight']=audit['report']['unserved_trip_weight']
        row['late_finished_weight']=audit['report']['late_arrival_weight'];save(receipt,row)
        print('REPAIR_AUDITED',case['case'],'maxwait',row['maximum_continuous_wait_min'],'over20',row['over20_weight'],
            'total',row['extended_diagnostics']['finished_trip_quantiles']['total_min'],flush=True)
        return row
    with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(worker,cases))
    guard();save(work/f'{group}-validation.json',{'release_id':work.name,'group':group,'results':rows,'source_sha256':code,
      'production_writes':False,'independent_empirical_accuracy':'NOT_EVALUABLE'})
    print('GROUP_COMPLETE',group,len(rows),flush=True)
if __name__=='__main__':main()
