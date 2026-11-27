from pathlib import Path
ROOT=Path(__file__).resolve().parent
p=ROOT/'finalize_workflow.py';assert not p.exists()
t=(ROOT.parent/'v12_linear_wait_sensitivity_20261116/finalize_workflow.py').read_text(encoding='utf8')
t=t.replace("w=ROOT.parent/'261116120358'","w=ROOT.parent/'261116122336'")
t=t.replace("sources=sources.replace('[최종 비교](FINAL_REVIEW.md)','[최종 후보 상세 결과](RESULTS.md)')",
 "sources=sources.replace('[최종 비교](FINAL_REVIEW.md)','[최종 후보 상세 결과](RESULTS.md)').replace('[사전 계획](PROTOCOL.md)','[사전 계획](../v12_current_pressure_20261116/PROTOCOL.md)')")
t=t.replace("assert len(v['results'])==2","assert len(v['results'])==3")
t=t.replace("assert len(list((w/'runs').glob('*/attempt_*')))==2","assert len(list((w/'runs').glob('*/attempt_*')))==3")
t=t.replace("assert read(w/'enabled-unit-receipt.json')['status']=='PASS'", "assert 'Ran 129 tests' in (w/'enabled-final.log').read_text(encoding='utf8') and '\\nOK\\n' in (w/'enabled-final.log').read_text(encoding='utf8')")
t=t.replace("assert read(w/'static-sensitivity-proof.json')['status']=='PASS_STATIC_SENSITIVITY_SCOPE'", "assert read(w/'static-current-pressure-proof.json')['status']=='PASS_STATIC_CURRENT_PRESSURE_SCOPE'")
t=t.replace("'main_cases':2,'not_executed_remaining_main_cases':8", "'main_cases':2,'diagnostic_cases':1,'not_executed_remaining_main_cases':8")
t=t.replace("'active':128", "'active':129")
needle="run('build_final_review.py')\n"
assert t.count(needle)==1
t=t.replace(needle,"""# The disabled-pressure diagnostic must reproduce the direct parent D.
v=read(w/'pilot-validation.json')['results']
diag=next(r for r in v if r['case']['case'].startswith('ablation'))
drows=read(ROOT.parent/'261116112731/pilot-validation.json')['results']
parent=next(r for r in drows if not r['case']['case'].startswith('ablation') and r['case']['day']=='월')
metrics=lambda r:[r['extended_diagnostics']['all_recorded_time_over20_episode_weight'],
                  r['extended_diagnostics']['all_recorded_time_max_continuous_wait_min'],
                  *r['extended_diagnostics']['finished_trip_quantiles']['total_min'].values()]
errors=[abs(a-b) for a,b in zip(metrics(diag),metrics(parent))]
assert max(errors)<1e-6,errors
target=w/'disabled-pressure-reproduction.json';assert not target.exists()
target.write_text(json.dumps({'status':'PASS_NUMERICAL_REPRODUCTION','parent':'261116112731',
    'metric_absolute_errors':errors,'maximum_absolute_error':max(errors),'new_model_execution':False,
    'scope':'Completed registered disabled-mechanism diagnostic compared to completed parent; not an independent field test.'},ensure_ascii=False,indent=2)+'\\n',encoding='utf8')
run('build_final_review.py')
""")
needle="names=['FINAL_REVIEW.md','SOURCES_AND_ASSUMPTIONS.md','experiment-review.json']\n"
assert needle in t
t=t.replace(needle,"""# Verify handoff file links, including the full and current-pilot queue tables.
import re
for name in ['FINAL_REVIEW.md','SOURCES_AND_ASSUMPTIONS.md']:
    for href in re.findall(r'\\]\\(([^)]+)\\)',(ROOT/name).read_text(encoding='utf8')):
        if not href.startswith(('http://','https://','#')):assert (ROOT/href).resolve().exists(),(name,href)
names=['FINAL_REVIEW.md','SOURCES_AND_ASSUMPTIONS.md','experiment-review.json']
""")
p.write_text(t,encoding='utf8')
print('FINALIZER_PREPARED')
