"""Run independent weekday replays. Use the same interpreter for every process."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent

def replay(job):
    day, service, mode = job
    folder = HERE / "runs" / mode / f"{service}-{day}"
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "summary.json").exists():
        return
    with (folder / "run.log").open("w", encoding="utf8") as log:
        entry = "capture_inputs.py" if mode=="V13" else "v13.py"
        result = subprocess.run([sys.executable, str(HERE/entry), *job], stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"{job} failed; see {folder/'run.log'}")
    print(f"verified {job}", flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=("fit","final"))
    parser.add_argument("--workers",default=4,type=int)
    args = parser.parse_args()
    if args.step=="fit":
        jobs = [(d,"peak",m) for m in ("r20","r40","r20g10","r40g10","r40g20") for d in ("wed","thu")]
        jobs.append(("tue","peak","r0"))
    else:
        jobs = [(d,s,"V13") for d in ("mon","tue","wed","thu","fri") for s in ("peak","regular")]
    with ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(replay,jobs))
