"""Retrospective one-parameter cohort-release lag calibration, without thinning demand."""
from pathlib import Path
import hashlib,json,shutil
def replace(path,old,new):
    text=path.read_text(encoding='utf8');assert text.count(old)==1,(path,old[:70],text.count(old))
    path.write_text(text.replace(old,new),encoding='utf8')
def apply(work,root):
    sources=[(root/'class_release_map.json.gz','frozen/class_release_map.json.gz'),
      (root.parent/'course_demand_2026-11-06/outputs/course_endings_current.json','frozen/class_endings_source_20261106.json')]
    added=[]
    for source,name in sources:
        target=work/name;assert not target.exists();shutil.copy2(source,target)
        added.append({'path':name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
    manifest=json.loads((work/'input_manifest.json').read_bytes());manifest['frozen']+=added
    (work/'input_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    replace(work/'prepare.py',"    physical=config['physics']!='v9_frozen'", """    if config.get('cohort_release_lag_scale',1.)!=1.:
        meta=read(ROOT/'frozen/class_release_map.json.gz')
        assert meta['parent_prepared_sha256']==sha(ROOT/amendment['active_prepared'])
        alpha=config['cohort_release_lag_scale'];assert 0<alpha<=1.5
        for p in plans:
            event=meta['events'][(p[0]-1)//48]
            assert event['weekday']==day and event['building']==p[1]
            end=event['class_end_seconds'];lag=p[4]-end
            assert 60<=lag<=480
            p[4]=end+alpha*lag
    physical=config['physics']!='v9_frozen'""")
    replace(work/'analyze_followup.py',"        actual[parent]+=trip['weight'];close(trip['start'],source[parent][4]);w=trip['weight']", """        actual[parent]+=trip['weight'];expected_start=source[parent][4]
        alpha=receipt['config'].get('cohort_release_lag_scale',1.)
        if alpha!=1.:
            # Independent reconstruction from immutable class-end lineage.
            event=release_map['events'][(parent-1)//48]
            assert event['weekday']==case['day'] and event['building']==source[parent][1]
            end=event['class_end_seconds'];expected_start=end+alpha*(expected_start-end)
        close(trip['start'],expected_start);w=trip['weight']""")
    replace(work/'analyze_followup.py',"    paths=None\n", "    release_map=read(ROOT/'frozen/class_release_map.json.gz') if receipt['config'].get('cohort_release_lag_scale',1.)!=1. else None\n    paths=None\n")
    return added
