import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE=Path(__file__).resolve().parent
def run(args):
    subprocess.run([sys.executable,str(HERE/'simulate.py'),*args],check=True)

if __name__=='__main__':
    cases=[(day,s,'candidate') for day in ('tue','mon','wed','fri','thu') for s in ('peak','regular')]
    cases.extend(('tue','peak',v) for v in ('nov24','nov10','berth_only','parallel','nov10_early','nov10_late'))
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(run,cases))
