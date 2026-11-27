"""Run isolated weekdays with bounded memory and deterministic template assignments."""
import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE=Path(__file__).resolve().parent

def case(pair):
    day,service=pair
    subprocess.run([sys.executable,str(HERE/'run.py'),day,service,
                    'baseline','combined','supply','release'],check=True)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--workers',type=int,default=3)
    a=p.parse_args()
    with ThreadPoolExecutor(a.workers) as pool:
        list(pool.map(case,((day,service) for day in ('tue','mon','wed','thu','fri')
                            for service in ('peak','regular'))))
