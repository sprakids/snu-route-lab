"""Create a versioned read-only ledger for later failures; preserve the first87,353 rows."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parent
def main():
    source=ROOT/'diagnose_all_long_waits.py';target=ROOT/'diagnose_followups_182218.py'
    assert not target.exists()
    s=source.read_text(encoding='utf8')
    old="    roots=[ANALYSIS/'prototype_model_2026-11-10',*[ANALYSIS/f'prototype_followup_{stamp}' for stamp in ('261110165541','261110171121','261110172045','261110173157','261110175338')]]"
    assert old in s
    s=s.replace(old,"    roots=[ANALYSIS/'prototype_followup_261110175338',ANALYSIS/'prototype_followup_261110180529',ANALYSIS/'prototype_followup_261110181553',ANALYSIS/'prototype_validation_261110182218']",1)
    s=s.replace("output=ROOT/'long_wait_episodes.csv'","output=ROOT/'long_wait_episodes_followups_182218.csv'",1)
    s=s.replace("ROOT/'long_wait_episodes.json'","ROOT/'long_wait_episodes_followups_182218.json'",1)
    old="def main():\n"
    s=s.replace(old,old+"    assert (ANALYSIS/'prototype_validation_261110182218/validation.json').exists(),'Do not label an incomplete grid as complete'\n",1)
    target.write_text(s,encoding='utf8')
    (ROOT/'supplement_ledger_plan.json').write_text(json.dumps({'reader':target.name,'reader_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
        'original_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'original_ledger_preserved':True,'scope':'R5/R6/R7 and all11 new validation cells, completed cases only',
        'not_a_simulation_rerun':True,'production_writes':False},ensure_ascii=False,indent=2),encoding='utf8')
    print(target)
if __name__=='__main__':main()
