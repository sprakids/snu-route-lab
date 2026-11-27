"""Final immutable-source/reference/artifact checks, not field-accuracy certification."""
from pathlib import Path
import argparse,csv,hashlib,json,re

ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main(release):
    release=Path(release).resolve();target=release/'final_verification.json';assert not target.exists()
    v=read(release/'validation_reference_corrected.json');original=read(release/'validation.json')
    review=read(release/'review_final.json');inventory=read(release/'evidence_inventory_final.json');creation=read(release/'creation_manifest.json')
    assert re.fullmatch(r'\d{12}',review['release_id']) and review['version_family']=='V12'
    assert len(v['results'])==10 and review['cases']==10
    assert review['validation_sha256']==sha(release/'validation_reference_corrected.json')
    assert review['inventory_sha256']==sha(release/'evidence_inventory_final.json')
    assert review['queue_empirical_accuracy']=='NOT_EVALUABLE' and not review['production_replacement_allowed']
    runtime_checks=0
    for before,after in zip(original['results'],v['results']):
        assert {k:x for k,x in before.items() if k!='r10_reference'}=={k:x for k,x in after.items() if k!='r10_reference'}
        c=after['case'];assert c['seed']==0
        ref=after['r10_reference'];assert ref['reference_case']['seed']==c['seed']
        assert ref['reference_case']['day']==c['day'] and ref['reference_case']['scenario']==c['scenario']
        assert ref['reference_case']['operations']=='distribution_v8'
        day={'월':'mon','화':'tue','수':'wed','목':'thu','금':'fri'}[c['day']]
        folder=Path(after['source_directory']);assert sha(folder/f'audit-{c["scenario"]}-{day}.json.gz')==after['audit_sha256']
        assert sha(Path(ref['source_directory'])/f'audit-{c["scenario"]}-{day}.json.gz')==ref['audit_sha256']
        for name,digest in after['source_code_sha256'].items():
            assert sha(release/name)==digest==sha(folder/'source_snapshot'/name);runtime_checks+=1
        assert after['parent_mass_max_error']<1e-6
        usage=after['policy_report']['empirical_evidence']['calls_are_model_queries_not_people']
        assert usage.get('historical_ordinal_distribution_and_transition',0)>0 and usage.get('missing_observed_grade_model_occupancy_scenario_fallback',0)>0
    for name,digest in creation['parent_source_sha256'].items():assert sha(Path(creation['parent'])/name)==digest
    plan=read(release/'future_evaluation_plan.json')
    assert not plan['new_outcome_raw_opened'] and not plan['production_promotion_allowed']
    for name,digest in plan['frozen_sha256'].items():assert sha(release/name)==digest
    evidence=read(release/'frozen/empirical_evidence.json')
    assert evidence['full_flag_passage_n']==28935 and evidence['full_flag_true_n']==14
    for rid in evidence['missing_crowd_routes']:assert not any(k.startswith(rid+'|') for k in evidence['grades'])
    assert len(inventory['items'])==53
    assert sum(r['integration_status']=='UNAVAILABLE_NOT_APPLIED' for r in inventory['items'])==6
    ledger=read(release/'field_observation_usage_ledger_final.json')
    assert len(ledger['observations'])==4 and ledger['individual_wait']['individual_samples']==1
    assert ledger['individual_wait']['queue_people']==67 and ledger['individual_wait']['queue_wait_seconds']==189 and ledger['individual_wait']['post_boarding_seconds']==30
    assert ledger['individual_wait']['network_validation_status']=='NOT_EVALUABLE'
    with (release/'all_stops_waits.csv').open(encoding='utf-8-sig') as f:assert len(list(csv.DictReader(f)))==990
    with (release/'field_queue_comparison_final.csv').open(encoding='utf-8-sig') as f:assert len(list(csv.DictReader(f)))==24
    source_report=release/'RESULTS_FINAL.md';links=[]
    for dest in re.findall(r'\[[^\]]*\]\(([^)]+)\)',source_report.read_text(encoding='utf8')):
        if dest.startswith(('https://','http://','#')):continue
        assert (release/dest.split('#',1)[0].strip('<>')).resolve().exists(),dest;links.append(dest)
    public=read(release/'production_unchanged_verification_v2.json')
    assert public['status']=='PASS_V11_UNCHANGED_AND_MOBILE_ASSETS_MATCH' and len(public['responses'])==8
    assert public['expected_model_id']=='261110162302'
    assert 'Ran 44 tests' in (release/'boundary-integration-evidence-tests.log').read_text(encoding='utf8')
    result={'status':'PASS_SOURCE_REFERENCE_AND_ARTIFACT_CHECKS','release_id':review['release_id'],'version_family':'V12',
      'candidate_audit_hashes':10,'r10_same_seed_reference_hashes':10,'runtime_snapshot_hash_checks':runtime_checks,
      'future_frozen_hash_checks':len(plan['frozen_sha256']),'inventory_items':53,'unavailable_items':6,'local_links':len(links),
      'internal_status':v['status'],'empirical_queue_accuracy':'NOT_EVALUABLE','original_candidate_outcomes_unchanged_by_reference_fix':True,
      'original_and_corrected_reports_preserved':True,'production_writes':False,'production_replacement_allowed':False,
      'report_sha256':sha(source_report),'review_sha256':sha(release/'review_final.json')}
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(result['status'],runtime_checks,len(links),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--release',required=True);a=p.parse_args();main(a.release)
