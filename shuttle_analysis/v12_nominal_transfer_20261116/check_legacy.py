"""Run inherited components with the student wrapper explicitly disabled in memory."""
from pathlib import Path
import sys,unittest
w=Path(sys.argv[1]).resolve();sys.path.insert(0,str(w))
import artifacts
original=artifacts.read
def read(p):
    result=original(p)
    if Path(p).resolve()==w/'config.json':result['student_strategy']=False
    return result
artifacts.read=read
modules=[p.stem for p in sorted(w.glob('test_*.py')) if p.stem not in ['test_student_strategy','test_walking_opportunities','test_same_stop_release','test_trunk_preservation','test_primary_stop','test_transfer_perception','test_review_perception','test_linear_wait_sensitivity','test_current_pressure','test_direct_restoration','test_nominal_transfer']]
suite=unittest.defaultTestLoader.loadTestsFromNames(modules)
with (w/'legacy-final.log').open('x',encoding='utf8') as log:
    log.write('LEGACY COMPONENT SCOPE: student_strategy=False in memory; active user behavior is checked separately\n')
    result=unittest.TextTestRunner(stream=log).run(suite)
print('LEGACY_COMPONENTS',suite.countTestCases(),'tests',result.wasSuccessful(),flush=True)
assert result.wasSuccessful()
