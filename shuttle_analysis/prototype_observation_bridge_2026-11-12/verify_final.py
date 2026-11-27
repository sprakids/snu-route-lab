"""Artifact/source consistency only; never labels it field queue validation."""
from pathlib import Path
import csv,hashlib,json,re

ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    target=ROOT/'final_verification.json';assert not target.exists()
    report=ROOT/'RESULTS.md';review=read(ROOT/'review.json');prior=read(ROOT/'review_verification.json')
    assert sha(report)==prior['report_sha256'] and sha(ROOT/'review.json')==prior['review_sha256']
    candidate=Path(review['candidate']);validation=read(candidate/'pilot_validation.json')
    creation=read(candidate/'creation_manifest.json');assessment=read(ROOT/'assessment.json')
    assert validation['cases']==2 and validation['invariant_audits']=='PASS'
    assert not review['production_replacement_allowed'] and review['queue_empirical_accuracy']=='NOT_EVALUABLE'
    checked=0
    for cell in validation['results']:
        case=cell['case'];folder=candidate/'runs'/case['case']/'attempt_01'
        assert sha(folder/f'audit-{case["scenario"]}-wed.json.gz')==cell['audit_sha256']
        for name,digest in cell['source_code_sha256'].items():
            assert sha(candidate/name)==digest==sha(folder/'source_snapshot'/name)==creation['parent_source_sha256'][name]
        assert cell['parent_mass_max_error']<1e-6
        checked+=1
    ops=read(candidate/'frozen/operations_observed_train_v1.json')
    old=read(Path(creation['parent'])/'frozen/operations_distribution_v8.json')
    assert sha(candidate/'frozen/operations_observed_train_v1.json')==assessment['outputs']['operations_observed_train_v1.json']
    for rid in old['routes']:
        assert old['routes'][rid]['departures']==ops['routes'][rid]['departures']
        assert old['routes'][rid]['stops']==ops['routes'][rid]['stops']
    assert read(ROOT/'stop_identity_reconciliation.json')['matched_stop_ids']==279
    public=read(ROOT/'production_unchanged_verification_v2.json')
    assert public['status']=='PASS_V11_UNCHANGED_AND_MOBILE_ASSETS_MATCH' and len(public['responses'])==8
    links=[]
    for dest in re.findall(r'\[[^\]]*\]\(([^)]+)\)',report.read_text(encoding='utf8')):
        if dest.startswith(('https://','http://','#')):continue
        assert (ROOT/dest.split('#',1)[0].strip('<>')).resolve().exists(),dest
        links.append(dest)
    summary={'status':'PASS_ARTIFACT_AND_SCOPE_CHECKS','audits_sha_checked':checked,'local_links':len(links),
      'training_dates':assessment['training_dates'],'date_split_check_dates':assessment['heldout_diagnostic_dates'],
      'pristine_holdout':False,'queue_accuracy':'NOT_EVALUABLE','production_writes':False,
      'report_sha256':sha(report),'review_sha256':sha(ROOT/'review.json'),
      'max_stop_wait_comparison_csv_scope':'whole network per supply scenario, also repeated on engineering cohort rows for context',
      'time_error_units':'seconds between adjacent stop detections, not independent passenger wait observations',
      'future_information_and_path_loop_issues_resolved':False}
    target.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    print(summary['status'],checked,len(links))

if __name__=='__main__':main()
