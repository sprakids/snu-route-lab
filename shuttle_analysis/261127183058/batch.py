"""Run independent weekday replays. Use the same interpreter for every process."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent

def replay(job):
    day, service, mode = job
    folder = HERE / "runs" / mode / f"{service}-{day}"
    folder.mkdir(parents=True, exist_ok=True)
    summary=folder/"summary.json"
    if summary.exists():
        key=f"{service}-{day}"
        required=(f"audit-{key}.json.gz",f"{key}.json.gz")
        if all((folder/name).exists() for name in required):return
        # Earlier research runs keep their summary after the detailed output is pruned.
        with TemporaryDirectory(prefix="snu-r-replay-") as tmp:
            subprocess.run([sys.executable,str(HERE/"v13.py"),*job,"--output",tmp],check=True)
            rebuilt=Path(tmp)/"runs"/mode/key
            if json.loads((rebuilt/"summary.json").read_bytes())!=json.loads(summary.read_bytes()):
                raise ValueError(f"Regenerated run disagrees with the archived summary: {job}")
            for name in required:
                if not (folder/name).exists():
                    with TemporaryDirectory(dir=folder) as staged:
                        local=Path(staged)/name
                        shutil.copyfile(rebuilt/name,local)
                        local.replace(folder/name)
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
