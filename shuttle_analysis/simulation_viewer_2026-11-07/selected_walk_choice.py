"""Read the explicitly selected, independently verified candidate for publication."""
from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parent

def selected_work():
    path=ROOT/'crowding_walk_choices_2026-11-10/selected_candidate.json'
    if not path.exists():raise RuntimeError('No verified walk-choice candidate selected for publication')
    selection=json.loads(path.read_text(encoding='utf8'));assert selection['status']=='VERIFIED'
    work=(ROOT/selection['directory']).resolve();assert work.is_relative_to(ROOT)
    verified=json.loads((work/'independent_verification.json').read_text(encoding='utf8'))
    assert verified['status']=='PASS' and verified['simulation_runs']==10
    assert verified['model_sha256']==selection['model_sha256']
    assert hashlib.sha256((work/'prepared.json.gz').read_bytes()).hexdigest()==selection['prepared_sha256']
    return work
