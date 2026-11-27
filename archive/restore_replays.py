"""Recreate a historical uncompressed JSON by verifying its recorded gzip sibling."""
import argparse
import csv
import gzip
import hashlib
from pathlib import Path
from tempfile import NamedTemporaryFile

ROOT=Path(__file__).resolve().parents[1]
def restore(relative):
    with gzip.open(ROOT/"archive/replay_copies.csv.gz","rt",encoding="utf8",newline="") as stream:
        record=next((r for r in csv.DictReader(stream) if r["path"]==relative),None)
    if record is None:raise SystemExit("The path is not in the recoverable JSON list.")
    target=(ROOT/relative).resolve()
    if not target.is_relative_to(ROOT/"shuttle_analysis"):raise ValueError("Unexpected target")
    if target.exists():
        with target.open("rb") as existing:
            if hashlib.file_digest(existing,"sha256").hexdigest()==record["sha256"]:return
        raise FileExistsError(target)
    source=target.with_suffix(target.suffix+".gz")
    temp=None
    try:
        with gzip.open(source,"rb") as f,NamedTemporaryFile(dir=target.parent,delete=False) as out:
            temp=Path(out.name);digest=hashlib.sha256()
            for block in iter(lambda:f.read(1024*1024),b""):
                digest.update(block);out.write(block)
            if digest.hexdigest()!=record["sha256"] or out.tell()!=int(record["bytes"]):raise ValueError("Incorrect source")
        temp.rename(target)
    finally:
        if temp:temp.unlink(missing_ok=True)
    print(target)
if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path",help="Project-relative JSON path, using /")
    restore(parser.parse_args().path)
