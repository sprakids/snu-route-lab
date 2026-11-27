"""Reconcile frozen inputs with the peer's final extraction contract before pilots."""
from pathlib import Path
import gzip,hashlib,json

ROOT=Path(__file__).resolve().parent
PEER=ROOT.parent/'collected_data_review_2026-11-12'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
    assert not p.exists()
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')

def main():
    output=ROOT/'peer_contract_reconciliation.json';assert not output.exists()
    contract=read(PEER/'calibration_contract.json')
    raw=json.loads(gzip.decompress((ROOT/'source_snapshot/observed_intervals.json.gz').read_bytes()))
    peer=read(PEER/'adjacent_segment_samples_stable_dates.json')
    def key(r):return (r['day'],r['route'],int(r['from_seq']),int(r['to_seq']),int(r['hour']))
    frozen={key(r):r['seconds'] for r in raw['travel'] if r['day'] in ('2026-11-10','2026-11-11') and int(r['to_seq'])==int(r['from_seq'])+1}
    checked={key(r):r['seconds'] for r in peer}
    assert frozen==checked,'The peer changed the extraction; preserve current bridge and prepare a new version.'
    candidate=Path(read(ROOT/'private_candidate.json')['directory'])
    for name in ('calibration_contract.json','calibration_candidates.json'):
        target=candidate/'frozen'/('peer_'+name);assert not target.exists();target.write_bytes((PEER/name).read_bytes())
    manifest=read(candidate/'input_manifest.json')
    for name in ('calibration_contract.json','calibration_candidates.json'):
        relative='frozen/peer_'+name
        manifest['frozen'].append({'path':relative,'sha256':sha(candidate/relative)})
    prior_manifest=ROOT/'candidate_input_manifest_before_peer_contract.json';assert not prior_manifest.exists()
    prior_manifest.write_bytes((candidate/'input_manifest.json').read_bytes())
    (candidate/'input_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    note='\n\n검증 표현 정정: 11/11 자료는 구현 에이전트가 이미 기술적으로 살펴본 자료이다. 11/10 학습과 날짜를 분리한 사후 점검이며, 완전히 미사용인 최종 검증 자료로 주장하지 않는다. 학습값과 셀 선택에 11/11 값은 사용하지 않았다.\n'
    (candidate/'PLAN.md').write_text((candidate/'PLAN.md').read_text(encoding='utf8')+note,encoding='utf8')
    write(output,{'status':'PASS_EXACT_ADJACENT_EXTRACTION_MATCH','interval_groups':len(frozen),
        'interval_count':sum(map(len,frozen.values())), 'peer_contract_sha256':sha(PEER/'calibration_contract.json'),
        'pristine_holdout':False,'evaluation_kind':'Tuesday-fit Wednesday date-split retrospective check; Wednesday previously described by peer',
        'shuttle_history_available':contract['shuttle_gap']['continuous_archives_available'],
        'missing_city_crowd':contract['missing_city_crowd'],'production_writes':False})
    print('PASS_PEER_CONTRACT_RECONCILIATION',len(frozen),sum(map(len,frozen.values())),flush=True)

if __name__=='__main__':main()
