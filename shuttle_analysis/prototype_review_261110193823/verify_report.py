"""Check reviewed numbers, audit hashes, links and generated figures once."""
from pathlib import Path
import argparse,csv,hashlib,json,re,struct
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main(attempt):
    target=ROOT/f'report_verification_{attempt:02d}.json';assert not target.exists()
    result={'status':'STARTED','simulation_reruns':0,'production_writes':False}
    try:
        r=read(ROOT/'review.json');vroot=Path(r['validation']);v=read(vroot/'validation.json');parent=Path(r['candidate'])
        assert r['internal_status']==v['status'] and r['empirical_status']=='NOT_EVALUABLE'
        assert not r['new_algorithm_promoted'] and not r['production_candidate_ready']
        assert len(r['weekday_comparison'])==10 and len(r['factor_comparison'])==6 and len(v['results'])==12
        count=0
        for cell in v['results']:
            c=cell['case'];folder=Path(cell['source_directory']);day={'월':'mon','화':'tue','수':'wed','목':'thu','금':'fri'}[c['day']]
            audit=folder/f'audit-{c["scenario"]}-{day}.json.gz';assert sha(audit)==cell['audit_sha256']
            for n,digest in cell['source_code_sha256'].items():assert sha(parent/n)==digest==sha(vroot/n)==sha(folder/'source_snapshot'/n)
            count+=1
        for row in r['factor_comparison']:
            if row['behavior']!='candidate' or row['operations']=='distribution_v8':continue
            folder=Path(row['source']);cell=read(folder/'independent_analysis.json');c=cell['case']
            audit=folder/'audit-regular-mon.json.gz';assert sha(audit)==cell['audit_sha256']
            for n,digest in cell['source_code_sha256'].items():assert sha(parent/n)==digest==sha(folder/'source_snapshot'/n)
            count+=1
        assert count==14
        assert len(read(ROOT/'known_queue_diagnostic.json')['rows'])==22
        assert len(read(ROOT/'journey_tail_comparison.json')['rows'])==40
        assert len(read(ROOT/'queue_peaks_by_window.json')['rows'])==990
        assert read(ROOT/'engineering_snu_departure_half_hour_comparison.json')['daily_scope_means_cross_checked']
        extra=read(ROOT/'additional_clock_diagnostic.json');assert extra['over20_weight']>=0
        assert r['all_experiments_including_additional_clock_pass20']==(v['over20_episode_weight']<1e-7 and extra['over20_weight']<1e-7)
        assert abs(r['maximum_continuous_wait_min']-v['maximum_continuous_wait_min'])<1e-9
        missing=[];local_links=0
        for link in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)',(ROOT/'RESULTS.md').read_text(encoding='utf8')):
            if link.startswith(('https://','http://','#')):continue
            name=link.split('#',1)[0].strip('<>');local_links+=1
            if not (ROOT/name).resolve().exists():missing.append(link)
        assert not missing,missing
        figure=read(ROOT/'figure_manifest.json');assert figure['source_sha256']==sha(ROOT/'review.json')
        for name,digest in figure['outputs'].items():
            p=ROOT/name;assert sha(p)==digest;b=p.read_bytes();assert b[:8]==b'\x89PNG\r\n\x1a\n'
            w,h=struct.unpack('>II',b[16:24]);assert w>=800 and h>=400
        result.update(status='PASS_REVIEW_ARTIFACT_CONSISTENCY',audit_hashes=count,local_links=local_links,
            main_internal_status=v['status'],additional_clock_remains_failed20=extra['over20_weight']>1e-7,
            main_maximum_wait_min=r['maximum_continuous_wait_min'],empirical_status='NOT_EVALUABLE',
            report_sha256=sha(ROOT/'RESULTS.md'),review_json_sha256=sha(ROOT/'review.json'),figure_count=len(figure['outputs']))
    except Exception as exc:
        result.update(status='FAILED',error=type(exc).__name__,message=str(exc));raise
    finally:target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(result['status'],result['audit_hashes'],result['local_links'])
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--attempt',type=int,default=1);a=p.parse_args();main(a.attempt)
