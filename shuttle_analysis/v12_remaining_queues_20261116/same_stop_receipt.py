from pathlib import Path
import json,hashlib
root=Path(__file__).resolve().parent;peer=root.parent/'collaboration/v12_remaining_queues_20261116'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
expected={'DIAGNOSIS.md':'7f3ef813e87ef8becca84351313d6a883c8ffb4e2b83d14d638ac26f574401ff','evidence.json':'919cebbc4c927067c2affec869869431c7036bd369b87c39fb2da9a65882b38b'}
for n,h in expected.items():assert sha(peer/n)==h,n
out=root/'independent-diagnosis-receipt.json';assert not out.exists()
out.write_text(json.dumps({'directory':str(peer),'verified_sha256':expected,'scope':'Read-only existing ledger/static independent diagnosis; no independent field outcome validation or new model runs'},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('INDEPENDENT_DIAGNOSIS_HASHES_MATCH')
