"""Parent regression components with new policy explicitly disabled in fixtures."""
from pathlib import Path
import argparse,sys,unittest
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');a=p.parse_args();w=Path(a.candidate).resolve();sys.path.insert(0,str(w))
    import artifacts
    raw=artifacts.read
    def component_config(path):
        value=raw(path)
        if Path(path).resolve()==(w/'config.json').resolve():value={**value,'student_strategy':False}
        return value
    artifacts.read=component_config
    patterns=[f.name for f in w.glob('test_*.py') if f.name not in ('test_student_strategy.py','test_walking_opportunities.py')]
    suite=unittest.TestSuite()
    for pattern in sorted(patterns):suite.addTests(unittest.defaultTestLoader.discover(str(w),pattern=pattern))
    print('LEGACY COMPONENT SCOPE: student_strategy=False; new enabled-policy tests are separate',flush=True)
    result=unittest.TextTestRunner(verbosity=1).run(suite);sys.exit(0 if result.wasSuccessful() else 1)
if __name__=='__main__':main()
