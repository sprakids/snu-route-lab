"""Finish metadata/tests of newly created, not-yet-executed scalar candidates."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parent
for stamp in ('261112165437','261112165438'):
    work=ROOT.parent/stamp;assert not (work/'runs').exists()
    cfg=json.loads((work/'config.json').read_bytes())
    cfg['calibration_status']='Only the global effective release-lag scale is retrospectively fit to reused constraints; whole model not independently validated.'
    cfg['unverified_parameters']='Legacy tastes, hazards, walking and grade mappings remain prototype assumptions. Effective release lag is retrospectively calibrated on reused SNU queue constraints; not identified actual building egress.'
    (work/'config.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf8')
    manifest=json.loads((work/'repair_manifest.json').read_bytes());manifest['config_sha256']=hashlib.sha256((work/'config.json').read_bytes()).hexdigest()
    (work/'repair_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    shutil.copy2(ROOT/'test_release_calibration.py',work/'test_release_calibration.py')
    print('PREFLIGHT_METADATA_COMPLETE',stamp)
