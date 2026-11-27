from pathlib import Path
import sys,unittest
w=Path(sys.argv[1]).resolve();sys.path.insert(0,str(w))
names=['test_student_strategy','test_walking_opportunities','test_same_stop_release','test_trunk_preservation',
    'test_primary_stop','test_transfer_perception','test_review_perception','test_current_pressure','test_direct_restoration','test_nominal_transfer']
suite=unittest.defaultTestLoader.loadTestsFromNames(names)
with (w/'enabled-final.log').open('x',encoding='utf8') as f:result=unittest.TextTestRunner(stream=f).run(suite)
print('ACTIVE_TESTS',suite.countTestCases(),'PASS' if result.wasSuccessful() else 'FAIL',flush=True)
assert result.wasSuccessful()
