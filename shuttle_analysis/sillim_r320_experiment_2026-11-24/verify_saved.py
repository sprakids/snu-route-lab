"""Verify the saved event ledger; no traffic simulation, no new assignment or routing."""
import math
from experiment import (BASELINE, DAY, DEST, OUTPUT, SERVICE, TARGET, fingerprint,
                        load, prepared, reference, save)
from verify_supply import check


def main():
    bundle = prepared()
    common = bundle['prepared']['common']
    expected = load(OUTPUT/'input_check.json')
    plans = bundle['prepared']['plans'][DAY]
    assert fingerprint(plans)==expected['original_plan_hash']
    assert fingerprint(common['route_info'])==expected['supply_hash']
    selected = load(OUTPUT/'assignments.json')
    donors = {r['id']:r['donor'] for r in selected}
    by_uid = {p[0]:i for i,p in enumerate(plans)}
    for r in selected:
        i = by_uid[r['donor']]
        p = plans[i]
        assert p[1]==r['building'] and p[4]==r['start'] and p[3]+1e-8>=r['weight']
        new = [r['id'],p[1],DEST,r['weight'],p[4]]
        if r['id']==r['donor']:
            assert math.isclose(r['weight'],p[3])
            plans[i] = new
        else:
            plans[i] = [*p[:3],p[3]-r['weight'],*p[4:]]
            plans.append(new)
    added = load(OUTPUT/'added_paths.json.gz')
    assert len(common['paths'])==added['first_index']
    common['paths'].extend(added['paths'])
    common['destinations'][DEST]=list(TARGET)
    result = check(bundle,SERVICE,DAY,'thu',OUTPUT,donors)
    result['split_ids_resolved_to_original_course'] = sum(k!=v for k,v in donors.items())
    result['reference_verified'] = load(BASELINE/'result.json')['status']
    result['validator_sha256'] = reference.base.sha(OUTPUT.parent/'verify_supply.py')
    save(OUTPUT/'independent_checks.json',result)
    print(result['status'],result['checks'])


if __name__=='__main__':
    main()
