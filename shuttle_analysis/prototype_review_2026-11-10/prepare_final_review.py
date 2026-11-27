"""Separate final-candidate artifacts from the completed R7 failure review."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parent
def main():
    parent=Path(json.loads((ROOT/'individual_request_candidate.json').read_bytes())['directory'])
    work=ROOT.parent/('prototype_review_'+parent.name.rsplit('_',1)[1]);work.mkdir()
    names=['validation_metrics.py','compare_known_queues.py','compare_journey_tails.py','queue_peaks_by_window.py','verify_production_unchanged.py']
    for n in names:shutil.copy2(ROOT/n,work/n)
    p=work/'compare_known_queues.py';s=p.read_text(encoding='utf8')
    old="            jobs.append(('prototype_V8',scenario,day,folder/f'audit-{scenario}-{day}.json.gz'))";assert old in s
    s=s.replace(old,"            if not folder.exists():folder=validation/f'runs/distribution_v8-combined-{scenario}-{day}/attempt_01'\n"+old,1)
    p.write_text(s,encoding='utf8')
    (work/'creation_manifest.json').write_text(json.dumps({'candidate':str(parent),'previous_review':str(ROOT),
        'source_files':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names},
        'all_original_R7_files_preserved':True,'new_algorithm_promoted':False,'production_approval_required':True,
        'one_script_adaptation':'Find Monday regular V8 in the new validation folder when parent reused cell is Thursday peak.'},ensure_ascii=False,indent=2),encoding='utf8')
    (ROOT/'final_review_location.json').write_text(json.dumps({'directory':str(work),'candidate':str(parent)},ensure_ascii=False,indent=2),encoding='utf8')
    print(work)
if __name__=='__main__':main()
